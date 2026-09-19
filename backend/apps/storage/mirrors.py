"""Queue provider replicas after local commit. No provider I/O lives here."""

import logging
import time

from django.db import OperationalError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.common.jobs import enqueue
from apps.storage.models import StorageConnection, Upload

logger = logging.getLogger(__name__)


def automatic_connection(file):
    matches = list(
        StorageConnection.objects.filter(
            workspace_id=file.workspace_id,
            brand_id=file.brand_id,
            provider="google_drive",
            status="connected",
        ).order_by("pk")
    )
    preferred = [connection for connection in matches if connection.auto_upload_default]
    if len(preferred) == 1:
        return preferred[0], ""
    if len(matches) == 1:
        return matches[0], ""
    return None, "drive_destination_ambiguous" if matches else "drive_not_connected"


def enqueue_drive_mirror(actor, file, connection=None, retry=False):
    for attempt in range(6):
        try:
            return _enqueue_drive_mirror(actor, file, connection, retry)
        except OperationalError as exc:
            if (
                "locked" not in str(exc).lower()
                or attempt == 5
                or transaction.get_connection().in_atomic_block
            ):
                raise
            time.sleep(0.025 * 2**attempt)


@transaction.atomic
def _enqueue_drive_mirror(actor, file, connection=None, retry=False):
    if connection is None:
        connection, reason = automatic_connection(file)
        if connection is None:
            return {"queued": False, "reason": reason}
    connection = StorageConnection.objects.select_for_update().get(pk=connection.pk)
    if (
        connection.workspace_id != file.workspace_id
        or connection.brand_id != file.brand_id
        or connection.provider != "google_drive"
        or connection.status != "connected"
    ):
        raise ValidationError("Drive destination does not match the file workspace and brand.")
    if not file.version_id or file.storage_object.provider != "local":
        raise ValidationError("Drive mirroring requires a versioned local asset.")
    key = f"drive-mirror:{connection.pk}:{file.storage_object_id}:{file.version_id}"
    # Adopt old manual transfers as well, retaining their IDs, sessions and receipts.
    candidates = Upload.objects.filter(
        connection=connection,
        version=file.version,
        storage_object=file.storage_object,
        provider="google_drive",
    )
    upload = (
        candidates.filter(status="complete").order_by("created_at", "pk").first()
        or candidates.order_by("created_at", "pk").first()
    )
    created = False
    if upload is None:
        upload, created = Upload.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "workspace": file.workspace,
                "brand": file.brand,
                "connection": connection,
                "version": file.version,
                "storage_object": file.storage_object,
                "provider": "google_drive",
                "role": file.role,
                "total_bytes": file.storage_object.size,
                "created_by": actor,
            },
        )
    if upload.status == "complete":
        return {"queued": False, "status": "complete", "upload_id": str(upload.pk)}
    job = enqueue(
        "google_upload",
        upload,
        actor,
        {"upload": str(upload.pk)},
        key="upload:" + upload.idempotency_key,
    )
    if retry and job.status == "failed":
        if upload.status == "initializing" and not upload.session_encrypted:
            raise ValidationError(
                "Upload initialization is uncertain. Reconcile with Google before retrying."
            )
        job.status, job.attempts, job.available_at = "queued", 0, timezone.now()
        job.save(update_fields=["status", "attempts", "available_at"])
    if created:
        record(
            actor,
            upload,
            "drive_upload_queued",
            {"source_storage_object_id": str(file.storage_object_id), "source_role": file.role},
        )
    return {
        "queued": job.status in ["queued", "running"],
        "status": upload.status,
        "upload_id": str(upload.pk),
        "reason": "drive_upload_failed" if job.status == "failed" else "",
    }


def mirror_after_commit(actor, file, asset):
    """A queue failure can never roll back or unlink a successfully saved local asset."""
    try:
        state = enqueue_drive_mirror(actor, file)
    except Exception:
        logger.warning("drive_queue_failed asset=%s", asset.pk)
        state = {"queued": False, "reason": "drive_queue_failed"}
    asset.drive_upload = state
    try:
        asset.metadata = {**asset.metadata, "drive_upload": state}
        asset.save(update_fields=["metadata"])
    except Exception:
        logger.warning("drive_queue_status_write_failed asset=%s", asset.pk)
