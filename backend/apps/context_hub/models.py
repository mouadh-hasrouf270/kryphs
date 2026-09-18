from django.db import models

from apps.common.models import Scoped


class ContextDocument(Scoped):
    title = models.CharField(max_length=200, default="", blank=True)
    category = models.CharField(
        max_length=40,
        choices=[
            ("guidelines", "guidelines"),
            ("facts", "facts"),
            ("allowed_claims", "allowed_claims"),
            ("forbidden_claims", "forbidden_claims"),
            ("audience", "audience"),
            ("tone", "tone"),
            ("platform", "platform"),
            ("campaign", "campaign"),
        ],
        default="guidelines",
    )
    current_version = models.ForeignKey(
        "context_hub.ContextDocumentVersion",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class ContextDocumentVersion(Scoped):
    document = models.ForeignKey(
        "context_hub.ContextDocument", on_delete=models.PROTECT, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    content = models.TextField(blank=True)
    status = models.CharField(
        max_length=40,
        choices=[("draft", "draft"), ("approved", "approved"), ("archived", "archived")],
        default="draft",
    )
    author = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "version_number"], name="context_version"),
        ]


class ContextCreativeLink(Scoped):
    document_version = models.ForeignKey(
        "context_hub.ContextDocumentVersion", on_delete=models.PROTECT, related_name="+"
    )
    creative = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(blank=True)


class CreativeProposal(Scoped):
    title = models.CharField(max_length=200, default="", blank=True)
    proposed_change = models.TextField(blank=True)
    rationale = models.TextField(blank=True)
    source = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(
        max_length=40,
        choices=[("proposed", "proposed"), ("accepted", "accepted"), ("rejected", "rejected")],
        default="proposed",
    )
    resulting_creative = models.ForeignKey(
        "creatives.Creative", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )

    def __str__(self):
        return self.title
