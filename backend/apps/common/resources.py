"""Explicit public resource registry. New models are not automatically exposed."""

from django.apps import apps

# route: model label, write permission, read permission
DEFINITIONS = {
    "deliverable-assignments": (
        "requests_app.RequestDeliverableAssignment",
        "create_requests",
        "view_creatives",
    ),
    "brands": ("catalog.Brand", "manage_workspaces", "view_creatives"),
    "products": ("catalog.Product", "create_products", "view_creatives"),
    "campaigns": ("catalog.Campaign", "create_campaigns", "view_creatives"),
    "projects": ("catalog.Project", "manage_projects", "view_creatives"),
    "tags": ("catalog.Tag", "manage_taxonomy", "view_creatives"),
    "taxonomy": ("catalog.Taxonomy", "manage_taxonomy", "view_creatives"),
    "attributes": ("catalog.AttributeValue", "manage_taxonomy", "view_creatives"),
    "naming": ("catalog.NamingTemplate", "manage_naming", "view_creatives"),
    "requests": ("requests_app.CreativeRequest", "create_requests", "view_creatives"),
    "deliverables": ("requests_app.RequestDeliverable", "create_requests", "view_creatives"),
    "sources": ("requests_app.RequestSourceMaterial", "manage_source_materials", "view_creatives"),
    "source-usages": (
        "requests_app.SourceMaterialUsage",
        "manage_source_materials",
        "view_creatives",
    ),
    "creatives": ("creatives.Creative", "edit_creatives", "view_creatives"),
    "versions": ("creatives.CreativeVersion", "submit_version", "view_creatives"),
    "comments": ("creatives.CreativeComment", "comment_creatives", "view_creatives"),
    "feedback": ("creatives.CreativeFeedback", "review_version", "view_creatives"),
    "relationships": ("creatives.CreativeRelationship", "manage_lineage", "view_creatives"),
    "storage/connections": (
        "storage.StorageConnection",
        "manage_storage_connections",
        "view_storage_connections",
    ),
    "storage/objects": ("storage.StorageObject", "submit_version", "view_creatives"),
    "files": ("storage.CreativeFile", "submit_version", "view_creatives"),
    "storage/folders": (
        "storage.DriveFolderMapping",
        "manage_storage_connections",
        "view_storage_connections",
    ),
    "storage/uploads": ("storage.Upload", "submit_version", "view_creatives"),
    "storage/syncs": ("storage.SyncRun", "manage_storage_connections", "view_storage_connections"),
    "clips": ("storage.Clip", "manage_clips", "view_creatives"),
    "clip-usages": ("storage.ClipUsage", "manage_clips", "view_creatives"),
    "content": ("storage.ContentIndexEntry", "manage_content_index", "view_creatives"),
    "ad-connections": ("integrations.AdConnection", "manage_deployments", "view_analytics"),
    "publishing": ("integrations.PublishJob", "publish_ads", "manage_deployments"),
    "publish-steps": ("integrations.PublishStep", "publish_ads", "manage_deployments"),
    "deployments": ("performance.Deployment", "manage_deployments", "view_analytics"),
    "performance": ("performance.PerformanceSnapshot", "manage_performance", "view_analytics"),
    "outcomes": ("performance.OutcomeHistory", "mark_winner", "view_analytics"),
    "experiments": ("experiments.Experiment", "manage_experiments", "view_analytics"),
    "experiment-arms": ("experiments.ExperimentArm", "manage_experiments", "view_analytics"),
    "context": ("context_hub.ContextDocument", "manage_context", "view_creatives"),
    "context-versions": ("context_hub.ContextDocumentVersion", "manage_context", "view_creatives"),
    "context-links": ("context_hub.ContextCreativeLink", "manage_context", "view_creatives"),
    "proposals": ("context_hub.CreativeProposal", "manage_lineage", "view_creatives"),
    "automations": ("automations.AutomationRule", "manage_automations", "manage_automations"),
    "automation-runs": ("automations.AutomationRun", "manage_automations", "manage_automations"),
    "automation-steps": (
        "automations.AutomationRunStep",
        "manage_automations",
        "manage_automations",
    ),
    "notifications": ("notifications.Notification", None, "view_creatives"),
    "activity": ("audit.Activity", None, "view_creatives"),
    "audit": ("audit.AuditEvent", None, "view_audit_log"),
    "jobs": ("common.Job", None, "manage_automations"),
}
READ_ONLY = set(
    "files versions feedback storage/objects storage/folders storage/uploads storage/syncs publishing publish-steps outcomes context-versions automation-runs automation-steps notifications activity audit jobs".split()
)
APPEND_ONLY = set(
    "performance comments relationships source-usages clip-usages context-links".split()
)
HIDDEN = {
    "submission_key",
    "submission_hash",
    "credentials_encrypted",
    "session_encrypted",
    "local_path",
    "change_token",
    "payload",
    "response",
    "receipt",
}
PROTECTED = {
    "scopes",
    "account_email",
    "winner",
    "resulting_creative",
    "id",
    "workspace",
    "created_at",
    "updated_at",
    "code",
    "status",
    "current_version",
    "approved_version",
    "outcome",
    "archived_at",
    "requester",
    "author",
    "actor",
    "created_by",
    "requested_by",
    "editor",
    "submitted_at",
    "approved_at",
    "published_at",
    "completed_at",
    "version_number",
    "last_error",
    "last_sync",
    "metrics",
    "resolved_at",
    "external_id",
    # Ordering is assigned by the backend for ordered child records.
    # It must never be supplied by generic create/edit forms.
    "sequence",
}


def models():
    return {key: apps.get_model(info[0]) for key, info in DEFINITIONS.items()}
