from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from apps.storage.drive_names import (
    component,
    drive_file_name,
    request_folder_name,
    reserve_name,
    version_folder_name,
    workspace_folder_name,
)
from apps.storage.models import StorageConnection


def test_exact_names_and_unicode():
    manager = SimpleNamespace(display_name="Manager", email="manager@example.test")
    ahmed = SimpleNamespace(display_name="Ahmed", email="ahmed@example.test")
    mohamed = SimpleNamespace(display_name="Mohamed", email="m@example.test")
    ws = SimpleNamespace(
        name="Olive Studio",
        created_at=datetime(2026, 9, 19, 4, 15, tzinfo=timezone.utc),
        created_by=manager,
    )
    assert workspace_folder_name(ws) == "Olive-Studio-20260919-041500-Manager"
    req = SimpleNamespace(
        title="Hair Loss UGC",
        created_at=datetime(2026, 9, 19, 4, 22, 30, tzinfo=timezone.utc),
        requester=ahmed,
    )
    assert request_folder_name(req) == "Hair-Loss-UGC-20260919-042230-Ahmed"
    version = SimpleNamespace(
        version_number=2,
        label="Second Cut",
        created_at=datetime(2026, 9, 19, 4, 32, 50, tzinfo=timezone.utc),
        editor=mohamed,
        creative=SimpleNamespace(title="Hook A"),
    )
    assert version_folder_name(version) == "v002-Second-Cut-20260919-043250-Mohamed"
    source = SimpleNamespace(
        filename="final edit (new).mp4",
        created_at=datetime(2026, 9, 19, 4, 34, tzinfo=timezone.utc),
    )
    upload = SimpleNamespace(
        storage_object=source, version=version, role="master", created_by=mohamed
    )
    assert (
        drive_file_name(upload) == "Hook-A-v002-master-final-edit-new-20260919-043400-Mohamed.mp4"
    )
    assert component("فيديو تساقط الشعر") == "فيديو-تساقط-الشعر"
    source.filename = "../../bad/name\\test?.mp4"
    name = drive_file_name(upload)
    assert name.endswith(".mp4") and "/" not in name and "\\" not in name and "?" not in name
    assert component("\x00\x01 / ") == ""


def test_collision_suffix_is_reserved_and_stable(team):
    drive = StorageConnection.objects.create(
        workspace=team["ws"], brand=team["brand"], created_by=team["people"]["manager"]
    )
    remote = [{"id": "some-other-id", "name": "Readable.mp4"}]
    with patch(
        "apps.storage.google.request",
        side_effect=lambda *a, **kw: httpx.Response(200, json={"files": remote}),
    ):
        first = reserve_name(
            drive, {}, "parent", "Readable.mp4", "upload:one", "", extension=".mp4"
        )
        second = reserve_name(
            drive, {}, "parent", "Readable.mp4", "upload:two", "", extension=".mp4"
        )
        assert first == "Readable-02.mp4" and second == "Readable-03.mp4"
        remote.clear()
        assert (
            reserve_name(drive, {}, "parent", "Readable.mp4", "upload:one", "", extension=".mp4")
            == first
        )
