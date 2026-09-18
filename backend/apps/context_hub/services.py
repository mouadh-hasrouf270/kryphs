from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.context_hub.models import ContextDocumentVersion
from apps.workspaces.policies import require, validate_scope


@transaction.atomic
def new_version(actor, document, data):
    require(actor, document.workspace_id, "manage_context")
    validate_scope(actor, document.workspace_id, document.brand)
    content = str(data.get("content", "")).strip()
    if not content:
        raise ValidationError("Content is required.")
    number = (document.versions.aggregate(n=Max("version_number"))["n"] or 0) + 1
    version = ContextDocumentVersion.objects.create(
        workspace=document.workspace,
        brand=document.brand,
        document=document,
        version_number=number,
        content=content,
        author=actor,
    )
    document.current_version = version
    document.save()
    record(actor, document, "context_version_created", {"version": number})
    return version


@transaction.atomic
def approve(actor, version):
    require(actor, version.workspace_id, "manage_context")
    validate_scope(actor, version.workspace_id, version.brand)
    if version.status != "draft":
        raise ValidationError("Only a draft can be approved.")
    version.status = "approved"
    version.save()
    record(actor, version, "context_approved")
    return version


@transaction.atomic
def decide_proposal(actor,proposal,decision):
    require(actor,proposal.workspace_id,'manage_lineage')
    validate_scope(actor,proposal.workspace_id,proposal.brand)
    proposal=type(proposal).objects.get(pk=proposal.pk)
    if proposal.status!='proposed' or decision not in ['accept','reject']:
        raise ValidationError('Only an open proposal can be decided.')
    if decision=='accept':
        from apps.creatives.services import related
        proposal.resulting_creative=related(actor,proposal.source,{'title':proposal.title,'relationship':'variant','hypothesis':proposal.rationale,'what_changed':proposal.proposed_change})
        proposal.status='accepted'
    else:proposal.status='rejected'
    proposal.save()
    record(actor,proposal,'proposal_'+proposal.status)
    return proposal
