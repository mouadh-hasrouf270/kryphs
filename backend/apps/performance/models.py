from django.db import models

from apps.common.models import Scoped


class Deployment(Scoped):
    title = models.CharField(max_length=200, default="", blank=True)
    creative = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    version = models.ForeignKey(
        "creatives.CreativeVersion", on_delete=models.PROTECT, related_name="+"
    )
    provider = models.CharField(
        max_length=40,
        choices=[
            ("manual", "manual"),
            ("meta", "meta"),
            ("tiktok", "tiktok"),
            ("youtube", "youtube"),
            ("google_ads", "google_ads"),
            ("snapchat", "snapchat"),
            ("pinterest", "pinterest"),
            ("linkedin", "linkedin"),
            ("other", "other"),
        ],
        default="manual",
    )
    connection = models.ForeignKey(
        "integrations.AdConnection",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    external_account_id = models.CharField(max_length=200, default="", blank=True)
    campaign_id = models.CharField(max_length=200, default="", blank=True)
    adset_id = models.CharField(max_length=200, default="", blank=True)
    ad_id = models.CharField(max_length=200, default="", blank=True)
    destination_url = models.URLField(blank=True)
    utm = models.JSONField(default=dict, blank=True)
    state = models.CharField(
        max_length=40,
        choices=[
            ("draft", "draft"),
            ("paused", "paused"),
            ("active", "active"),
            ("archived", "archived"),
        ],
        default="draft",
    )
    deployed_at = models.DateTimeField(null=True, blank=True)
    last_sync = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class PerformanceSnapshot(Scoped):
    deployment = models.ForeignKey(
        "performance.Deployment", on_delete=models.PROTECT, related_name="+"
    )
    provider = models.CharField(max_length=200, default="manual", blank=True)
    interval_start = models.DateTimeField()
    interval_end = models.DateTimeField()
    spend = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    impressions = models.PositiveIntegerField(default=0)
    reach = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    link_clicks = models.PositiveIntegerField(default=0)
    conversions = models.PositiveIntegerField(default=0)
    purchases = models.PositiveIntegerField(default=0)
    revenue = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    video_views = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD", blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["deployment", "interval_start", "interval_end"], name="performance_window"
            ),
            models.CheckConstraint(
                condition=models.Q(interval_end__gt=models.F("interval_start")),
                name="performance_interval",
            ),
        ]


class OutcomeHistory(Scoped):
    creative = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    outcome = models.CharField(
        max_length=40,
        choices=[
            ("winner", "winner"),
            ("loser", "loser"),
            ("neutral", "neutral"),
            ("fatigued", "fatigued"),
            ("refresh_requested", "refresh_requested"),
        ],
        default="winner",
    )
    reason = models.TextField(blank=True)
    actor = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    snapshot = models.ForeignKey(
        "performance.PerformanceSnapshot",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
