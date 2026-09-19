"""Root-bounded inventory and durable managed-folder identities.

No HTTP call runs inside a database write transaction. A single worker serializes
organization; provider IDs are allocated and persisted before folder creation.
"""

import re
from collections import deque

from django.utils import timezone

from apps.audit.services import record
from apps.storage.models import DriveFolderMapping, StorageObject, SyncRun

FOLDER = "application/vnd.google-apps.folder"
FIELDS = "id,name,mimeType,size,md5Checksum,parents,trashed,driveId"


def identity(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value or ""):
        from apps.storage.google import ProviderFailure

        raise ProviderFailure("Invalid Drive folder identity.")
    return value


def metadata(headers, file_id):
    from apps.storage.google import DRIVE, request

    return request(
        "GET",
        DRIVE + "/files/" + identity(file_id),
        headers=headers,
        params={"supportsAllDrives": "true", "fields": FIELDS},
    ).json()


def validate_root(connection, headers):
    from apps.storage.google import ProviderFailure

    if not connection.root_folder_id:
        raise ProviderFailure("Select or create a managed root before syncing files.")
    root = metadata(headers, connection.root_folder_id)
    if root.get("trashed") or root.get("mimeType") != FOLDER:
        raise ProviderFailure("The configured root is not an active Drive folder.")
    if connection.shared_drive_id and root.get("driveId") != connection.shared_drive_id:
        raise ProviderFailure("Root does not belong to the configured Shared Drive.")
    return root


def in_root(connection, headers, folder_id):
    seen = set()
    pending = [folder_id]
    while pending:
        node = pending.pop()
        if node == connection.root_folder_id:
            return True
        if node in seen or len(seen) > 200:
            continue
        seen.add(node)
        item = metadata(headers, node)
        if not item.get("trashed"):
            pending.extend(item.get("parents", []))
    return False


def list_params(connection):
    params = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true", "pageSize": 100}
    if connection.shared_drive_id:
        params.update(corpora="drive", driveId=connection.shared_drive_id)
    return params


def sync(connection, heartbeat=lambda: None):
    from apps.storage.google import DRIVE, ProviderFailure, request, token, upsert

    run = SyncRun.objects.create(
        workspace=connection.workspace, brand=connection.brand, connection=connection
    )
    try:
        headers = {"Authorization": "Bearer " + token(connection)}
        validate_root(connection, headers)
        params = {"supportsAllDrives": "true"}
        if connection.shared_drive_id:
            params["driveId"] = connection.shared_drive_id
        next_token = request(
            "GET", DRIVE + "/changes/startPageToken", headers=headers, params=params
        ).json()["startPageToken"]
        # Changes update known identities only. Never ingest an arbitrary accessible
        # file from the change feed. The subtree walk reconciles folder moves too.
        page = connection.change_token
        while page:
            heartbeat()
            result = request(
                "GET",
                DRIVE + "/changes",
                headers=headers,
                params={
                    **params,
                    "pageToken": page,
                    "includeItemsFromAllDrives": "true",
                    "fields": f"nextPageToken,changes(fileId,removed,file({FIELDS}))",
                },
            ).json()
            for change in result.get("changes", []):
                known = StorageObject.objects.filter(
                    connection=connection, external_id=change["fileId"]
                )
                if change.get("removed"):
                    known.update(active=False, metadata={"availability": "removed_or_inaccessible"})
                elif change.get("file") and known.exists():
                    upsert(connection, change["file"])
            page = result.get("nextPageToken")
        seen, visited = set(), set()
        pending = deque([connection.root_folder_id])
        while pending:
            parent = pending.popleft()
            if parent in visited:
                continue
            visited.add(parent)
            page = None
            while True:
                heartbeat()
                query = {
                    **list_params(connection),
                    "q": f"'{identity(parent)}' in parents and trashed=false",
                    "fields": f"nextPageToken,incompleteSearch,files({FIELDS})",
                }
                if page:
                    query["pageToken"] = page
                result = request("GET", DRIVE + "/files", headers=headers, params=query).json()
                if result.get("incompleteSearch"):
                    raise ProviderFailure(
                        "Drive returned an incomplete inventory. Retry before reconciling files."
                    )
                for item in result.get("files", []):
                    # Defense in depth: a provider response must match the bounded query.
                    if parent not in item.get("parents", []) or item.get("trashed"):
                        continue
                    upsert(connection, item)
                    seen.add(item["id"])
                    if item.get("mimeType") == FOLDER:
                        pending.append(item["id"])
                page = result.get("nextPageToken")
                if not page:
                    break
        # Keep historical links while removing availability outside the root.
        # Individual updates avoid SQLite's variable-count limit on large inventories.
        for obj in (
            StorageObject.objects.filter(connection=connection)
            .only("pk", "external_id", "metadata", "active")
            .iterator()
        ):
            if obj.external_id not in seen:
                obj.active = False
                obj.metadata = {**obj.metadata, "availability": "outside_root_or_unavailable"}
                obj.save(update_fields=["active", "metadata"])
        connection.change_token = next_token
        connection.last_sync = timezone.now()
        connection.last_error = ""
        connection.status = "connected"
        connection.save(update_fields=["change_token", "last_sync", "last_error", "status"])
        run.status, run.object_count = "succeeded", len(seen)
        record(connection.created_by, connection, "drive_synced", {"objects": len(seen)})
    except Exception:
        run.status = "failed"
        run.error = "Drive sync failed. Check authorization, root access and Shared Drive settings."
        connection.last_error = run.error
        connection.save(update_fields=["last_error"])
        raise
    finally:
        run.completed_at = timezone.now()
        run.save()


