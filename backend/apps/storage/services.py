import hashlib
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.creatives.models import CreativeVersion
from apps.creatives.services import editor_access
from apps.storage.models import CreativeFile, StorageObject, Upload
from apps.workspaces.policies import require, scope, validate_scope


def local_path(obj):
    root = settings.MEDIA_ROOT.resolve()
    path = (root / obj.local_path).resolve()
    if not path.is_relative_to(root):
        raise ValidationError("Invalid storage path.")
    return path


def detect(file):
    head = file.read(512)
    file.seek(0)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:6] in [b"GIF87a", b"GIF89a"]:
        return "image/gif"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp":
        return "video/mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"ID3") or head[:2] in [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"]:
        return "audio/mpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    raise ValidationError(
        "Unsupported file signature. Use PNG, JPEG, GIF, WebP, MP4, WebM, MP3, WAV or PDF."
    )


def upload_local(actor, creative, file, role):
    editor_access(actor, creative)
    if not file or file.size <= 0 or file.size > settings.MAX_UPLOAD_BYTES:
        raise ValidationError("File is empty or exceeds the upload limit.")
    version = creative.current_version
    if not version or version.status != "draft":
        raise ValidationError("Create a draft version before attaching files.")
    if role not in dict(CreativeFile._meta.get_field("role").choices):
        raise ValidationError("Invalid file role.")
    mime = detect(file)
    width = height = 0
    if mime.startswith("image/"):
        try:
            img = Image.open(file)
            width, height = img.size
            img.verify()
            file.seek(0)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValidationError("Invalid image.") from None
    filename = re.sub(r"[^\w.\- ()]", "_", Path(file.name).name)[:180]
    relative = f"{creative.workspace_id}/{uuid.uuid4().hex}"
    path = settings.MEDIA_ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256()
    size = 0
    try:
        with path.open("xb") as out:
            for chunk in file.chunks():
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES:
                    raise ValidationError("Upload limit exceeded.")
                checksum.update(chunk)
                out.write(chunk)
        with transaction.atomic():
            version.refresh_from_db()
            if version.status != "draft":
                raise ValidationError("The version is no longer a draft.")
            if (
                role == "master"
                and CreativeFile.objects.filter(
                    version=version, role="master", active=True
                ).exists()
            ):
                raise ValidationError(
                    "A master already exists. Create another version to replace it."
                )
            obj = StorageObject.objects.create(
                workspace=creative.workspace,
                brand=creative.brand,
                provider="local",
                external_id=uuid.uuid4().hex,
                filename=filename,
                mime_type=mime,
                size=size,
                checksum=checksum.hexdigest(),
                width=width,
                height=height,
                local_path=relative,
            )
            CreativeFile.objects.create(
                workspace=creative.workspace,
                brand=creative.brand,
                creative=creative,
                version=version,
                storage_object=obj,
                role=role,
            )
            record(actor, creative, "upload_complete", {"file_id": str(obj.pk)})
        return obj
    except Exception:
        path.unlink(missing_ok=True)
        raise


def master(version):
    if version.status not in ["approved", "published"]:
        raise ValidationError("Publishing requires an approved version.")
    files = list(
        CreativeFile.objects.filter(
            version=version, role="master", active=True, storage_object__active=True
        ).select_related("storage_object")[:2]
    )
    if len(files) != 1:
        raise ValidationError("Exactly one active approved master asset is required.")
    return files[0].storage_object


@transaction.atomic
def enqueue_transfer(actor, connection, data):
    require(actor, connection.workspace_id, "submit_version")
    validate_scope(actor, connection.workspace_id, connection.brand)
    version = (
        scope(CreativeVersion.objects.all(), actor, connection.workspace_id)
        .filter(pk=data.get("version"), brand=connection.brand)
        .first()
    )
    if not version:
        raise ValidationError("Version unavailable.")
    provider = data.get("provider", "google_drive")
    if provider not in ["google_drive", "youtube"]:
        raise ValidationError({"provider": "Unsupported upload provider."})
    if provider == "youtube":
        from django.conf import settings

        if (
            not settings.YOUTUBE_PUBLISH_ENABLED
            or "https://www.googleapis.com/auth/youtube.upload" not in connection.scopes
        ):
            raise ValidationError(
                "YouTube publishing is not configured and accepted for this connection."
            )
        require(actor, connection.workspace_id, "publish_ads")
        obj = master(version)
    else:
        editor_access(actor, version.creative)
        files = CreativeFile.objects.filter(
            version=version, role="master", active=True
        ).select_related("storage_object")
        if files.count() != 1:
            raise ValidationError("Attach exactly one local master first.")
        obj = files.first().storage_object
    if obj.provider != "local":
        raise ValidationError("This upload requires a local master asset.")
    if connection.provider != "google_drive" or connection.status != "connected":
        raise ValidationError("Connect Google first.")
    privacy = data.get("privacy", "private")
    if privacy not in ["private", "unlisted", "public"]:
        raise ValidationError("Invalid privacy setting.")
    key = str(data.get("idempotency_key", ""))[:200]
    if not key:
        raise ValidationError("An idempotency key is required.")
    upload, created = Upload.objects.get_or_create(
        idempotency_key=key,
        defaults=dict(
            workspace=connection.workspace,
            brand=version.brand,
            connection=connection,
            version=version,
            storage_object=obj,
            provider=provider,
            total_bytes=obj.size,
            created_by=actor,
            privacy=privacy,
        ),
    )
    if (
        upload.version_id != version.pk
        or upload.connection_id != connection.pk
        or upload.provider != provider
    ):
        raise ValidationError("Idempotency key belongs to another upload.")
    if created:
        from apps.common.jobs import enqueue

        enqueue("google_upload", upload, actor, {"upload": str(upload.pk)}, key="upload:" + key)
        record(actor, upload, "upload_queued")
    return upload
