"""Explicit browser-test fixture, never loaded by the production provider registry."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.conf import settings

from apps.accounts.models import User
from apps.catalog.models import Brand
from apps.storage.google import upsert
from apps.storage.models import StorageConnection
from apps.workspaces.models import Workspace

if not settings.DEBUG:
    raise RuntimeError("Test fixtures require DEBUG=True")
workspace = Workspace.objects.get(slug="studio-demo")
brand = Brand.objects.filter(workspace=workspace).first()
actor = User.objects.get(email="admin@demo.local")
connection, _ = StorageConnection.objects.get_or_create(
    workspace=workspace,
    brand=brand,
    name="Explicit development Drive fixture",
    defaults={"created_by": actor, "provider": "google_drive", "status": "disconnected"},
)
rename = "--rename" in sys.argv
obj = upsert(
    connection,
    {
        "id": "development-fixture-file-identity",
        "name": "Renamed fixture.png" if rename else "Original fixture.png",
        "mimeType": "image/png",
        "parents": ["fixture-folder-b" if rename else "fixture-folder-a"],
        "size": "12",
    },
)
print(obj.pk)
