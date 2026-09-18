from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record
from apps.creatives.models import Creative, CreativeFeedback, CreativeRelationship, CreativeVersion
from apps.requests_app.services import code, rollup
from apps.workspaces.policies import permissions, require, validate_scope


def editor_access(actor, creative):
    require(actor, creative.workspace_id, "submit_version")
    validate_scope(actor, creative.workspace_id, creative.brand)
    if creative.owner_id != actor.pk and "assign_editors" not in permissions(
        actor, creative.workspace_id
    ):
        raise PermissionDenied("Only the assigned editor can submit this creative.")


@transaction.atomic
def new_version(actor, creative, notes=""):
    creative = Creative.objects.get(pk=creative.pk)
    editor_access(actor, creative)
    if creative.current_version_id and creative.current_version.status not in [
        "changes_requested",
        "approved",
        "published",
    ]:
        raise ValidationError("Finish the current version before adding another.")
    number = (creative.versions.aggregate(n=Max("version_number"))["n"] or 0) + 1
    version = CreativeVersion.objects.create(
        workspace=creative.workspace,
        brand=creative.brand,
        creative=creative,
        editor=actor,
        version_number=number,
        label=f"v{number:03}",
        version_type="original" if number == 1 else "revision",
        notes=notes,
    )
    creative.current_version = version
    creative.status = "in_production"
    creative.save()
    rollup(creative)
    record(actor, creative, "version_created", {"version": number})
    return version


@transaction.atomic
def transition(actor, creative, action, feedback=""):
    creative = Creative.objects.select_related("current_version").get(pk=creative.pk)
    validate_scope(actor, creative.workspace_id, creative.brand)
    version = creative.current_version
    if not version:
        raise ValidationError("Create a version first.")
    if action == "submit":
        editor_access(actor, creative)
        if version.status != "draft":
            raise ValidationError("Only a draft can be submitted.")
        version.status = "submitted"
        version.submitted_at = timezone.now()
        creative.status = "ready_for_review"
    elif action in ["approve", "request-changes"]:
        require(
            actor,
            creative.workspace_id,
            "approve_version" if action == "approve" else "review_version",
        )
        if version.status != "submitted":
            raise ValidationError("Only a submitted version can be reviewed.")
        if version.editor_id == actor.pk and "assign_editors" not in permissions(
            actor, creative.workspace_id
        ):
            raise PermissionDenied("You cannot review your own version.")
        if action == "request-changes" and not feedback.strip():
            raise ValidationError({"feedback": "Explain the changes required."})
        version.status = "approved" if action == "approve" else "changes_requested"
        creative.status = version.status
        if action == "approve":
            version.approved_at = timezone.now()
            creative.approved_version = version
        CreativeFeedback.objects.create(
            workspace=creative.workspace,
            brand=creative.brand,
            version=version,
            author=actor,
            text=feedback,
            category=version.status,
        )
    else:
        raise ValidationError("Unknown workflow action.")
    version.save()
    creative.save()
    rollup(creative)
    event = record(actor, creative, creative.status, {"version": version.version_number})
    from apps.automations.services import dispatch

    dispatch(event, creative)
    return creative


@transaction.atomic
def related(actor, parent, data):
    require(actor, parent.workspace_id, "manage_lineage")
    validate_scope(actor, parent.workspace_id, parent.brand)
    child = Creative.objects.create(
        workspace=parent.workspace,
        brand=parent.brand,
        title=data.get("title") or parent.title + " — variant",
        code=code("CR"),
        product=parent.product,
        campaign=parent.campaign,
        owner=parent.owner,
        creative_type=parent.creative_type,
    )
    CreativeRelationship.objects.create(
        workspace=parent.workspace,
        brand=parent.brand,
        parent=parent,
        child=child,
        relationship=data.get("relationship", "variant"),
        hypothesis=data.get("hypothesis", ""),
        what_changed=data.get("what_changed", ""),
        reason=data.get("reason", ""),
        author=actor,
    )
    record(actor, child, "related_creative_created", {"parent": str(parent.pk)})
    return child


def confirmed_publication(actor, version):
    """Called only after a durable provider receipt, inside its final transaction."""
    version.refresh_from_db()
    if version.status not in ["approved", "published"]:
        raise ValidationError("Only an approved version can be published.")
    if version.status == "published":
        return
    version.status = "published"
    version.published_at = timezone.now()
    version.save(update_fields=["status", "published_at", "updated_at"])
    creative = Creative.objects.get(pk=version.creative_id)
    if creative.current_version_id == version.pk:
        creative.status = "published"
        creative.save(update_fields=["status", "updated_at"])
        rollup(creative)
    record(actor, creative, "published", {"version": version.version_number})