def ensure_folder(connection, headers, entity, role, name, parent, heartbeat=lambda: None):
    from apps.storage.drive_names import reserve_name
    from apps.storage.google import DRIVE, ProviderFailure, request

    heartbeat()
    kind = entity._meta.model_name
    mapping = DriveFolderMapping.objects.filter(
        connection=connection, entity_type=kind, entity_id=entity.pk, folder_role=role
    ).first()
    if mapping:
        # A pre-generated ID is safe to retry after an uncertain create. A remote
        # 404 is interpreted here only; authorization errors never trigger creates.
        response = request(
            "GET",
            DRIVE + "/files/" + identity(mapping.drive_folder_id),
            headers=headers,
            params={"supportsAllDrives": "true", "fields": FIELDS},
            accepted=[200, 404],
        )
        if response.status_code == 200:
            item = response.json()
            if item.get("trashed") or item.get("mimeType") != FOLDER:
                raise ProviderFailure(
                    "A mapped folder is trashed or unavailable. Restore it in Drive."
                )
            if parent and not in_root(connection, headers, mapping.drive_folder_id):
                raise ProviderFailure(
                    "A mapped folder was moved outside the managed root. Restore it before uploading."
                )
            if parent and parent not in item.get("parents", []):
                request(
                    "PATCH",
                    DRIVE + "/files/" + identity(mapping.drive_folder_id),
                    headers=headers,
                    params={
                        "supportsAllDrives": "true",
                        "addParents": identity(parent),
                        "removeParents": ",".join(item.get("parents", [])),
                        "fields": "id",
                    },
                    json={},
                )
            desired = reserve_name(
                connection, headers, parent, name, f"folder:{mapping.pk}", mapping.drive_folder_id
            )
            if item.get("name") != desired:
                request(
                    "PATCH",
                    DRIVE + "/files/" + identity(mapping.drive_folder_id),
                    headers=headers,
                    params={"supportsAllDrives": "true", "fields": "id"},
                    json={"name": desired},
                )
            return mapping.drive_folder_id
        if response.status_code != 404:
            raise ProviderFailure("Cannot verify the mapped Drive folder.")
    if not mapping:
        allocated = (
            request(
                "GET",
                DRIVE + "/files/generateIds",
                headers=headers,
                params={"count": 1, "space": "drive", "type": "files"},
            )
            .json()
            .get("ids", [])
        )
        if not allocated:
            raise ProviderFailure("Drive did not allocate a folder identity.")
        mapping, _ = DriveFolderMapping.objects.get_or_create(
            connection=connection,
            entity_type=kind,
            entity_id=entity.pk,
            folder_role=role,
            defaults={
                "workspace": connection.workspace,
                "brand": connection.brand,
                "drive_folder_id": allocated[0],
            },
        )
    body = {
        "id": mapping.drive_folder_id,
        "name": reserve_name(
            connection, headers, parent, name, f"folder:{mapping.pk}", mapping.drive_folder_id
        ),
        "mimeType": FOLDER,
        "appProperties": {
            "app": "creative_manager",
            "entity": str(entity.pk),
            "role": role,
            "connection": str(connection.pk),
        },
    }
    if parent:
        body["parents"] = [parent]
    receipt = request(
        "POST",
        DRIVE + "/files",
        headers=headers,
        params={"supportsAllDrives": "true", "fields": "id"},
        json=body,
    ).json()
    if receipt.get("id") != mapping.drive_folder_id:
        raise ProviderFailure("Folder receipt did not match the allocated identity.")
    return mapping.drive_folder_id


