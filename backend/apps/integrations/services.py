"""Publishing uses a durable write-ahead step ledger; ambiguous writes never auto-retry."""

import hashlib
import ipaddress
import json
import re
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.integrations.crypto import unseal
from apps.integrations.models import AdConnection, PublishJob, PublishStep
from apps.storage.google import ProviderFailure
from apps.storage.services import local_path, master
from apps.workspaces.policies import require, scope


def destination_url(value):
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationError(
            "Destination must be a public HTTPS URL without embedded credentials."
        )
    if (
        parsed.hostname.lower() in ["localhost", "localhost.localdomain"]
        or "." not in parsed.hostname
    ):
        raise ValidationError("Destination must use a public host.")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_global:
            raise ValidationError("Private destination addresses are not allowed.")
    except ValueError:
        pass
    return value


@transaction.atomic
def enqueue_publish(actor, creative, data):
    from django.conf import settings

    if not settings.META_PUBLISH_ENABLED:
        raise ValidationError(
            "Meta publishing is beta and disabled until live acceptance is completed."
        )
    require(actor, creative.workspace_id, "publish_ads")
    version = creative.approved_version
    if not version:
        raise ValidationError("Approve a creative version first.")
    asset = master(version)
    connection = (
        scope(AdConnection.objects.all(), actor, creative.workspace_id)
        .filter(pk=data.get("connection"), brand=creative.brand)
        .first()
    )
    if not connection or connection.status != "connected":
        raise ValidationError("Select a connected ad account.")
    if connection.provider != "meta":
        raise ValidationError("Publishing is not supported for this provider.")
    if asset.provider != "local" or not asset.mime_type.startswith("video/"):
        raise ValidationError(
            "Meta publishing currently requires a locally available video master."
        )
    destination = data.get("destination", {})
    destination_url(destination.get("destination_url", ""))
    for key in ["adset_id", "page_id"]:
        if not re.fullmatch(r"[0-9]+", str(destination.get(key, ""))):
            raise ValidationError(f"{key} must be a numeric provider ID.")
    key = str(data.get("idempotency_key", ""))[:200]
    if not key:
        raise ValidationError("An idempotency key is required.")
    job, created = PublishJob.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "workspace": creative.workspace,
            "brand": creative.brand,
            "creative": creative,
            "version": version,
            "connection": connection,
            "provider": "meta",
            "requested_by": actor,
            "destination": destination,
        },
    )
    if (
        job.version_id != version.pk
        or job.connection_id != connection.pk
        or job.destination != destination
    ):
        raise ValidationError("Idempotency key belongs to a different publication.")
    if created:
        from apps.common.jobs import enqueue

        enqueue("publish", job, actor, {"publish_job": str(job.pk)}, key="publish:" + key)
        record(actor, job, "publish_queued")
    return job


