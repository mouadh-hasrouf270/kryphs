from django.db import models

from apps.common.models import Scoped


class CreativeRequest(Scoped):
    code = models.CharField(max_length=40, unique=True)
    title = models.CharField(max_length=200, default="", blank=True)
    objective = models.TextField(blank=True)
    details = models.TextField(blank=True)
    priority = models.CharField(
        max_length=40,
        choices=[("normal", "normal"), ("high", "high"), ("urgent", "urgent"), ("low", "low")],
        default="normal",
    )
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=40,
        choices=[
            ("new", "new"),
            ("assigned", "assigned"),
            ("in_production", "in_production"),
            ("ready_for_review", "ready_for_review"),
            ("changes_requested", "changes_requested"),
            ("approved", "approved"),
            ("published", "published"),
            ("refresh_requested", "refresh_requested"),
        ],
        default="new",
    )
    requester = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    owner = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    campaign = models.ForeignKey(
        "catalog.Campaign", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    platforms = models.ManyToManyField("catalog.Platform", blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class RequestDeliverable(Scoped):
    request = models.ForeignKey(
        "requests_app.CreativeRequest", on_delete=models.PROTECT, related_name="deliverables"
    )
    sequence = models.PositiveIntegerField()
    title = models.CharField(max_length=200, default="", blank=True)
    creative_type = models.CharField(
        max_length=40,
        choices=[
            ("video", "video"),
            ("image", "image"),
            ("audio", "audio"),
            ("document", "document"),
        ],
        default="video",
    )
    platform = models.ForeignKey(
        "catalog.Platform", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    aspect_ratio = models.CharField(max_length=200, default="9:16", blank=True)
    quantity = models.PositiveIntegerField(default=1)
    duration_target = models.PositiveIntegerField(default=0)
    requirements = models.TextField(blank=True)
    assigned_editor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=40,
        choices=[
            ("new", "new"),
            ("assigned", "assigned"),
            ("in_production", "in_production"),
            ("ready_for_review", "ready_for_review"),
            ("changes_requested", "changes_requested"),
            ("approved", "approved"),
            ("published", "published"),
            ("refresh_requested", "refresh_requested"),
        ],
        default="new",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["request", "sequence"], name="deliverable_sequence"),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="positive_quantity"),
        ]

    def __str__(self):
        return self.title


class RequestSourceMaterial(Scoped):
    request = models.ForeignKey(
        "requests_app.CreativeRequest", on_delete=models.PROTECT, related_name="+"
    )
    title = models.CharField(max_length=200, default="", blank=True)
    kind = models.CharField(
        max_length=40,
        choices=[("note", "note"), ("link", "link"), ("file", "file"), ("drive", "drive")],
        default="note",
    )
    url = models.URLField(blank=True)
    note = models.TextField(blank=True)
    storage_object = models.ForeignKey(
        "storage.StorageObject", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )

    def __str__(self):
        return self.title


class SourceMaterialUsage(Scoped):
    source = models.ForeignKey(
        "requests_app.RequestSourceMaterial", on_delete=models.PROTECT, related_name="+"
    )
    version = models.ForeignKey(
        "creatives.CreativeVersion", on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source", "version"], name="source_usage"),
        ]