def organize(connection, heartbeat=lambda: None, creative=None):
    from apps.catalog.models import Brand
    from apps.creatives.models import Creative
    from apps.storage import drive_names
    from apps.storage.google import ProviderFailure, token

    headers = {"Authorization": "Bearer " + token(connection)}
    if not connection.brand_id:
        raise ProviderFailure("Choose a brand for this connection before organizing files.")

    def folder(entity, role, name, parent):
        return ensure_folder(connection, headers, entity, role, name, parent, heartbeat)

    if not connection.root_folder_id:
        connection.root_folder_id = folder(
            connection, "managed_root", "CreativeManager", connection.shared_drive_id or None
        )
        connection.save(update_fields=["root_folder_id"])
    validate_root(connection, headers)
    ws = connection.workspace
    ws_root = folder(ws, "root", drive_names.workspace_folder_name(ws), connection.root_folder_id)
    brand = Brand.objects.get(pk=connection.brand_id)
    brand_root = folder(brand, "root", drive_names.brand_folder_name(brand), ws_root)
    roots = {
        name: folder(brand, name.lower(), name, brand_root)
        for name in ["Library", "Clips", "Context", "Campaigns", "Requests"]
    }
    rows = Creative.objects.filter(workspace=ws, brand=brand, archived_at__isnull=True)
    if creative:
        rows = rows.filter(pk=creative.pk)
    request_roots = {}
    # Include requests before their first creative exists.
    from apps.requests_app.models import CreativeRequest

    requests = CreativeRequest.objects.filter(workspace=ws, brand=brand)
    if creative:
        requests = requests.filter(pk=creative.request_id)
    for req in requests.select_related("campaign"):
        parent = roots["Requests"]
        if req.campaign_id:
            campaign = req.campaign
            campaign_root = folder(
                campaign,
                "root",
                drive_names.campaign_folder_name(campaign),
                roots["Campaigns"],
            )
            parent = folder(campaign, "requests", "Requests", campaign_root)
        req_root = folder(req, "root", drive_names.request_folder_name(req), parent)
        folder(req, "source", "Source", req_root)
        request_roots[req.pk] = folder(req, "creatives", "Creatives", req_root)
    for row in rows:
        root = folder(
            row,
            "root",
            drive_names.creative_folder_name(row),
            request_roots.get(row.request_id, roots["Library"]),
        )
        for version in row.versions.all():
            folder(version, "root", drive_names.version_folder_name(version), root)


def upload_folder(upload, heartbeat=lambda: None):
    organize(upload.connection, heartbeat, creative=upload.version.creative)
    mapping = DriveFolderMapping.objects.get(
        connection=upload.connection,
        entity_type="creativeversion",
        entity_id=upload.version_id,
        folder_role="root",
    )
    return mapping.drive_folder_id
