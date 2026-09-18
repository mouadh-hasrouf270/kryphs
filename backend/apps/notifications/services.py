from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.notifications.models import Notification
from apps.requests_app.models import CreativeRequest
from apps.workspaces.policies import validate_scope


def scan_deadlines():
    now = timezone.now()
    count = 0
    requests = (
        CreativeRequest.objects.filter(
            workspace__active=True, due_date__lte=now + timedelta(days=1)
        )
        .exclude(status__in=["approved", "published"])
        .select_related("workspace", "brand", "owner", "requester")
    )
    for request in requests:
        kind = "overdue" if request.due_date < now else "deadline_approaching"
        for user in {request.owner, request.requester} - {None}:
            try:
                validate_scope(user, request.workspace_id, request.brand)
            except (PermissionDenied, ValidationError):
                continue
            if (
                getattr(getattr(user, "profile", None), "notification_preferences", {}).get(kind)
                is False
            ):
                continue
            _, created = Notification.objects.get_or_create(
                dedupe_key=f"deadline:{request.pk}:{user.pk}:{kind}:{now.date()}",
                defaults={
                    "workspace": request.workspace,
                    "brand": request.brand,
                    "user": user,
                    "kind": kind,
                    "title": request.title,
                    "link": f"/requests/{request.pk}",
                },
            )
            count += int(created)
    return count
