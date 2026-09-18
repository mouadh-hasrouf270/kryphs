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

    require(actor, data["workspace"].pk, "create_requests")
    validate_scope(actor, data["workspace"].pk, data.get("brand"))
    obj = CreativeRequest.objects.create(**data, requester=actor, code=code("REQ"))
    if platforms:
        obj.platforms.set(platforms)

    for i, entry in enumerate(deliverables or [], 1):
        RequestDeliverable.objects.create(
            workspace=obj.workspace,
            brand=obj.brand,
            request=obj,
            sequence=i,
            title=entry["title"],
            creative_type=entry.get("creative_type", "video"),
        )
    record(actor, obj, "request_created")
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
            d.status = "assigned"
            d.save()
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
    record(actor, obj, "in_production")
    return obj


def rollup(creative):
    if creative.deliverable_id:
        siblings = list(
            creative.__class__.objects.filter(deliverable_id=creative.deliverable_id).values_list(
                "status", flat=True
            )
        )
        d = creative.deliverable
        d.status = aggregate(siblings)
        d.save(update_fields=["status", "updated_at"])
    if creative.request_id:
        request = creative.request
        states = list(request.deliverables.values_list("status", flat=True))
        if not states:
            states = list(
                creative.__class__.objects.filter(request=request).values_list("status", flat=True)
            )
        request.status = aggregate(states)
        if request.status == "approved":
            request.completed_at = timezone.now()
        if request.status == "published":
            request.published_at = timezone.now()
        request.save()


def aggregate(states):
    if not states:
        return "new"
    if all(s == "published" for s in states):
        return "published"
    if all(s in ["approved", "published"] for s in states):
        return "approved"
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
