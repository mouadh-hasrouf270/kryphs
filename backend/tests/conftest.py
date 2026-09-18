import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Brand
from apps.creatives.models import Creative
from apps.requests_app.models import CreativeRequest
from apps.workspaces.models import Workspace, WorkspaceMembership


@pytest.fixture
def team(db, settings, tmp_path):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.MEDIA_ROOT = tmp_path / "media"
    ws = Workspace.objects.create(name="Studio", slug="studio")
    other = Workspace.objects.create(name="Other", slug="other")
    brand = Brand.objects.create(workspace=ws, name="One", slug="one")
    restricted = Brand.objects.create(workspace=ws, name="Two", slug="two")
    people = {}
    for role in ["manager", "editor", "reviewer", "requester", "viewer", "media_buyer"]:
        user = User.objects.create_user(role + "@example.test", "TestPassword!546")
        WorkspaceMembership.objects.create(workspace=ws, user=user, role=role)
        people[role] = user
    req = CreativeRequest.objects.create(
        workspace=ws,
        brand=brand,
        code="REQ-1",
        title="Request",
        requester=people["requester"],
        owner=people["editor"],
        status="assigned",
    )
    creative = Creative.objects.create(
        workspace=ws,
        brand=brand,
        code="CR-1",
        title="Creative",
        request=req,
        owner=people["editor"],
        status="assigned",
    )
    return dict(
        ws=ws,
        other=other,
        brand=brand,
        restricted=restricted,
        people=people,
        request=req,
        creative=creative,
    )


@pytest.fixture
def client_for():
    def client(user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    return client
