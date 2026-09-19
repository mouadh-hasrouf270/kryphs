from unittest.mock import patch

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.common.models import Job
from apps.creatives.services import new_version, transition
from apps.storage.google import ProviderFailure, resume
from apps.storage.mirrors import enqueue_drive_mirror
from apps.storage.models import CreativeFile, StorageConnection, StorageObject, Upload
from apps.storage.services import enqueue_transfer, master, upload_local


@pytest.fixture
def drive(team):
    return StorageConnection.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        created_by=team["people"]["manager"],
        name="Automatic",
        status="connected",
        root_folder_id="root",
    )


def video(name="original.mp4"):
    return SimpleUploadedFile(name, b"\x00\x00\x00\x18ftypmp42" + b"0" * 30)


def prepare(team):
    c = team["creative"]
    new_version(team["people"]["editor"], c)
    c.refresh_from_db()
    return c


@pytest.mark.parametrize(
    "role", ["master", "source", "thumbnail", "subtitle", "reference", "attachment", "export"]
)
def test_every_role_queues_exact_asset_after_commit(
    team, drive, django_capture_on_commit_callbacks, role
):
    c = prepare(team)
    with patch("apps.storage.google.request") as network:
        with django_capture_on_commit_callbacks(execute=True):
            asset = upload_local(team["people"]["editor"], c, video(), role)
            assert not Upload.objects.exists()
        network.assert_not_called()
    queued = Upload.objects.get()
    assert (
        queued.storage_object == asset
        and queued.version == c.current_version
        and queued.role == role
    )
    assert queued.connection == drive and asset.drive_upload["queued"]
    assert Job.objects.filter(type="google_upload").count() == 1
    file = CreativeFile.objects.get(storage_object=asset)
    for _ in range(3):
        assert enqueue_drive_mirror(team["people"]["editor"], file)["upload_id"] == str(queued.pk)
    assert Upload.objects.count() == 1 and Job.objects.filter(type="google_upload").count() == 1


def test_disconnected_ambiguous_and_default_selection(team, django_capture_on_commit_callbacks):
    c = prepare(team)
    with django_capture_on_commit_callbacks(execute=True):
        asset = upload_local(team["people"]["editor"], c, video(), "master")
    assert asset.drive_upload == {"queued": False, "reason": "drive_not_connected"}
    file = CreativeFile.objects.get(storage_object=asset)
    connections = [
        StorageConnection.objects.create(
            workspace=team["ws"],
            brand=team["brand"],
            created_by=team["people"]["manager"],
            name=str(i),
            status="connected",
        )
        for i in range(2)
    ]
    assert (
        enqueue_drive_mirror(team["people"]["editor"], file)["reason"]
        == "drive_destination_ambiguous"
    )
    connections[1].auto_upload_default = True
    connections[1].save()
    enqueue_drive_mirror(team["people"]["editor"], file)
    assert Upload.objects.get().connection == connections[1]
    connections[0].brand = team["restricted"]
    connections[0].save()
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        enqueue_drive_mirror(team["people"]["editor"], file, connection=connections[0])


