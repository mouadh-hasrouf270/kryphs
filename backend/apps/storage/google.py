"""Google OAuth, durable Drive identities, incremental sync and resumable transport."""

import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode, urlparse

import httpx
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.integrations.crypto import seal, unseal
from apps.storage.models import (
    StorageConnection,
    StorageObject,
)
from apps.storage.services import local_path, master
from apps.workspaces.policies import require, validate_scope

DRIVE = "https://www.googleapis.com/drive/v3"


class ProviderFailure(Exception):
    pass


def request(method, url, **kwargs):
    accepted = kwargs.pop("accepted", [200, 201, 204, 308])
    try:
        response = httpx.request(
            method, url, timeout=settings.PROVIDER_TIMEOUT, follow_redirects=False, **kwargs
        )
    except httpx.HTTPError:
        raise ProviderFailure(
            "Google request failed or timed out; retry after checking connection."
        ) from None
    if response.status_code not in accepted:
        raise ProviderFailure(
            f"Google returned HTTP {response.status_code}; check authorization, quota and provider configuration."
        )
    return response


def begin_oauth(request_obj, connection, scope="file", youtube=False):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise ValidationError("Configure Google OAuth credentials on the server.")
    scopes = ["https://www.googleapis.com/auth/drive.file"]
    if scope == "full":
        scopes = ["https://www.googleapis.com/auth/drive"]
    elif scope != "file":
        raise ValidationError("Unknown scope choice.")
    if youtube:
        scopes.append("https://www.googleapis.com/auth/youtube.upload")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    request_obj.session["google_oauth"] = {
        "state": state,
        "verifier": verifier,
        "connection": str(connection.pk),
        "created": time.time(),
        "user": str(request_obj.user.pk),
        "scopes": scopes,
    }
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


@api_view(["GET"])
def callback(request_obj):
    flow = request_obj.session.pop("google_oauth", None)
    if (
        not flow
        or not secrets.compare_digest(str(request_obj.GET.get("state", "")), flow["state"])
        or time.time() - flow["created"] > 600
        or flow["user"] != str(request_obj.user.pk)
    ):
        raise ValidationError("Invalid or expired OAuth state. Start the connection again.")
    connection = StorageConnection.objects.get(pk=flow["connection"])
    require(request_obj.user, connection.workspace_id, "manage_storage_connections")
    validate_scope(request_obj.user, connection.workspace_id, connection.brand)
    if not request_obj.GET.get("code"):
        raise ValidationError("Google authorization was not granted.")
    try:
        response = request(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "code": request_obj.GET["code"],
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": flow["verifier"],
            },
        ).json()
        if not response.get("refresh_token"):
            raise ProviderFailure("No refresh token returned; revoke the old grant and reconnect.")
        connection.credentials_encrypted = seal({"refresh_token": response["refresh_token"]})
        connection.scopes = response.get("scope", " ".join(flow["scopes"])).split()
        access = response.get("access_token")
        if access:
            about = request(
                "GET",
                DRIVE + "/about",
                headers={"Authorization": "Bearer " + access},
                params={"fields": "user(emailAddress)"},
            ).json()
            connection.account_email = about.get("user", {}).get("emailAddress", "")
        connection.status = "connected"
        connection.last_error = ""
        connection.save()
        record(request_obj.user, connection, "integration_connected")
    except ProviderFailure as exc:
        raise ValidationError(str(exc)) from None
    return HttpResponseRedirect("/integrations")


def token(connection):
    if connection.status != "connected" or not connection.credentials_encrypted:
        raise ProviderFailure("Google connection is disconnected. Reconnect before continuing.")
    credentials = unseal(connection.credentials_encrypted)
    try:
        result = request(
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": credentials["refresh_token"],
                "grant_type": "refresh_token",
            },
        ).json()
        if not result.get("access_token"):
            raise ProviderFailure("Google did not return an access token.")
        return result["access_token"]
    except ProviderFailure:
        connection.status = "error"
        connection.last_error = "Google authorization failed; reconnect the account."
        connection.save(update_fields=["status", "last_error"])
        raise


def upsert(connection, metadata):
    identity = metadata.get("id")
    if not identity:
        raise ProviderFailure("Google response did not contain a file identity.")
    with transaction.atomic():
        obj, _ = StorageObject.objects.update_or_create(
            connection=connection,
            external_id=identity,
            defaults={
                "workspace": connection.workspace,
                "brand": connection.brand,
                "provider": "google_drive",
                "filename": metadata.get("name", identity),
                "mime_type": metadata.get("mimeType", ""),
                "size": int(metadata.get("size", 0)),
                "checksum": metadata.get("md5Checksum", ""),
                "parents": metadata.get("parents", []),
                "active": not metadata.get("trashed", False),
                "metadata": {"availability": "trashed" if metadata.get("trashed") else "available"},
            },
        )
    return obj


def sync(connection, heartbeat=lambda: None):
    from apps.storage.drive_tree import sync as scoped_sync

    return scoped_sync(connection, heartbeat)


