import uuid

from django.conf import settings
from django.db import models


class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class Scoped(Record):
    workspace = models.ForeignKey("workspaces.Workspace", on_delete=models.PROTECT)
    brand = models.ForeignKey("catalog.Brand", on_delete=models.PROTECT, null=True, blank=True)

    class Meta(Record.Meta):
        abstract = True


class Job(Scoped):
    type = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="queued")
    priority = models.IntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    available_at = models.DateTimeField(
        default=__import__("django.utils.timezone", fromlist=["now"]).now
    )
    claimed_at = models.DateTimeField(null=True)
    heartbeat_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    failed_at = models.DateTimeField(null=True)
    last_error = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=200, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)

    class Meta(Scoped.Meta):
        indexes = [models.Index(fields=["status", "available_at"])]


class LegacyMapping(Record):
    source = models.CharField(max_length=64)
    table = models.CharField(max_length=100)
    legacy_id = models.CharField(max_length=100)
    target_id = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "table", "legacy_id"], name="legacy_identity")
        ]
