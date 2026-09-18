from django.db import models

from apps.common.models import Scoped


class AdConnection(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    provider = models.CharField(
        max_length=40,
        choices=[("meta", "meta"), ("tiktok", "tiktok"), ("google_ads", "google_ads")],
        default="meta",
    )
    account_id = models.CharField(max_length=200, default="", blank=True)
    credentials_encrypted = models.TextField(blank=True)
    status = models.CharField(
        max_length=40,
        choices=[("disconnected", "disconnected"), ("connected", "connected"), ("error", "error")],
        default="disconnected",
    )
    last_sync = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")

    def __str__(self):
        return self.name


class PublishJob(Scoped):
    creative = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    version = models.ForeignKey(
        "creatives.CreativeVersion", on_delete=models.PROTECT, related_name="+"
    )
    connection = models.ForeignKey(
        "integrations.AdConnection", on_delete=models.PROTECT, related_name="+"
    )
    provider = models.CharField(
        max_length=40,
        choices=[("meta", "meta"), ("tiktok", "tiktok"), ("google_ads", "google_ads")],
        default="meta",
    )
    state = models.CharField(
        max_length=40,
        choices=[
            ("queued", "queued"),
            ("running", "running"),
            ("waiting", "waiting"),
            ("succeeded", "succeeded"),
            ("failed", "failed"),
            ("cancelled", "cancelled"),
        ],
        default="queued",
    )
    idempotency_key = models.CharField(max_length=200, unique=True)
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    error = models.TextField(blank=True)
    receipt = models.JSONField(default=dict, blank=True)
    destination = models.JSONField(default=dict, blank=True)


class PublishStep(Scoped):
    job = models.ForeignKey("integrations.PublishJob", on_delete=models.PROTECT, related_name="+")
    sequence = models.PositiveIntegerField()
    operation = models.CharField(max_length=200, default="", blank=True)
    status = models.CharField(
        max_length=40,
        choices=[
            ("pending", "pending"),
            ("running", "running"),
            ("succeeded", "succeeded"),
            ("uncertain", "uncertain"),
            ("failed", "failed"),
        ],
        default="pending",
    )
    fingerprint = models.CharField(max_length=200, default="", blank=True)
    response = models.JSONField(default=dict, blank=True)
    external_id = models.CharField(max_length=200, default="", blank=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["job", "operation"], name="publish_operation"),
        ]
