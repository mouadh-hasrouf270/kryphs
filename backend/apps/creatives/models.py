from django.db import models

from apps.common.models import Scoped


class Creative(Scoped):
    code = models.CharField(max_length=40, unique=True)
    title = models.CharField(max_length=200, default="", blank=True)
    description = models.TextField(blank=True)
    request = models.ForeignKey(
        "requests_app.CreativeRequest",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    deliverable = models.ForeignKey(
        "requests_app.RequestDeliverable",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    campaign = models.ForeignKey(
        "catalog.Campaign", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
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
    owner = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
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
    current_version = models.ForeignKey(
        "creatives.CreativeVersion",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    approved_version = models.ForeignKey(
        "creatives.CreativeVersion",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    outcome = models.CharField(max_length=200, default="", blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField("catalog.Tag", blank=True)

    def __str__(self):
        return self.title


class CreativeVersion(Scoped):
    creative = models.ForeignKey(
        "creatives.Creative", on_delete=models.PROTECT, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    label = models.CharField(max_length=200, default="", blank=True)
    version_type = models.CharField(
        max_length=40,
        choices=[("original", "original"), ("revision", "revision"), ("refresh", "refresh")],
        default="original",
    )
    editor = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=40,
        choices=[
            ("draft", "draft"),
            ("submitted", "submitted"),
            ("changes_requested", "changes_requested"),
            ("approved", "approved"),
            ("published", "published"),
        ],
        default="draft",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["creative", "version_number"], name="creative_version_number"
            ),
        ]


class CreativeComment(Scoped):
    creative = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    version = models.ForeignKey(
        "creatives.CreativeVersion",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    author = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    text = models.TextField(blank=True)


class CreativeFeedback(Scoped):
    version = models.ForeignKey(
        "creatives.CreativeVersion", on_delete=models.PROTECT, related_name="+"
    )
    author = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    text = models.TextField(blank=True)
    category = models.CharField(max_length=200, default="", blank=True)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)


class CreativeRelationship(Scoped):
    parent = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    child = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    relationship = models.CharField(
        max_length=40,
        choices=[
            ("variant", "variant"),
            ("refresh", "refresh"),
            ("remake", "remake"),
            ("derivative", "derivative"),
            ("localization", "localization"),
        ],
        default="variant",
    )
    hypothesis = models.TextField(blank=True)
    what_changed = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    author = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "child", "relationship"], name="creative_relationship"
            ),
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("child")), name="no_self_lineage"
            ),
        ]
