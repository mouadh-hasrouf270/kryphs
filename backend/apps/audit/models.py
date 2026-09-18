from django.db import models

from apps.common.models import Scoped


class AuditEvent(Scoped):
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    action = models.CharField(max_length=200, default="", blank=True)
    object_type = models.CharField(max_length=200, default="", blank=True)
    object_id = models.CharField(max_length=200, default="", blank=True)
    summary = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=500, default="", blank=True)
    correlation_id = models.CharField(max_length=200, default="", blank=True)


class Activity(Scoped):
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    action = models.CharField(max_length=200, default="", blank=True)
    object_type = models.CharField(max_length=200, default="", blank=True)
    object_id = models.CharField(max_length=200, default="", blank=True)
    title = models.CharField(max_length=200, default="", blank=True)

    def __str__(self):
        return self.title
