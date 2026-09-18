import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record
from apps.requests_app.models import CreativeRequest, RequestDeliverable
from apps.workspaces.models import WorkspaceMembership
from apps.workspaces.policies import require, validate_scope

TRANSITIONS = {
    "new": ["assigned"],
    "assigned": ["in_production"],
    "in_production": ["ready_for_review"],
    "ready_for_review": ["approved", "changes_requested"],
    "changes_requested": ["in_production"],
    "approved": ["published"],
    "published": ["refresh_requested"],
    "refresh_requested": ["in_production"],
}


def code(prefix):
    return f"{prefix}-{timezone.now().year}-{uuid.uuid4().hex[:10].upper()}"


def assert_editor(user, workspace, brand):
    member = WorkspaceMembership.objects.filter(
        user=user, workspace=workspace, active=True, role__in=["editor", "manager"]
    ).first()
    if not member or not user.is_active:
        raise ValidationError({"owner": "Select an active editor or manager in this workspace."})
    validate_scope(user, workspace.pk, brand)


@transaction.atomic
def create_request(actor, data, deliverables=None):
    # Model.objects.create() cannot accept many-to-many values.  The API serializer
    # validates ``platforms`` correctly, but this domain service bypasses
    # serializer.save(), so the relation must be applied after the request has a PK.
    data = dict(data)
    platforms = data.pop("platforms", [])
    deliverables = data.pop("deliverables", deliverables)

    require(actor, data["workspace"].pk, "create_requests")
    validate_scope(actor, data["workspace"].pk, data.get("brand"))
    obj = CreativeRequest.objects.create(**data, requester=actor, code=code("REQ"))
    obj.platforms.set(platforms)

    for i, entry in enumerate(deliverables or [], 1):
        RequestDeliverable.objects.create(
            workspace=obj.workspace,
            brand=obj.brand,
            request=obj,
            sequence=i,
            **entry,
        )
    if obj.owner_id:
        assign(actor, obj, obj.owner)
    for child in obj.deliverables.all():
        if child.assigned_editor_id:
            child.status = "assigned"
            child.save(update_fields=["status"])
            from apps.requests_app.assignments import sync_primary

            sync_primary(child)
    recalculate_request(obj)
    record(actor, obj, "request_created")
    return obj


@transaction.atomic
def update_request(actor, obj, data):
    require(actor, obj.workspace_id, "create_requests")
    validate_scope(actor, obj.workspace_id, obj.brand)
    from apps.workspaces.policies import permissions

    if obj.requester_id != actor.pk and "assign_editors" not in permissions(
        actor, obj.workspace_id
    ):
        raise PermissionDenied("Only the requester or manager may edit this request.")
    data = dict(data)
    platforms = data.pop("platforms", None)
    owner = data.pop("owner", None)
    for key, value in data.items():
        setattr(obj, key, value)
    obj.save()
    if platforms is not None:
        obj.platforms.set(platforms)
    if owner:
        assign(actor, obj, owner)
    record(actor, obj, "updated")
    return obj


@transaction.atomic
def assign(actor, obj, editor):
    require(actor, obj.workspace_id, "assign_editors")
    validate_scope(actor, obj.workspace_id, obj.brand)
    assert_editor(editor, obj.workspace, obj.brand)
    obj = type(obj).objects.get(pk=obj.pk)
    if obj.status not in ["new", "assigned", "in_production", "changes_requested"]:
        raise ValidationError("Assignment is closed at this stage.")
    field = "assigned_editor" if isinstance(obj, RequestDeliverable) else "owner"
    setattr(obj, field, editor)
    if obj.status == "new":
        obj.status = "assigned"
    obj.save()
    if isinstance(obj, CreativeRequest):
        for d in obj.deliverables.filter(assigned_editor__isnull=True):
            d.assigned_editor = editor
            if d.status == "new":
                d.status = "assigned"
            d.save()
            from apps.requests_app.assignments import sync_primary

            sync_primary(d)
        recalculate_request(obj)
    elif isinstance(obj, RequestDeliverable):
        from apps.requests_app.assignments import sync_primary

        sync_primary(obj)
        recalculate_request(obj.request)
    else:
        rollup(obj)
    record(actor, obj, "assignment", {"editor_id": str(editor.pk)})
    return obj


@transaction.atomic
def start(actor, obj):
    require(actor, obj.workspace_id, "submit_version")
    validate_scope(actor, obj.workspace_id, obj.brand)
    obj = type(obj).objects.get(pk=obj.pk)
    owner_id = getattr(obj, "owner_id", getattr(obj, "assigned_editor_id", None))
    if owner_id != actor.pk and "assign_editors" not in __import__(
        "apps.workspaces.policies", fromlist=["permissions"]
    ).permissions(actor, obj.workspace_id):
        raise PermissionDenied("Only the assigned editor can start this work.")
    if obj.status not in ["assigned", "changes_requested", "refresh_requested"]:
        raise ValidationError("Work cannot start in the current state.")
    obj.status = "in_production"
    obj.save()
    if isinstance(obj, CreativeRequest):
        children = list(obj.deliverables.all())
        if children:
            for child in children:
                if child.status in ["assigned", "changes_requested", "refresh_requested"]:
                    start(actor, child)
            recalculate_request(obj)
    elif isinstance(obj, RequestDeliverable):
        recalculate_request(obj.request)
    else:
        rollup(obj)
    record(actor, obj, "in_production")
    return obj


def rollup(creative):
    if creative.deliverable_id:
        recalculate_deliverable(creative.deliverable)
    if creative.request_id:
        recalculate_request(creative.request)


def recalculate_deliverable(obj):
    from apps.creatives.models import Creative

    states = list(
        Creative.objects.filter(deliverable=obj, archived_at__isnull=True).values_list(
            "status", flat=True
        )
    )
    if "changes_requested" in states:
        status = "changes_requested"
    elif states.count("published") >= obj.quantity:
        status = "published"
    elif sum(s in ["approved", "published"] for s in states) >= obj.quantity:
        status = "approved"
    elif len(states) >= obj.quantity and all(
        s in ["ready_for_review", "approved", "published"] for s in states
    ):
        status = "ready_for_review"
    elif states or obj.status not in ["new", "assigned"]:
        status = "in_production"
    else:
        status = "assigned" if obj.assigned_editor_id else "new"
    obj.status = status
    obj.save(update_fields=["status", "updated_at"])
    return obj


def recalculate_request(obj):
    from apps.creatives.models import Creative

    states = list(obj.deliverables.values_list("status", flat=True))
    if not states:
        states = list(
            Creative.objects.filter(request=obj, archived_at__isnull=True).values_list(
                "status", flat=True
            )
        )
    if states:
        obj.status = aggregate(states)
    if obj.status in ["approved", "published"] and not obj.completed_at:
        obj.completed_at = timezone.now()
    if obj.status == "published" and not obj.published_at:
        obj.published_at = timezone.now()
    obj.save()
    return obj


def aggregate(states):
    if not states:
        return "new"
    if all(s == "published" for s in states):
        return "published"
    if all(s in ["approved", "published"] for s in states):
        return "approved"
    if "changes_requested" in states:
        return "changes_requested"
    if all(s in ["ready_for_review", "approved", "published"] for s in states):
        return "ready_for_review"
    if any(
        s in ["in_production", "ready_for_review", "approved", "published", "refresh_requested"]
        for s in states
    ):
        return "in_production"
    for state in [
        "changes_requested",
        "ready_for_review",
        "in_production",
        "refresh_requested",
        "assigned",
        "new",
    ]:
        if state in states:
            return state
    return "new"