def test_queue_failure_keeps_local_upload_and_http_retry_identity(
    team, drive, client_for, django_capture_on_commit_callbacks
):
    c = prepare(team)
    editor = client_for(team["people"]["editor"])
    path = f"/api/v1/creatives/{c.pk}/actions/upload/?workspace={team['ws'].pk}"
    with patch(
        "apps.storage.mirrors.enqueue_drive_mirror", side_effect=RuntimeError("private payload")
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = editor.post(
                path, {"file": video(), "role": "thumbnail"}, HTTP_IDEMPOTENCY_KEY="one-attempt"
            )
    assert response.status_code == 201
    asset = StorageObject.objects.get(pk=response.json()["id"])
    assert asset.metadata["drive_upload"]["reason"] == "drive_queue_failed"
    from apps.storage.services import local_path

    assert local_path(asset).exists()
    retry = editor.post(
        path, {"file": video(), "role": "thumbnail"}, HTTP_IDEMPOTENCY_KEY="one-attempt"
    )
    assert retry.status_code == 201 and retry.json()["id"] == str(asset.pk)
    assert CreativeFile.objects.filter(version=c.current_version).count() == 1


@pytest.mark.django_db(transaction=True)
def test_rollback_never_queues_and_commit_runs_outside_transaction(team, drive):
    c = prepare(team)
    with patch("apps.storage.mirrors.enqueue_drive_mirror") as queue:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                upload_local(team["people"]["editor"], c, video(), "thumbnail")
                raise RuntimeError("rollback")
        queue.assert_not_called()
    from django.db import connection

    states = []
    real = enqueue_drive_mirror

    def observed(*args, **kwargs):
        states.append(connection.in_atomic_block)
        return real(*args, **kwargs)

    with patch("apps.storage.mirrors.enqueue_drive_mirror", side_effect=observed):
        upload_local(team["people"]["editor"], c, video(), "thumbnail")
    assert states == [False] and Upload.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_resumable_mirror_retries_manual_transfer_and_version_history(
    team, drive, django_capture_on_commit_callbacks
):
    from apps.storage.drive_tree import FOLDER

    c = prepare(team)
    remote = {"root": {"id": "root", "name": "CreativeManager", "mimeType": FOLDER, "parents": []}}
    sessions, allocated, init_names = {}, [], []

    def provider(method, url, **kwargs):
        from django.db import connection
        assert not connection.in_atomic_block
        if url.endswith("/generateIds"):
            key = "folder-" + str(len(allocated))
            allocated.append(key)
            return httpx.Response(200, json={"ids": [key]})
        if method == "GET" and url.endswith("/files"):
            parent = kwargs["params"]["q"].split("'")[1]
            return httpx.Response(
                200,
                json={
                    "files": [item for item in remote.values() if parent in item.get("parents", [])]
                },
            )
        if method == "POST" and "/upload/drive/" in url:
            body = kwargs["json"]
            init_names.append(body["name"])
            key = "asset-" + str(len(sessions))
            uri = "https://www.googleapis.com/upload/drive/v3/files?upload_id=" + key
            sessions[uri] = {**body, "id": key, "mimeType": "video/mp4", "size": "42"}
            return httpx.Response(200, headers={"Location": uri})
        if method == "PUT":
            if kwargs["headers"]["Content-Range"].startswith("bytes */"):
                return httpx.Response(308)
            item = sessions[url]
            remote[item["id"]] = item
            return httpx.Response(200, json=item)
        if method == "POST":
            body = kwargs["json"]
            remote[body["id"]] = body
            return httpx.Response(200, json={"id": body["id"]})
        key = url.rsplit("/", 1)[1]
        if method == "PATCH":
            remote[key].update(kwargs["json"])
        return httpx.Response(200 if key in remote else 404, json=remote.get(key, {}))

    with (
        patch("apps.storage.google.token", return_value="fixture"),
        patch("apps.storage.google.request", side_effect=provider),
    ):
        copies = []
        for index in [1, 2]:
            with django_capture_on_commit_callbacks(execute=True):
                asset = upload_local(
                    team["people"]["editor"], c, video(f"master-v{index}.mp4"), "master"
                )
            upload = Upload.objects.get(storage_object=asset)
            resume(upload)
            resume(upload)  # complete replay
            assert upload.status == "complete"
            copies.append(remote[upload.external_id])
            same = enqueue_transfer(
                team["people"]["editor"],
                drive,
                {"version": str(c.current_version_id), "idempotency_key": "random-new-key"},
            )
            assert same.pk == upload.pk
            assert (
                CreativeFile.objects.filter(
                    version=c.current_version, role="master", active=True
                ).count()
                == 1
            )
            transition(team["people"]["editor"], c, "submit")
            if index == 1:
                transition(team["people"]["reviewer"], c, "request-changes", "New cut")
                new_version(team["people"]["editor"], c)
                c.refresh_from_db()
            else:
                transition(team["people"]["reviewer"], c, "approve")
                c.current_version.refresh_from_db()
                assert master(c.current_version) == asset
        assert copies[0]["parents"] != copies[1]["parents"] and copies[0]["id"] != copies[1]["id"]
        assert len(init_names) == 2 and all("master-master-v" in name for name in init_names)
        assert Upload.objects.count() == 2
        assert CreativeFile.objects.filter(creative=c, active=True).count() == 4


def test_uncertain_drive_initialization_is_not_replayed(team, drive):
    c = prepare(team)
    obj = StorageObject.objects.create(workspace=team["ws"], brand=team["brand"], filename="a.mp4")
    upload = Upload.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        connection=drive,
        version=c.current_version,
        storage_object=obj,
        created_by=team["people"]["editor"],
        status="initializing",
        idempotency_key="uncertain",
    )
    with (
        patch("apps.storage.google.token", return_value="fixture"),
        patch("apps.storage.google.request") as provider,
    ):
        with pytest.raises(ProviderFailure, match="uncertain"):
            resume(upload)
        provider.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_concurrent_enqueue_reuses_one_identity(team, drive):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    c = prepare(team)
    # Persist a source first, then make both callers race on the same asset.
    drive.status = "disconnected"
    drive.save()
    asset = upload_local(team["people"]["editor"], c, video(), "thumbnail")
    drive.status = "connected"
    drive.save()
    file = CreativeFile.objects.get(storage_object=asset)
    barrier = Barrier(2)

    def queue():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return enqueue_drive_mirror(team["people"]["editor"], file)["upload_id"]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: queue(), range(2)))
    assert len(set(results)) == 1 and Upload.objects.count() == 1
    assert Job.objects.filter(type="google_upload").count() == 1