class MetaPublishingProvider:
    def step(self, job, operation, sequence, endpoint, body, headers, file=None):
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with transaction.atomic():
            step, created = PublishStep.objects.get_or_create(
                job=job,
                operation=operation,
                defaults={
                    "workspace": job.workspace,
                    "brand": job.brand,
                    "sequence": sequence,
                    "fingerprint": fingerprint,
                },
            )
            if step.status == "succeeded":
                return step.external_id
            if step.status in ["running", "uncertain"]:
                raise ProviderFailure(
                    "A provider write has an uncertain result. Reconcile it before retrying to prevent duplicate ads."
                )
            step.status = "running"
            step.attempts += 1
            step.save()
        try:
            kwargs = {
                "headers": headers,
                "data": body,
                "timeout": settings.PROVIDER_TIMEOUT,
                "follow_redirects": False,
            }
            if file:
                with local_path(file).open("rb") as stream:
                    response = httpx.post(
                        endpoint,
                        files={"source": (file.filename, stream, file.mime_type)},
                        **kwargs,
                    )
            else:
                response = httpx.post(endpoint, **kwargs)
            if response.status_code >= 400:
                raise ProviderFailure(
                    f"Meta returned HTTP {response.status_code}; reconcile before retry."
                )
            identity = response.json().get("id")
            if not re.fullmatch(r"[0-9]+", str(identity or "")):
                raise ProviderFailure("Meta returned no confirmed object ID.")
        except (httpx.HTTPError, ValueError, ProviderFailure):
            step.status = "uncertain"
            step.save(update_fields=["status"])
            raise ProviderFailure(
                "Meta publication did not produce a confirmed receipt. Reconcile the account before retrying."
            ) from None
        step.external_id = str(identity)
        step.status = "succeeded"
        step.response = {"id": str(identity)}
        step.save()
        return str(identity)

    def publish(self, job):
        credentials = unseal(job.connection.credentials_encrypted)
        api = credentials.get("api_version", "")
        account = job.connection.account_id
        if not re.fullmatch(r"v\d+\.\d+", api) or not re.fullmatch(r"\d+", account):
            raise ProviderFailure("Configure a supported Meta API version and numeric account ID.")
        if not credentials.get("access_token"):
            raise ProviderFailure("Meta credentials are missing.")
        asset = master(job.version)
        if asset.provider != "local":
            raise ProviderFailure("A local master is required for Meta upload.")
        base = f"https://graph.facebook.com/{api}/act_{account}"
        headers = {"Authorization": "Bearer " + credentials["access_token"]}
        video = self.step(
            job, "asset.upload", 1, base + "/advideos", {"name": job.creative.title}, headers, asset
        )
        dest = job.destination
        story = {
            "page_id": dest["page_id"],
            "video_data": {
                "video_id": video,
                "message": dest.get("message", job.creative.title),
                "call_to_action": {
                    "type": "LEARN_MORE",
                    "value": {"link": destination_url(dest["destination_url"])},
                },
            },
        }
        creative = self.step(
            job,
            "creative.create",
            2,
            base + "/adcreatives",
            {"name": job.creative.title, "object_story_spec": json.dumps(story)},
            headers,
        )
        ad = self.step(
            job,
            "ad.create",
            3,
            base + "/ads",
            {
                "name": job.creative.title,
                "adset_id": dest["adset_id"],
                "creative": json.dumps({"creative_id": creative}),
                "status": "PAUSED",
            },
            headers,
        )
        return {"ad_id": ad, "creative_id": creative, "video_id": video}


PRODUCTION_PROVIDERS = {"meta": MetaPublishingProvider}


def provider(name):
    cls = PRODUCTION_PROVIDERS.get(name)
    if not cls:
        raise ProviderFailure("Publishing is not supported/configured for this provider.")
    return cls()


def execute(job):
    if job.state == "succeeded":
        return
    job.state = "running"
    job.save(update_fields=["state"])
    try:
        receipt = provider(job.provider).publish(job)
        if not receipt.get("ad_id"):
            raise ProviderFailure("Provider returned no confirmed publication.")
        with transaction.atomic():
            from apps.performance.models import Deployment

            Deployment.objects.get_or_create(
                workspace=job.workspace,
                brand=job.brand,
                provider=job.provider,
                ad_id=receipt["ad_id"],
                defaults={
                    "creative": job.creative,
                    "version": job.version,
                    "connection": job.connection,
                    "title": job.creative.title,
                    "state": "paused",
                    "deployed_at": timezone.now(),
                    "destination_url": job.destination["destination_url"],
                },
            )
            job.state = "succeeded"
            job.receipt = receipt
            job.error = ""
            job.save()
            from apps.creatives.services import confirmed_publication

            confirmed_publication(job.requested_by, job.version)
            record(job.requested_by, job, "publish_complete", {"ad_id": receipt["ad_id"]})
    except Exception:
        job.state = "failed"
        job.error = (
            "Publication failed. Inspect the step ledger and reconcile uncertain provider writes."
        )
        job.save()
        record(job.requested_by, job, "publish_failed")
        raise
