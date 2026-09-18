from unittest.mock import patch

import httpx
import pytest

from apps.creatives.services import new_version, transition
from apps.integrations.crypto import seal
from apps.performance.models import Deployment
from apps.storage.google import ProviderFailure, confirm, resume
from apps.storage.models import StorageConnection, StorageObject, Upload


def fixture_upload(team, tmp_path, provider="google_drive"):
    c = team["creative"]
    p = team["people"]
    v = new_version(p["editor"], c)
    connection = StorageConnection.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        name="Explicit test fixture",
        provider="google_drive",
        created_by=p["manager"],
        status="connected",
        credentials_encrypted=seal({"refresh_token": "test-only"}),
    )
    from django.conf import settings

    settings.MEDIA_ROOT.mkdir(exist_ok=True)
    (settings.MEDIA_ROOT / "asset").write_bytes(b"12345678")
    obj = StorageObject.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        provider="local",
        filename="asset.mp4",
        mime_type="video/mp4",
        size=8,
        local_path="asset",
    )
    from apps.storage.models import CreativeFile

    CreativeFile.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        creative=c,
        version=v,
        storage_object=obj,
        role="master",
    )
    if provider == "youtube":
        transition(p["editor"], c, "submit")
        transition(p["reviewer"], c, "approve")
        v.refresh_from_db()
    return Upload.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        connection=connection,
        version=v,
        storage_object=obj,
        provider=provider,
        session_encrypted=seal({"uri": "https://www.googleapis.com/upload/test"}),
        status="uploading",
        total_bytes=8,
        idempotency_key="fixture-upload",
        created_by=p["editor"],
    )


@pytest.mark.parametrize("provider", ["google_drive", "youtube"])
def test_resumable_upload_uses_confirmed_offset_and_receipt(team, tmp_path, provider):
    upload = fixture_upload(team, tmp_path, provider)
    with (
        patch("apps.storage.google.token", return_value="test-token"),
        patch("apps.storage.google.request") as transport,
    ):
        transport.side_effect = [
            httpx.Response(308, headers={"Range": "bytes=0-3"}),
            httpx.Response(
                200,
                json={
                    "id": "confirmed-test-receipt",
                    "name": "asset.mp4",
                    "mimeType": "video/mp4",
                    "size": "8",
                },
            ),
        ]
        resume(upload)
        assert transport.call_args_list[1].kwargs["content"] == b"5678"
        assert transport.call_args_list[1].kwargs["headers"]["Content-Range"] == "bytes 4-7/8"
    upload.refresh_from_db()
    assert (
        upload.status == "complete"
        and upload.external_id == "confirmed-test-receipt"
        and upload.uploaded_bytes == 8
    )
    if provider == "youtube":
        assert Deployment.objects.filter(ad_id="confirmed-test-receipt").exists()
    with patch("apps.storage.google.request") as transport:
        resume(upload)
        transport.assert_not_called()


def test_missing_upload_receipt_does_not_succeed(team, tmp_path):
    upload = fixture_upload(team, tmp_path)
    with pytest.raises(ProviderFailure):
        confirm(upload, {})
    upload.refresh_from_db()
    assert upload.status != "complete" and not upload.external_id


def test_draft_youtube_upload_rejected_before_network(team, tmp_path):
    upload = fixture_upload(team, tmp_path)
    upload.provider = "youtube"
    upload.save()
    with patch("apps.storage.google.request") as transport:
        from rest_framework.exceptions import ValidationError

        with pytest.raises(ValidationError):
            resume(upload)
        transport.assert_not_called()


def test_uncertain_initialization_does_not_duplicate_video(team, tmp_path):
    upload = fixture_upload(team, tmp_path, "youtube")
    upload.session_encrypted = ""
    upload.status = "initializing"
    upload.save()
    with (
        patch("apps.storage.google.token", return_value="test"),
        patch("apps.storage.google.request") as transport,
    ):
        with pytest.raises(ProviderFailure):
            resume(upload)
        transport.assert_not_called()
