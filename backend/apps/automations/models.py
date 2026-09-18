from django.db import models

from apps.common.models import Scoped


class AutomationRule(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    enabled = models.BooleanField(default=True)
    event = models.CharField(
        max_length=40,
        choices=[
            ("ready_for_review", "ready_for_review"),
            ("approved", "approved"),
            ("fatigued", "fatigued"),
            ("overdue", "overdue"),
        ],
        default="ready_for_review",
    )
    conditions = models.JSONField(default=dict, blank=True)
    action = models.CharField(
        max_length=40,
        choices=[("notify", "notify"), ("refresh_recommendation", "refresh_recommendation")],
        default="notify",
    )
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")

    def __str__(self):
        return self.name


class AutomationRun(Scoped):
    rule = models.ForeignKey(
        "automations.AutomationRule", on_delete=models.PROTECT, related_name="+"
    )
    event_id = models.CharField(max_length=200, default="", blank=True)
    status = models.CharField(max_length=200, default="running", blank=True)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["rule", "event_id"], name="automation_once"),
        ]


class AutomationRunStep(Scoped):
    run = models.ForeignKey("automations.AutomationRun", on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=200, default="", blank=True)
    status = models.CharField(max_length=200, default="", blank=True)
    result = models.JSONField(default=dict, blank=True)