def safe_session(uri):
    parsed = urlparse(uri)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ["www.googleapis.com", "upload.googleapis.com"]
        or parsed.username
        or parsed.password
        or parsed.port not in [None, 443]
    ):
        raise ProviderFailure("Provider returned an unexpected resumable upload URL.")
    return uri


def resume(upload, heartbeat=lambda: None):
    if upload.status == "complete":
        return
    if upload.provider == "youtube":
        master(upload.version)
    connection = upload.connection
    headers = {"Authorization": "Bearer " + token(connection)}
    upload.attempts += 1
    upload.save(update_fields=["attempts"])
    size = upload.total_bytes
    if not upload.session_encrypted:
        # Mark initialization before network I/O. A lost response must not create another YouTube video.
        if upload.status == "initializing":
            raise ProviderFailure(
                "Upload initialization is uncertain. Reconcile with the provider before creating a new upload."
            )
        folder_id = None
        if upload.provider == "google_drive":
            from apps.storage.drive_tree import upload_folder

            folder_id = upload_folder(upload, heartbeat)
        upload.status = "initializing"
        upload.save(update_fields=["status"])
        if upload.provider == "youtube":
            url = "https://www.googleapis.com/upload/youtube/v3/videos"
            params = {"uploadType": "resumable", "part": "snippet,status"}
            body = {
                "snippet": {"title": upload.version.creative.title},
                "status": {"privacyStatus": upload.privacy},
            }
        else:
            url = "https://www.googleapis.com/upload/drive/v3/files"
            params = {
                "uploadType": "resumable",
                "supportsAllDrives": "true",
                "fields": "id,name,mimeType,size,md5Checksum,parents",
            }
            body = {
                "name": upload.storage_object.filename,
                "appProperties": {
                    "app": "creative_manager",
                    "workspace_id": str(upload.workspace_id),
                    "version_id": str(upload.version_id),
                    "upload_id": str(upload.pk),
                },
            }
            body["parents"] = [folder_id]
        result = request(
            "POST",
            url,
            params=params,
            headers=headers
            | {
                "X-Upload-Content-Type": upload.storage_object.mime_type,
                "X-Upload-Content-Length": str(size),
            },
            json=body,
        )
        session = safe_session(result.headers.get("Location", ""))
        upload.session_encrypted = seal({"uri": session})
        upload.status = "uploading"
        upload.save()
    session = safe_session(unseal(upload.session_encrypted)["uri"])
    result = request(
        "PUT",
        session,
        headers=headers | {"Content-Range": f"bytes */{size}", "Content-Length": "0"},
        content=b"",
    )
    if result.status_code in [200, 201]:
        return confirm(upload, result.json())
    position = (
        int(result.headers.get("Range", "bytes=0--1").split("-")[-1]) + 1
        if result.headers.get("Range")
        else 0
    )
    with local_path(upload.storage_object).open("rb") as stream:
        while position < size:
            heartbeat()
            stream.seek(position)
            chunk = stream.read(8 * 1024 * 1024)
            end = position + len(chunk) - 1
            result = request(
                "PUT",
                session,
                headers=headers
                | {
                    "Content-Type": upload.storage_object.mime_type,
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {position}-{end}/{size}",
                },
                content=chunk,
            )
            if result.status_code in [200, 201]:
                return confirm(upload, result.json())
            confirmed = (
                int(result.headers.get("Range", "").split("-")[-1]) + 1
                if result.headers.get("Range")
                else 0
            )
            if confirmed <= position:
                raise ProviderFailure("Google did not advance the confirmed upload offset.")
            position = confirmed
            upload.uploaded_bytes = position
            upload.status = "uploading"
            upload.save(update_fields=["uploaded_bytes", "status"])
    raise ProviderFailure("Upload bytes sent but no final provider receipt was returned.")


@transaction.atomic
def confirm(upload, result):
    external_id = result.get("id")
    if not external_id or not isinstance(external_id, str):
        raise ProviderFailure("No confirmed external identity in upload response.")
    upload.external_id = external_id
    upload.uploaded_bytes = upload.total_bytes
    upload.status = "complete"
    upload.last_error = ""
    upload.save()
    if upload.provider == "google_drive":
        obj = upsert(upload.connection, result)
        # Preserve approved file history. Drive copy is a separate export attachment.
        from apps.storage.models import CreativeFile

        CreativeFile.objects.get_or_create(
            workspace=upload.workspace,
            brand=upload.brand,
            creative=upload.version.creative,
            version=upload.version,
            storage_object=obj,
            role="export",
        )
    else:
        from apps.performance.models import Deployment

        Deployment.objects.get_or_create(
            workspace=upload.workspace,
            brand=upload.brand,
            provider="youtube",
            ad_id=external_id,
            defaults={
                "title": upload.version.creative.title,
                "creative": upload.version.creative,
                "version": upload.version,
                "state": "paused",
                "deployed_at": timezone.now(),
            },
        )
        from apps.creatives.services import confirmed_publication

        confirmed_publication(upload.created_by, upload.version)
    record(upload.created_by, upload, "upload_complete", {"external_id": external_id})


def organize(connection, heartbeat=lambda: None):
    from apps.storage.drive_tree import organize as organize_tree

    return organize_tree(connection, heartbeat)
