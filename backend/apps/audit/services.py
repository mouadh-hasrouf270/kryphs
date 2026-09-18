from apps.audit.models import Activity, AuditEvent
from apps.common.middleware import correlation, request_metadata
from apps.notifications.models import Notification
from apps.workspaces.models import WorkspaceMembership


def record(actor, obj, action, summary=None, notify=True):
    workspace = obj.workspace
    brand = getattr(obj, "brand", None)
    kwargs = dict(
        workspace=workspace,
        brand=brand,
        actor=actor,
        action=action,
        object_type=obj._meta.model_name,
        object_id=str(obj.pk),
    )
    event = AuditEvent.objects.create(
        **kwargs,
        summary=summary or {},
        correlation_id=correlation.get(),
        **(request_metadata.get() or {}),
    )
    title = getattr(obj, "title", getattr(obj, "name", action))
    Activity.objects.create(**kwargs, title=str(title)[:200])
    if notify:
        members = (
            WorkspaceMembership.objects.filter(
                workspace=workspace, active=True, user__is_active=True
            )
            .select_related("user")
            .prefetch_related("brands")
        )
        for member in members:
            if member.user_id == getattr(actor, "pk", None):
                continue
            if member.brand_restricted and (
                not brand or not member.brands.filter(pk=brand.pk).exists()
            ):
                continue
            prefs = getattr(getattr(member.user, "profile", None), "notification_preferences", {})
            if obj._meta.model_name in [
                "creativerequest",
                "requestdeliverable",
                "requestdeliverableassignment",
            ]:
                from apps.workspaces.policies import visible_requests

                request_id = (
                    obj.pk
                    if obj._meta.model_name == "creativerequest"
                    else obj.request_id
                    if obj._meta.model_name == "requestdeliverable"
                    else obj.deliverable.request_id
                )
                if not visible_requests(member.user, workspace.pk).filter(pk=request_id).exists():
                    continue
            if prefs.get(action) is False or prefs.get("in_app") is False:
                continue
            if (
                action in ["approved", "ready_for_review", "changes_requested"]
                and member.role == "viewer"
            ):
                continue
            route = {"creativerequest": "requests", "creative": "creatives"}.get(
                obj._meta.model_name, "activity"
            )
            Notification.objects.get_or_create(
                dedupe_key=f"{event.pk}:{member.user_id}",
                defaults=dict(
                    workspace=workspace,
                    brand=brand,
                    user=member.user,
                    kind=action,
                    title=f"{action}: {title}"[:200],
                    link=f"/{route}" + (f"/{obj.pk}" if route != "activity" else ""),
                ),
            )
    return event


def security_event(user, action, actor=None):
    for member in WorkspaceMembership.objects.filter(user=user, active=True):
        AuditEvent.objects.create(
            workspace=member.workspace,
            actor=actor or user,
            action=action,
            object_type="user",
            object_id=str(user.pk),
            correlation_id=correlation.get(),
            **(request_metadata.get() or {}),
        )
