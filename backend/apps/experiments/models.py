from django.db import models

from apps.common.models import Scoped


class Experiment(Scoped):
    title = models.CharField(max_length=200, default="", blank=True)
    hypothesis = models.TextField(blank=True)
    primary_kpi = models.CharField(
        max_length=40,
        choices=[("ctr", "ctr"), ("roas", "roas"), ("cpa", "cpa"), ("conversions", "conversions")],
        default="ctr",
    )
    secondary_kpi = models.CharField(max_length=200, default="", blank=True)
    status = models.CharField(
        max_length=40,
        choices=[
            ("draft", "draft"),
            ("running", "running"),
            ("completed", "completed"),
            ("cancelled", "cancelled"),
        ],
        default="draft",
    )
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    conclusion = models.TextField(blank=True)
    learning = models.TextField(blank=True)
    next_action = models.TextField(blank=True)
    winner = models.ForeignKey(
        "experiments.ExperimentArm",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    limitations = models.TextField(blank=True)

    def __str__(self):
        return self.title


class ExperimentArm(Scoped):
    experiment = models.ForeignKey(
        "experiments.Experiment", on_delete=models.PROTECT, related_name="arms"
    )
    name = models.CharField(max_length=200, default="", blank=True)
    control = models.BooleanField(default=False)
    creative = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    version = models.ForeignKey(
        "creatives.CreativeVersion",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    deployment = models.ForeignKey(
        "performance.Deployment", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["experiment", "creative"], name="experiment_creative"),
        ]

    def __str__(self):
        return self.name
