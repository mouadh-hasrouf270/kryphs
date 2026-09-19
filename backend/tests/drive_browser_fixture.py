"""Explicit local browser fixture. Never registered as a production provider."""

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import django
import httpx


def main():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from django.conf import settings
    from django.db import connection as database
    from django.utils import timezone

    from apps.accounts.models import User
    from apps.catalog.models import Brand
    from apps.common.jobs import handle
    from apps.common.models import Job
    from apps.storage.drive_tree import FOLDER
    from apps.storage.models import StorageConnection, Upload
    from apps.workspaces.models import Workspace

    if not settings.DEBUG:
        raise RuntimeError("Browser fixtures require development mode.")
    prefix = "Browser automatic Drive fixture"
    if sys.argv[1] == "--seed":
        workspace = Workspace.objects.get(slug="studio-demo")
        brand = Brand.objects.create(
            workspace=workspace, name="Automatic Drive QA", slug="auto-qa-" + uuid.uuid4().hex[:10]
        )
        destination = StorageConnection.objects.create(
            workspace=workspace,
            brand=brand,
            name=prefix,
            created_by=User.objects.get(email="manager@demo.local"),
            status="connected",
            root_folder_id="fixture-root",
        )
        print(json.dumps({"brand": str(brand.pk), "connection": str(destination.pk)}))
        return
    upload = Upload.objects.select_related("connection").get(pk=sys.argv[2])
    if upload.connection.name != prefix or upload.connection.credentials_encrypted:
        raise RuntimeError("Refusing to operate on a real Google connection.")
    path = root / ".qa" / ("drive-browser-" + str(upload.connection_id) + ".json")
    path.parent.mkdir(exist_ok=True)
    state = (
        json.loads(path.read_text())
        if path.exists()
        else {
            "next_id": 1,
            "remote": {
                "fixture-root": {
                    "id": "fixture-root",
                    "name": "CreativeManager",
                    "mimeType": FOLDER,
                    "parents": [],
                }
            },
            "sessions": {},
        }
    )
    remote = state["remote"]

    def provider(method, url, **kwargs):
        assert not database.in_atomic_block, "Provider I/O must run after commit."
        if url.endswith("/generateIds"):
            value = "folder-" + str(state["next_id"])
            state["next_id"] += 1
            return httpx.Response(200, json={"ids": [value]})
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
            value = "asset-" + str(upload.pk)
            uri = "https://www.googleapis.com/upload/drive/v3/files?upload_id=" + value
            state["sessions"][uri] = {
                **body,
                "id": value,
                "mimeType": upload.storage_object.mime_type,
                "size": str(upload.total_bytes),
            }
            return httpx.Response(200, headers={"Location": uri})
        if method == "PUT":
            item = state["sessions"][url]
            if item["id"] in remote:
                return httpx.Response(200, json=item)
            if kwargs["headers"]["Content-Range"].startswith("bytes */"):
                return httpx.Response(308)
            remote[item["id"]] = item
            return httpx.Response(200, json=item)
        if method == "POST" and url.endswith("/files"):
            body = kwargs["json"]
            assert body["id"] not in remote
            remote[body["id"]] = body
            return httpx.Response(200, json={"id": body["id"]})
        value = url.rsplit("/", 1)[1]
        if method == "PATCH":
            remote[value].update(kwargs["json"])
        return httpx.Response(200 if value in remote else 404, json=remote.get(value, {}))

    job = Job.objects.get(type="google_upload", payload__upload=str(upload.pk))
    if job.status != "succeeded":
        job.status = "running"
        job.heartbeat_at = timezone.now()
        job.save()
        with (
            patch("apps.storage.google.token", return_value="explicit-browser-fixture"),
            patch("apps.storage.google.request", side_effect=provider),
        ):
            handle(job)
        job.status, job.completed_at = "succeeded", timezone.now()
        job.save()
    path.write_text(json.dumps(state), encoding="utf-8")
    upload.refresh_from_db()
    print(json.dumps({"status": upload.status, "remote": list(remote.values())}))


if __name__ == "__main__":
    main()
