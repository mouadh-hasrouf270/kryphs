import hashlib
import sqlite3
import zipfile

from django.core.management import call_command

from apps.common.legacy import inspect_and_import
from apps.common.models import LegacyMapping
from apps.workspaces.models import Workspace


def test_legacy_dry_run_resume_and_source_immutability(db, tmp_path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as source:
        source.execute("CREATE TABLE cm_workspaces (id INTEGER PRIMARY KEY,name TEXT,slug TEXT)")
        source.execute("INSERT INTO cm_workspaces VALUES (1,'Legacy studio','legacy')")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    dry = inspect_and_import(path, True)
    assert dry["imported"] == {"cm_workspaces": 1} and not dry["committed"]
    assert not Workspace.objects.exists()
    actual = inspect_and_import(path, False)
    assert actual["committed"] and Workspace.objects.count() == 1
    again = inspect_and_import(path, False)
    assert again["existing"] == {"cm_workspaces": 1} and LegacyMapping.objects.count() == 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_unsupported_legacy_data_rolls_back(db, tmp_path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as source:
        source.execute("CREATE TABLE cm_unknown (id INTEGER PRIMARY KEY)")
        source.execute("INSERT INTO cm_unknown VALUES (1)")
    report = inspect_and_import(path, False)
    assert report["unsupported_tables"] == {"cm_unknown": 1} and not report["committed"]


def test_restore_rejects_zip_traversal(tmp_path):
    import pytest
    from django.core.management.base import CommandError

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escaped", "no")
    with pytest.raises(CommandError):
        call_command("restore_database", str(archive), destination=str(tmp_path / "restore"))
    assert not (tmp_path / "escaped").exists()


def test_legacy_review_status_mapping_and_attribution(db, tmp_path):
    path = tmp_path / "complete-legacy.sqlite"
    with sqlite3.connect(path) as source:
        source.executescript("""
        CREATE TABLE cm_workspaces(id INTEGER PRIMARY KEY,name TEXT,slug TEXT);
        INSERT INTO cm_workspaces VALUES(1,'Original','original');
        CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,name TEXT);
        INSERT INTO users VALUES(1,'legacy@example.test','Legacy Editor');
        CREATE TABLE cm_brands(id INTEGER PRIMARY KEY,workspace_id INTEGER,name TEXT);
        INSERT INTO cm_brands VALUES(1,1,'Brand');
        CREATE TABLE cm_products(id INTEGER PRIMARY KEY,brand_id INTEGER,name TEXT);
        INSERT INTO cm_products VALUES(1,1,'Product');
        CREATE TABLE cm_statuses(id INTEGER PRIMARY KEY,slug TEXT);
        INSERT INTO cm_statuses VALUES(1,'in_review');
        CREATE TABLE cm_creative_requests(id INTEGER PRIMARY KEY,product_id INTEGER,requested_by INTEGER,assigned_editor_id INTEGER,status_id INTEGER,objective TEXT);
        INSERT INTO cm_creative_requests VALUES(1,1,1,1,1,'Legacy request');
        CREATE TABLE cm_creatives(id INTEGER PRIMARY KEY,request_id INTEGER,product_id INTEGER,assigned_editor_id INTEGER,public_code TEXT,name TEXT);
        INSERT INTO cm_creatives VALUES(1,1,1,1,'OLD-1','Legacy creative');
        CREATE TABLE cm_creative_versions(id INTEGER PRIMARY KEY,creative_id INTEGER,version_number INTEGER,editor_id INTEGER,status_id INTEGER);
        INSERT INTO cm_creative_versions VALUES(1,1,1,1,1);
        """)
    report = inspect_and_import(path, False)
    assert report["committed"], report
    from apps.accounts.models import User
    from apps.creatives.models import CreativeVersion

    version = CreativeVersion.objects.get()
    assert version.status == "submitted" and version.creative.status == "ready_for_review"
    assert version.editor.email == "legacy@example.test"
    assert not User.objects.get(email="legacy@example.test").is_active
