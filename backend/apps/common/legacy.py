"""Read-only legacy SQLite adapter. Unsupported data is reported, never silently discarded."""

import hashlib
import sqlite3
from pathlib import Path

from django.apps import apps
from django.db import transaction
from django.utils.text import slugify

from apps.common.models import LegacyMapping

TABLES = {
    "cm_workspaces": "workspaces.Workspace",
    "users": "accounts.User",
    "cm_brands": "catalog.Brand",
    "cm_platforms": "catalog.Platform",
    "cm_products": "catalog.Product",
    "cm_projects": "catalog.Project",
    "cm_campaigns": "catalog.Campaign",
    "cm_tags": "catalog.Tag",
    "cm_creative_requests": "requests_app.CreativeRequest",
    "cm_request_deliverables": "requests_app.RequestDeliverable",
    "cm_creatives": "creatives.Creative",
    "cm_creative_versions": "creatives.CreativeVersion",
    "cm_creative_comments": "creatives.CreativeComment",
    "cm_creative_feedback": "creatives.CreativeFeedback",
    "cm_creative_relationships": "creatives.CreativeRelationship",
}
ALIASES = {
    "requester_id": "requested_by",
    "owner_id": "assigned_editor_id",
    "sequence": "sequence_number",
    "author_id": "user_id",
    "text": "body",
    "description": "brief",
    "notes": "refresh_reason",
    "code": "public_code",
    "due_date": "deadline",
}


