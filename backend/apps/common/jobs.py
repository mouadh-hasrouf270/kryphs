import logging
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.common.models import Job

logger = logging.getLogger(__name__)


def enqueue(kind, obj, actor, payload, key=None):
    return Job.objects.get_or_create(
        idempotency_key=key or str(uuid.uuid4()),
        defaults={
            "workspace": obj.workspace,
            "brand": getattr(obj, "brand", None),
            "type": kind,
            "payload": payload,
            "created_by": actor,
        },
    )[0]


@transaction.atomic
def claim():
    now = timezone.now()
    Job.objects.filter(status="running", heartbeat_at__lt=now - timedelta(minutes=10)).update(
        status="queued", available_at=now, last_error="Recovered a stale worker lease."
    )
    job = (
        Job.objects.filter(status="queued", available_at__lte=now)
        .order_by("-priority", "created_at")
        .first()
    )
    if not job:
        return None
    changed = Job.objects.filter(pk=job.pk, status="queued").update(
        status="running", claimed_at=now, heartbeat_at=now, attempts=job.attempts + 1
    )
    if not changed:
        return None
    job.refresh_from_db()
    return job


def heartbeat(job):
    Job.objects.filter(pk=job.pk, status="running").update(heartbeat_at=timezone.now())


def handle(job):
    if job.type == "automation":
        from apps.automations.services import execute

        execute(job)
    elif job.type == "publish":
        from apps.integrations.models import PublishJob
        from apps.integrations.services import execute

        execute(PublishJob.objects.get(pk=job.payload["publish_job"], workspace=job.workspace))
    elif job.type == "google_upload":
        from apps.storage.google import resume
        from apps.storage.models import Upload

        resume(
            Upload.objects.select_related("connection", "storage_object", "version__creative").get(
                pk=job.payload["upload"], workspace=job.workspace
            ),
            lambda: heartbeat(job),
        )
    elif job.type == "performance_sync":
        from apps.integrations.models import AdConnection
        from apps.performance.providers import sync

        sync(AdConnection.objects.get(pk=job.payload["connection"], workspace=job.workspace))
    elif job.type in ["drive_sync", "drive_test", "drive_organize"]:
        from apps.storage.google import organize, sync, token
        from apps.storage.models import StorageConnection

        connection = StorageConnection.objects.get(
            pk=job.payload["connection"], workspace=job.workspace
        )
        if job.type == "drive_test":
            token(connection)
        else:
            {"drive_sync": sync, "drive_organize": organize}[job.type](
                connection, lambda: heartbeat(job)
            )
    else:
        raise ValueError("Unregistered job handler")


def run_once():
    job = claim()
    if not job:
        return False
    logger.info("job_started id=%s type=%s attempt=%s", job.pk, job.type, job.attempts)
    try:
        handle(job)
    except Exception as exc:
        # Never persist provider exception payloads: they may contain credentials.
        job.last_error = (
            "Operation failed. Check provider configuration and the domain operation record."
        )
        job.status = (
            "failed" if job.attempts >= job.max_attempts or job.type == "publish" else "queued"
        )
        if job.type == "google_upload":
            from apps.storage.google import ProviderFailure
            from apps.storage.models import Upload

            upload = Upload.objects.filter(
                pk=job.payload.get("upload"), workspace=job.workspace
            ).first()
            if upload:
                upload.last_error = str(exc) if isinstance(exc, ProviderFailure) else job.last_error
                if upload.status == "initializing" and not upload.session_encrypted:
                    job.status = "failed"
                elif job.status == "failed":
                    upload.status = "failed"
                upload.save(update_fields=["last_error", "status"])
        job.available_at = timezone.now() + timedelta(seconds=min(3600, 2**job.attempts * 15))
        if job.status == "failed":
            job.failed_at = timezone.now()
        logger.warning("job_failed id=%s type=%s", job.pk, job.type)
    else:
        job.status = "succeeded"
        job.completed_at = timezone.now()
        job.last_error = ""
    job.save()
    return True
