from django.db import models

from apps.common.models import Record


class Workspace(Record):
    name = models.CharField(max_length=200, default="", blank=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    settings = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class WorkspaceMembership(Record):
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.PROTECT, related_name="+"
    )
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    role = models.CharField(
        max_length=40,
        choices=[
            ("manager", "manager"),
            ("media_buyer", "media_buyer"),
            ("editor", "editor"),
            ("reviewer", "reviewer"),
            ("requester", "requester"),
            ("viewer", "viewer"),
        ],
        default="manager",
    )
    active = models.BooleanField(default=True)
    brand_restricted = models.BooleanField(default=False)
    brands = models.ManyToManyField("catalog.Brand", blank=True)
    permission_overrides = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "user"], name="workspace_member"),
        ]