def inspect_and_import(path, dry_run=True, allow_partial=False):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Source database does not exist.")
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "source_sha256": fingerprint,
        "dry_run": dry_run,
        "counts": {},
        "imported": {},
        "existing": {},
        "orphans": [],
        "duplicates": [],
        "unsupported_tables": {},
        "errors": [],
        "warnings": [
            "Legacy OAuth credentials and password hashes are never imported. Imported users remain inactive until reviewed. Memberships require explicit administrator configuration."
        ],
    }
    source = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # Names come from SQLite metadata and are escaped as identifiers, never interpolated from CLI values.
    def rows(table):
        safe = table.replace('"', '""')
        return [dict(r) for r in source.execute(f'SELECT * FROM "{safe}"')]

    for table in sorted(tables):
        if table.startswith("cm_") or table == "users":
            report["counts"][table] = len(rows(table))
            if table not in TABLES and table != "cm_statuses" and report["counts"][table]:
                report["unsupported_tables"][table] = report["counts"][table]
    statuses = (
        {str(r["id"]): r["slug"] for r in rows("cm_statuses")} if "cm_statuses" in tables else {}
    )
    reverse = {label: table for table, label in TABLES.items()}
    objects = {}

    def resolve(label, identity):
        table = reverse.get(label)
        if not table or identity is None:
            return None
        key = (table, str(identity))
        if key in objects:
            return objects[key]
        mapping = LegacyMapping.objects.filter(
            source=fingerprint, table=table, legacy_id=str(identity)
        ).first()
        if mapping:
            return apps.get_model(label).objects.filter(pk=mapping.target_id).first()
        return None

    with transaction.atomic():
        for table, label in TABLES.items():
            if table not in tables:
                continue
            model = apps.get_model(label)
            for row in rows(table):
                identity = str(row.get("id", ""))
                if not identity:
                    report["errors"].append(
                        {"table": table, "id": "", "error": "Missing legacy identity"}
                    )
                    continue
                existing = resolve(label, identity)
                if existing:
                    objects[(table, identity)] = existing
                    report["existing"][table] = report["existing"].get(table, 0) + 1
                    continue
                values = {}
                missing = []
                for field in model._meta.fields:
                    name = field.name
                    if name in [
                        "id",
                        "created_at",
                        "updated_at",
                        "current_version",
                        "approved_version",
                        "password",
                        "last_login",
                        "date_joined",
                        "is_staff",
                        "is_superuser",
                        "is_active",
                    ]:
                        continue
                    if field.is_relation:
                        raw = row.get(field.attname, row.get(ALIASES.get(field.attname, "")))
                        if name == "author" and raw is None:
                            raw = row.get("reviewer_id")
                        obj = resolve(field.related_model._meta.label, raw)
                        if obj:
                            values[name] = obj
                        elif raw is not None:
                            missing.append(field.attname)
                    elif name == "status":
                        value = row.get("status") or statuses.get(str(row.get("status_id")))
                        if value == "in_review":
                            value = (
                                "submitted"
                                if label.endswith("CreativeVersion")
                                else "ready_for_review"
                            )
                        if value in ["planned", "created"]:
                            value = "new" if value == "planned" else "in_production"
                        if value and value in dict(field.choices):
                            values[name] = value
                    elif name == "slug":
                        values[name] = (
                            slugify(row.get("slug") or row.get("name") or table)[:35]
                            + "-"
                            + identity
                        )
                    elif name == "title":
                        values[name] = str(
                            row.get("title")
                            or row.get("name")
                            or row.get("objective")
                            or f"Imported {table} {identity}"
                        )[:200]
                    elif name == "code":
                        values[name] = (
                            "LEGACY-"
                            + fingerprint[:6]
                            + "-"
                            + str(row.get("public_code") or identity)
                        )
                    elif name == "text":
                        values[name] = row.get("body") or row.get("feedback_text") or ""
                    elif name == "version_type":
                        values[name] = (
                            row.get(name)
                            if row.get(name) in ["original", "revision", "refresh"]
                            else "original"
                        )
                    elif name in row and row[name] is not None:
                        values[name] = row[name]
                    elif ALIASES.get(name) in row and row[ALIASES[name]] is not None:
                        values[name] = row[ALIASES[name]]
                if label == "accounts.User":
                    values["email"] = str(
                        row.get("email") or f"legacy-{identity}@import.invalid"
                    ).lower()
                    values["display_name"] = row.get("name") or row.get("username") or ""
                    values["is_active"] = False
                    values["password"] = "!"
                    if model.objects.filter(email=values["email"]).exists():
                        report["duplicates"].append(
                            {"table": table, "id": identity, "field": "email"}
                        )
                        continue
                if any(f.name == "brand" for f in model._meta.fields) and "brand" not in values:
                    for relation in [
                        "product",
                        "project",
                        "request",
                        "creative",
                        "version",
                        "parent",
                    ]:
                        obj = values.get(relation)
                        if obj and getattr(obj, "brand_id", None):
                            values["brand"] = obj.brand
                            break
                    if row.get("project_id") and "brand" not in values:
                        project = resolve("catalog.Project", row["project_id"])
                        if project:
                            values["brand"] = project.brand
                if (
                    any(f.name == "workspace" for f in model._meta.fields)
                    and "workspace" not in values
                ):
                    for obj in values.copy().values():
                        if getattr(obj, "workspace_id", None):
                            values["workspace"] = obj.workspace
                            break
                if label == "creatives.CreativeVersion" and not values.get("editor"):
                    creative = values.get("creative")
                    values["editor"] = getattr(creative, "owner", None)
                missing += [
                    f.name
                    for f in model._meta.fields
                    if f.is_relation and not f.null and f.name not in values
                ]
                if missing:
                    report["orphans"].append(
                        {"table": table, "id": identity, "fields": sorted(set(missing))}
                    )
                    continue
                try:
                    with transaction.atomic():
                        obj = model(**values)
                        excluded = [
                            f.name
                            for f in model._meta.fields
                            if f.null and getattr(obj, f.attname, None) is None
                        ]
                        if label == "accounts.User":
                            excluded.append("password")
                        obj.full_clean(exclude=excluded)
                        obj.save()
                        LegacyMapping.objects.create(
                            source=fingerprint, table=table, legacy_id=identity, target_id=obj.pk
                        )
                        objects[(table, identity)] = obj
                        report["imported"][table] = report["imported"].get(table, 0) + 1
                except Exception:
                    report["errors"].append(
                        {
                            "table": table,
                            "id": identity,
                            "error": "Validation or uniqueness failure; inspect source record.",
                        }
                    )
        for (table, _), obj in objects.items():
            if table != "cm_creatives":
                continue
            versions = obj.versions.order_by("-version_number")
            obj.current_version = versions.first()
            obj.approved_version = versions.filter(status__in=["approved", "published"]).first()
            if obj.current_version:
                obj.status = {"submitted": "ready_for_review", "draft": "in_production"}.get(
                    obj.current_version.status, obj.current_version.status
                )
            obj.save()
        has_problems = any(
            report[k] for k in ["orphans", "duplicates", "errors", "unsupported_tables"]
        )
        report["committed"] = not dry_run and (allow_partial or not has_problems)
        if not report["committed"]:
            transaction.set_rollback(True)
        else:
            from apps.audit.models import AuditEvent

            for obj in objects.values():
                if obj._meta.label == "workspaces.Workspace":
                    AuditEvent.objects.create(
                        workspace=obj,
                        action="legacy_import",
                        object_type="legacy",
                        object_id=fingerprint,
                        summary={"counts": report["imported"]},
                    )
    source.close()
    if hashlib.sha256(path.read_bytes()).hexdigest() != fingerprint:
        raise RuntimeError("Source changed during import; investigate concurrent source writes.")
    return report
