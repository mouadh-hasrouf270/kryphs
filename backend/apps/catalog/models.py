from django.db import models

from apps.common.models import Record, Scoped


class Brand(Record):
    workspace = models.ForeignKey(
        "workspaces.Workspace", on_delete=models.PROTECT, related_name="+"
    )
    name = models.CharField(max_length=200, default="", blank=True)
    slug = models.SlugField()
    logo = models.URLField(blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace", "slug"], name="brand_slug"),
        ]

    def __str__(self):
        return self.name


class Product(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class Campaign(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class Project(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class Tag(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class Taxonomy(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class NamingTemplate(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class Platform(Record):
    name = models.CharField(max_length=200, default="", blank=True)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class AttributeValue(Scoped):
    taxonomy = models.ForeignKey("catalog.Taxonomy", on_delete=models.PROTECT, related_name="+")
    creative = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    value = models.CharField(max_length=200, default="", blank=True)
