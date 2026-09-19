from unittest.mock import patch

import httpx
import pytest

from apps.storage.drive_tree import FOLDER, organize, sync
from apps.storage.google import ProviderFailure
from apps.storage.models import DriveFolderMapping, StorageConnection, StorageObject, SyncRun


@pytest.fixture
def drive(team):
    return StorageConnection.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        created_by=team["people"]["manager"],
        name="Fixture",
        root_folder_id="root",
        status="connected",
    )


def test_root_inventory_move_delete_and_exclusion(drive):
    tree = {
        "root": {"id": "root", "mimeType": FOLDER, "parents": []},
        "folder": {"id": "folder", "name": "Folder", "mimeType": FOLDER, "parents": ["root"]},
        "asset": {"id": "asset", "name": "Before", "parents": ["folder"]},
        "outside": {"id": "outside", "name": "Secret", "parents": ["outside-root"]},
    }
    changes = []

    def transport(method, url, **kwargs):
        params = kwargs.get("params", {})
        if url.endswith("/changes/startPageToken"):
            return httpx.Response(200, json={"startPageToken": "token"})
        if url.endswith("/changes"):
            return httpx.Response(200, json={"changes": changes})
        if url.endswith("/files"):
            parent = params["q"].split("'")[1]
            assert parent in ["root", "folder"]
            return httpx.Response(
                200, json={"files": [v for v in tree.values() if parent in v["parents"]]}
            )
        return httpx.Response(200, json=tree[url.rsplit("/", 1)[1]])

    with (
        patch("apps.storage.google.token", return_value="fixture"),
        patch("apps.storage.google.request", side_effect=transport),
    ):
        sync(drive)
        original = StorageObject.objects.get(external_id="asset")
        assert not StorageObject.objects.filter(external_id="outside").exists()
        tree["asset"].update(name="After", parents=["root"])
        changes[:] = [
            {"fileId": "asset", "file": tree["asset"]},
            {"fileId": "outside", "file": tree["outside"]},
        ]
        sync(drive)
        current = StorageObject.objects.get(external_id="asset")
        assert current.pk == original.pk and current.filename == "After" and current.active
        tree["asset"]["parents"] = ["outside-root"]
        sync(drive)
        current.refresh_from_db()
        assert (
            not current.active and not StorageObject.objects.filter(external_id="outside").exists()
        )
        changes[:] = [{"fileId": "asset", "removed": True}]
        sync(drive)
        assert StorageObject.objects.get(pk=original.pk).active is False


def test_failed_scan_does_not_advance_cursor_or_deactivate_inventory(drive):
    obj = StorageObject.objects.create(
        workspace=drive.workspace,
        brand=drive.brand,
        connection=drive,
        external_id="asset",
        provider="google_drive",
    )
    with (
        patch("apps.storage.google.token", return_value="fixture"),
        patch("apps.storage.google.request", side_effect=ProviderFailure("Denied")),
    ):
        with pytest.raises(ProviderFailure):
            sync(drive)
    obj.refresh_from_db()
    drive.refresh_from_db()
    assert obj.active and drive.change_token == ""
    assert SyncRun.objects.get(connection=drive).status == "failed"


def test_organization_retries_use_provider_ids_without_duplicate_folders(team, drive):
    from apps.creatives.services import new_version

    new_version(team["people"]["editor"], team["creative"])
    remote = {"root": {"id": "root", "mimeType": FOLDER, "parents": []}}
    allocated = []
    posts = []

    def transport(method, url, **kwargs):
        if url.endswith("/files/generateIds"):
            value = f"id-{len(allocated)}"
            allocated.append(value)
            return httpx.Response(200, json={"ids": [value]})
        if method == "GET" and url.endswith("/files"):
            parent = kwargs["params"]["q"].split("'")[1]
            return httpx.Response(
                200,
                json={
                    "files": [item for item in remote.values() if parent in item.get("parents", [])]
                },
            )
        if method == "PATCH":
            remote[url.rsplit("/", 1)[1]].update(kwargs["json"])
        if method == "POST":
            data = kwargs["json"]
            assert data["id"] not in remote
            remote[data["id"]] = data
            posts.append(data)
            return httpx.Response(200, json={"id": data["id"]})
        item = remote.get(url.rsplit("/", 1)[1])
        return httpx.Response(200 if item else 404, json=item or {})

    with (
        patch("apps.storage.google.token", return_value="fixture"),
        patch("apps.storage.google.request", side_effect=transport),
    ):
        organize(drive)
        count = len(posts)
        organize(drive)
        assert len(posts) == count
        assert {"Source", "Creatives", "Library", "Clips", "Context"} <= {p["name"] for p in posts}
        assert any(p["name"].startswith("v001-") for p in posts)
        assert not any(p["name"] == "Masters" for p in posts)
        folder = DriveFolderMapping.objects.get(
            entity_type="creative", entity_id=team["creative"].pk, folder_role="root"
        )
        remote[folder.drive_folder_id]["name"] = "Renamed outside app"
        organize(drive)
        assert len(posts) == count
        from apps.storage.drive_names import creative_folder_name, workspace_folder_name

        assert remote[folder.drive_folder_id]["name"] == creative_folder_name(team["creative"])
        ws_mapping = DriveFolderMapping.objects.get(
            entity_type="workspace", entity_id=team["ws"].pk, folder_role="root"
        )
        old_id = ws_mapping.drive_folder_id
        remote[old_id]["name"] = "WS-aabbccdd_old-name"
        parents_before = {key: item.get("parents") for key, item in remote.items()}
        organize(drive)
        ws_mapping.refresh_from_db()
        assert ws_mapping.drive_folder_id == old_id
        assert remote[old_id]["name"] == workspace_folder_name(team["ws"])
        assert (
            len(posts) == count
            and {key: item.get("parents") for key, item in remote.items()} == parents_before
        )


def test_missing_root_and_disconnected_authorization_fail_safely(drive):
    drive.root_folder_id = ""
    with (
        patch("apps.storage.google.token", return_value="fixture"),
        patch("apps.storage.google.request") as network,
    ):
        with pytest.raises(ProviderFailure):
            sync(drive)
        network.assert_not_called()
    from apps.storage.google import token

    drive.status = "disconnected"
    with pytest.raises(ProviderFailure):
        token(drive)
