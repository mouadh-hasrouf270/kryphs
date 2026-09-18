from django.db import models

from apps.common.models import Scoped


class StorageConnection(Scoped):
    name = models.CharField(max_length=200, default="", blank=True)
    provider = models.CharField(
        max_length=40,
        choices=[("google_drive", "google_drive"), ("local", "local")],
        default="google_drive",
    )
    account_email = models.EmailField(blank=True)
    root_folder_id = models.CharField(max_length=200, default="", blank=True)
    shared_drive_id = models.CharField(max_length=200, default="", blank=True)
    credentials_encrypted = models.TextField(blank=True)
    scopes = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=40,
        choices=[("disconnected", "disconnected"), ("connected", "connected"), ("error", "error")],
        default="disconnected",
    )
    last_sync = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    change_token = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")

    def __str__(self):
        return self.name


class StorageObject(Scoped):
    connection = models.ForeignKey(
        "storage.StorageConnection",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    provider = models.CharField(
        max_length=40,
        choices=[("local", "local"), ("google_drive", "google_drive")],
        default="local",
    )
    external_id = models.CharField(max_length=200, default="", blank=True)
    filename = models.CharField(max_length=200, default="", blank=True)
    mime_type = models.CharField(max_length=200, default="", blank=True)
    size = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=200, default="", blank=True)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    duration = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    local_path = models.CharField(max_length=500, default="", blank=True)
    parents = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "external_id"], name="storage_external_identity"
            ),
        ]


class DriveFolderMapping(Scoped):
    connection = models.ForeignKey(
        "storage.StorageConnection", on_delete=models.PROTECT, related_name="+"
    )
    entity_type = models.CharField(max_length=200, default="", blank=True)
    entity_id = models.UUIDField()
    folder_role = models.CharField(max_length=200, default="", blank=True)
    drive_folder_id = models.CharField(max_length=200, default="", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "entity_type", "entity_id", "folder_role"],
                name="drive_folder_identity",
            ),
        ]


class CreativeFile(Scoped):
    creative = models.ForeignKey("creatives.Creative", on_delete=models.PROTECT, related_name="+")
    version = models.ForeignKey(
        "creatives.CreativeVersion",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    storage_object = models.ForeignKey(
        "storage.StorageObject", on_delete=models.PROTECT, related_name="+"
    )
    role = models.CharField(
        max_length=40,
        choices=[
            ("master", "master"),
            ("source", "source"),
            ("thumbnail", "thumbnail"),
            ("subtitle", "subtitle"),
            ("export", "export"),
            ("reference", "reference"),
            ("attachment", "attachment"),
        ],
        default="master",
    )
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "storage_object", "role"], name="creative_file_identity"
            ),
        ]


class Upload(Scoped):
    connection = models.ForeignKey(
        "storage.StorageConnection", on_delete=models.PROTECT, related_name="+"
    )
    version = models.ForeignKey(
        "creatives.CreativeVersion", on_delete=models.PROTECT, related_name="+"
    )
    storage_object = models.ForeignKey(
        "storage.StorageObject", on_delete=models.PROTECT, related_name="+"
    )
    role = models.CharField(
        max_length=40,
        choices=[
            ("master", "master"),
            ("source", "source"),
            ("thumbnail", "thumbnail"),
            ("subtitle", "subtitle"),
            ("export", "export"),
            ("reference", "reference"),
            ("attachment", "attachment"),
        ],
        default="master",
    )
    provider = models.CharField(
        max_length=40,
        choices=[("google_drive", "google_drive"), ("youtube", "youtube")],
        default="google_drive",
    )
    status = models.CharField(
        max_length=40,
        choices=[
            ("queued", "queued"),
            ("initializing", "initializing"),
            ("uploading", "uploading"),
            ("verifying", "verifying"),
            ("complete", "complete"),
            ("failed", "failed"),
            ("cancelled", "cancelled"),
        ],
        default="queued",
    )
    idempotency_key = models.CharField(max_length=200, unique=True)
    session_encrypted = models.TextField(blank=True)
    total_bytes = models.PositiveBigIntegerField(default=0)
    uploaded_bytes = models.PositiveBigIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    external_id = models.CharField(max_length=200, default="", blank=True)
    privacy = models.CharField(
        max_length=40,
        choices=[("private", "private"), ("unlisted", "unlisted"), ("public", "public")],
        default="private",
    )
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")


class SyncRun(Scoped):
    connection = models.ForeignKey(
        "storage.StorageConnection", on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(max_length=200, default="running", blank=True)
    object_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class Clip(Scoped):
    source = models.ForeignKey("storage.StorageObject", on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200, default="", blank=True)
    start = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    end = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    description = models.TextField(blank=True)
    transcript = models.TextField(blank=True)
    tags = models.ManyToManyField("catalog.Tag", blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end__gt=models.F("start")) & models.Q(start__gte=0),
                name="clip_interval",
            ),
        ]

    def __str__(self):
        return self.title


class ClipUsage(Scoped):
    clip = models.ForeignKey("storage.Clip", on_delete=models.PROTECT, related_name="+")
    version = models.ForeignKey(
        "creatives.CreativeVersion", on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["clip", "version"], name="clip_usage"),
        ]


class ContentIndexEntry(Scoped):
    source = models.ForeignKey("storage.StorageObject", on_delete=models.PROTECT, related_name="+")
    version = models.ForeignKey(
        "creatives.CreativeVersion",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    kind = models.CharField(
        max_length=40,
        choices=[("transcript", "transcript"), ("ocr", "ocr"), ("note", "note")],
        default="transcript",
    )
    machine_text = models.TextField(blank=True)
    corrected_text = models.TextField(blank=True)
    language = models.CharField(max_length=200, default="ar", blank=True)
