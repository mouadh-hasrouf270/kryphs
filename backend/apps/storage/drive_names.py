"""Deterministic Unicode display names. Provider IDs remain the only identity."""

import re
import unicodedata
from datetime import timezone
from pathlib import PurePosixPath

from django.db import IntegrityError, transaction


def component(value, limit=65):
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "".join(c if unicodedata.category(c)[0] in "LMN" or c in "._-" else "-" for c in text)
    return re.sub(r"-+", "-", text).strip(".- ")[:limit].rstrip(".-")


def stamp(entity):
    return entity.created_at.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def person(user):
    return component(user.display_name or user.email) if user else ""


def entity_name(entity, name, user=None):
    return "-".join(
        part for part in [component(name) or "Untitled", stamp(entity), person(user)] if part
    )[:200]


def workspace_folder_name(workspace):
    return entity_name(workspace, workspace.name, workspace.created_by)


def brand_folder_name(brand):
    return entity_name(brand, brand.name)


def campaign_folder_name(campaign):
    return entity_name(campaign, campaign.name)


def request_folder_name(request):
    return entity_name(request, request.title, request.requester)


def creative_folder_name(creative):
    return entity_name(creative, creative.title, creative.owner)


def version_folder_name(version):
    number = f"v{version.version_number:03}"
    label = component(version.label)
    return entity_name(
        version, number + ("-" + label if label and label != number else ""), version.editor
    )


def drive_file_name(upload):
    source = upload.storage_object
    original = PurePosixPath(source.filename.replace("\\", "/"))
    extension = "." + component(original.suffix.lstrip("."), 16) if original.suffix else ""
    stem = "-".join(
        filter(
            None,
            [
                component(upload.version.creative.title),
                f"v{upload.version.version_number:03}",
                component(upload.role),
                component(original.stem, 45),
                stamp(source),
                person(upload.created_by),
            ],
        )
    )
    return stem[: 200 - len(extension)].rstrip(".-") + extension


def reserve_name(connection, headers, parent, desired, owner, remote_id, extension=""):
    """Check remote siblings, then reserve locally before provider I/O. Concurrent
    workers cannot reserve the same display name for different managed entities.
    A persisted reservation is stable across network failures and retries.
    """
    from apps.storage.drive_tree import identity, list_params
    from apps.storage.google import DRIVE, ProviderFailure, request
    from apps.storage.models import DriveNameReservation

    parent = parent or "root"
    taken, page = set(), None
    while True:
        params = {
            **list_params(connection),
            "q": f"'{identity(parent)}' in parents and trashed=false",
            "fields": "nextPageToken,incompleteSearch,files(id,name)",
        }
        if page:
            params["pageToken"] = page
        result = request("GET", DRIVE + "/files", headers=headers, params=params).json()
        if result.get("incompleteSearch"):
            raise ProviderFailure("Cannot reserve a name from an incomplete Drive listing.")
        taken.update(item["name"] for item in result.get("files", []) if item["id"] != remote_id)
        page = result.get("nextPageToken")
        if not page:
            break
    existing = DriveNameReservation.objects.filter(connection=connection, identity=owner).first()
    # Keep a previously chosen collision suffix when the desired base is unchanged.
    if (
        existing
        and existing.base_name == desired
        and existing.parent_id == parent
        and existing.name not in taken
    ):
        return existing.name
    stem = desired[: -len(extension)] if extension else desired
    for n in range(1, 10001):
        suffix = f"-{n:02}" if n > 1 else ""
        name = stem[: 200 - len(extension) - len(suffix)] + suffix + extension
        if name in taken:
            continue
        try:
            with transaction.atomic():
                if existing:
                    existing.parent_id, existing.name, existing.base_name = parent, name, desired
                    existing.save(update_fields=["parent_id", "name", "base_name"])
                else:
                    DriveNameReservation.objects.create(
                        connection=connection,
                        workspace=connection.workspace,
                        brand=connection.brand,
                        identity=owner,
                        parent_id=parent,
                        name=name,
                        base_name=desired,
                    )
            return name
        except IntegrityError:
            existing = DriveNameReservation.objects.filter(
                connection=connection, identity=owner
            ).first()
            if (
                existing
                and existing.base_name == desired
                and existing.parent_id == parent
                and existing.name not in taken
            ):
                return existing.name
    raise ProviderFailure("Unable to reserve a unique managed Drive name.")
