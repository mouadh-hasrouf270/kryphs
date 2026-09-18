from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record
from apps.requests_app.models import RequestDeliverable, RequestDeliverableAssignment
from apps.workspaces.models import WorkspaceMembership
from apps.workspaces.policies import permissions, require, validate_scope, visible_requests


def can_manage(actor, deliverable, role):
    validate_scope(actor, deliverable.workspace_id, deliverable.brand)
    granted = permissions(actor, deliverable.workspace_id)
    if role == "editor":
        require(actor, deliverable.workspace_id, "assign_editors")
    elif "assign_editors" not in granted:
        require(actor, deliverable.workspace_id, "create_requests")
        if deliverable.request.requester_id != actor.pk:
            raise PermissionDenied(
                "Only the requester or an assignment manager may edit the production team."
            )
    if (
        not visible_requests(actor, deliverable.workspace_id)
        .filter(pk=deliverable.request_id)
        .exists()
    ):
        raise PermissionDenied("Request unavailable.")


def sync_primary(deliverable):
    """Called by each existing editor assignment path; preserve matching notes."""
    rows = RequestDeliverableAssignment.objects.filter(deliverable=deliverable, role="editor")
    rows.exclude(user_id=deliverable.assigned_editor_id).delete()
    if deliverable.assigned_editor_id:
        RequestDeliverableAssignment.objects.get_or_create(
            deliverable=deliverable,
            role="editor",
            user=deliverable.assigned_editor,
            defaults={"workspace": deliverable.workspace, "brand": deliverable.brand},
        )


@transaction.atomic
def save_assignment(actor, data, instance=None):
    data = dict(data)
    deliverable = data.get("deliverable", getattr(instance, "deliverable", None))
    deliverable = RequestDeliverable.objects.select_for_update().get(pk=deliverable.pk)
    role = data.get("role", getattr(instance, "role", None))
    user = data.get("user", getattr(instance, "user", None))
    if role not in dict(RequestDeliverableAssignment._meta.get_field("role").choices):
        raise ValidationError({"role": "Select a production responsibility."})
    can_manage(actor, deliverable, role)
    if instance:
        can_manage(actor, deliverable, instance.role)
        if instance.deliverable_id != deliverable.pk:
            raise ValidationError("Assignments cannot be moved to another deliverable.")
    if (
        not user
        or not user.is_active
        or not WorkspaceMembership.objects.filter(
            workspace=deliverable.workspace, user=user, active=True
        ).exists()
    ):
        raise ValidationError({"user": "Select an active member of this workspace."})
    validate_scope(user, deliverable.workspace_id, deliverable.brand)
    duplicate = RequestDeliverableAssignment.objects.filter(
        deliverable=deliverable, user=user, role=role
    ).exclude(pk=getattr(instance, "pk", None))
    if duplicate.exists():
        raise ValidationError({"user": "This person already has this responsibility."})
    if instance and instance.role == "editor" and role != "editor":
        deliverable.assigned_editor = None
        deliverable.save(update_fields=["assigned_editor"])
        instance.delete()
        instance = None
    if role == "editor":
        if instance and instance.role != "editor":
            instance.delete()
        from apps.requests_app.services import assign

        assign(actor, deliverable, user)
        instance = RequestDeliverableAssignment.objects.get(deliverable=deliverable, role="editor")
    if instance is None:
        instance = RequestDeliverableAssignment(
            deliverable=deliverable, workspace=deliverable.workspace, brand=deliverable.brand
        )
    instance.user, instance.role = user, role
    instance.notes = data.get("notes", instance.notes)
    instance.save()
    record(
        actor,
        instance,
        "production_assignment_saved",
        {"person": str(user), "responsibility": role},
    )
    return instance


@transaction.atomic
def remove_assignment(actor, obj):
    can_manage(actor, obj.deliverable, obj.role)
    record(
        actor,
        obj,
        "production_assignment_removed",
        {"person": str(obj.user), "responsibility": obj.role},
    )
    if obj.role == "editor":
        obj.deliverable.assigned_editor = None
        obj.deliverable.save(update_fields=["assigned_editor"])
    obj.delete()
    # Removing a person must not undo already completed production work.
