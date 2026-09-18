from django.db import models

from apps.common.models import Scoped


class Notification(Scoped):
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=200, default="", blank=True)
    title = models.CharField(max_length=200, default="", blank=True)
    link = models.CharField(max_length=500, default="", blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.title
