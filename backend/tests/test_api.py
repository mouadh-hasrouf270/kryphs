from django.test import Client

from apps.creatives.models import Creative
from apps.creatives.services import new_version
from apps.integrations.crypto import seal
from apps.storage.models import StorageConnection
from apps.workspaces.models import WorkspaceMembership


def url(team, path):
    return f"/api/v1/{path}/?workspace={team['ws'].pk}"




def test_request_create_with_platforms_does_not_500(team, client_for):
    from apps.catalog.models import Platform

    meta = Platform.objects.create(name="Meta", slug="meta-test")
    tiktok = Platform.objects.create(name="TikTok", slug="tiktok-test")
    c = client_for(team["people"]["manager"])

    response = c.post(
        url(team, "requests"),
        {
            "title": "Platform request",
            "brand": str(team["brand"].pk),
            "platforms": [str(meta.pk), str(tiktok.pk)],
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    request = CreativeRequest.objects.get(pk=response.json()["id"])
    assert set(request.platforms.values_list("pk", flat=True)) == {meta.pk, tiktok.pk}


def test_cross_workspace_reads_and_writes(team, client_for):
    client = client_for(team["people"]["manager"])
    hidden = Creative.objects.create(workspace=team["other"], code="OTHER", title="Hidden")
    assert client.get(url(team, "creatives")).status_code == 200
    assert client.get(url(team, "creatives/" + str(hidden.pk))).status_code == 404
    assert client.get("/api/v1/creatives/?workspace=" + str(team["other"].pk)).status_code == 403
    assert (
        client.post(
            url(team, "creatives"),
            {"title": "Attack", "workspace": str(team["other"].pk), "brand": str(team["brand"].pk)},
            format="json",
        ).status_code
        == 201
    )
    assert Creative.objects.get(title="Attack").workspace_id == team["ws"].pk


def test_brand_scope_cannot_be_bypassed(team, client_for):
    user = team["people"]["manager"]
    m = WorkspaceMembership.objects.get(user=user)
    m.brand_restricted = True
    m.save()
    m.brands.add(team["brand"])
    forbidden = Creative.objects.create(
        workspace=team["ws"], brand=team["restricted"], code="SECRET", title="Secret"
    )
    client = client_for(user)
    assert client.get(url(team, "creatives/" + str(forbidden.pk))).status_code == 404
    r = client.post(
        url(team, "creatives"),
        {"title": "Attack", "brand": str(team["restricted"].pk)},
        format="json",
    )
    assert r.status_code in [400, 403]
    assert not client.get(url(team, "search") + "&q=Secret").json()["results"]


def test_viewer_cannot_mutate(team, client_for):
    c = client_for(team["people"]["viewer"])
    assert (
        c.post(
            url(team, "requests"), {"title": "Test", "brand": str(team["brand"].pk)}, format="json"
        ).status_code
        == 403
    )
    assert c.delete(url(team, "creatives/" + str(team["creative"].pk))).status_code == 405
    assert c.post(
        url(team, "creatives/" + str(team["creative"].pk) + "/actions/approve"), {}, format="json"
    ).status_code in [400, 403]


def test_status_and_history_are_protected(team, client_for):
    c = client_for(team["people"]["manager"])
    creative = team["creative"]
    result = c.patch(
        url(team, "creatives/" + str(creative.pk)),
        {"status": "published", "approved_version": None},
        format="json",
    )
    assert result.status_code == 200
    creative.refresh_from_db()
    assert creative.status == "assigned"
    version = new_version(team["people"]["editor"], creative)
    assert (
        c.patch(
            url(team, "versions/" + str(version.pk)), {"notes": "Overwrite"}, format="json"
        ).status_code
        == 403
    )


def test_inaccessible_experiment_arm_rejected(team, client_for):
    from apps.experiments.models import Experiment

    exp = Experiment.objects.create(workspace=team["ws"], brand=team["brand"], title="Test")
    hidden = Creative.objects.create(workspace=team["other"], code="OTHER", title="Hidden")
    c = client_for(team["people"]["manager"])
    r = c.post(
        url(team, "experiment-arms"),
        {
            "brand": str(team["brand"].pk),
            "experiment": str(exp.pk),
            "creative": str(hidden.pk),
            "name": "Bad",
        },
        format="json",
    )
    assert r.status_code == 400


def test_credentials_never_serialized(team, client_for):
    connection = StorageConnection.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        name="Secret",
        credentials_encrypted=seal({"refresh_token": "do-not-expose"}),
        created_by=team["people"]["manager"],
    )
    c = client_for(team["people"]["manager"])
    r = c.get(url(team, "storage/connections/" + str(connection.pk)))
    assert (
        r.status_code == 200
        and "credentials_encrypted" not in r.json()
        and "do-not-expose" not in r.content.decode()
    )
    assert "credentials_encrypted" not in str(c.get(url(team, "schema")).json())


def test_csrf_required_for_login(team):
    c = Client(enforce_csrf_checks=True)
    result = c.post(
        "/api/v1/auth/session/",
        {"email": "manager@example.test", "password": "TestPassword!546"},
        content_type="application/json",
    )
    assert result.status_code == 403
    c.get("/api/v1/auth/session/")
    token = c.cookies["csrftoken"].value
    result = c.post(
        "/api/v1/auth/session/",
        {"email": "manager@example.test", "password": "TestPassword!546"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert result.status_code == 200 and result.json()["email"] == "manager@example.test"


def test_oauth_invalid_state_rejected(team, client_for):
    c = client_for(team["people"]["manager"])
    result = c.get("/api/v1/google/callback/?state=forged&code=forged")
    assert result.status_code == 400


def test_schema_and_all_registered_resources(team, client_for):
    from apps.common.resources import DEFINITIONS

    c = client_for(team["people"]["manager"])
    result = c.get(url(team, "schema"))
    assert result.status_code == 200
    for route in DEFINITIONS:
        response = c.get(url(team, route))
        assert response.status_code == 200, (route, response.content)


def test_missing_scope_and_invalid_scope_fail_safely(team, client_for):
    c = client_for(team["people"]["manager"])
    assert c.get("/api/v1/creatives/").status_code == 400
    assert c.get("/api/v1/creatives/?workspace=invalid").status_code == 403


def test_temporary_password_blocks_business_data_until_changed(team, client_for):
    user = team["people"]["editor"]
    user.must_change_password = True
    user.save()
    c = client_for(user)
    assert c.get(url(team, "creatives")).status_code == 403
    assert c.get("/api/v1/me/").status_code == 200
    changed = c.post(
        "/api/v1/me/",
        {"old_password": "TestPassword!546", "new_password": "Changed!Password8642"},
        format="json",
    )
    assert changed.status_code == 200
    user.refresh_from_db()
    assert not user.must_change_password
    assert c.get(url(team, "creatives")).status_code == 200


def test_approved_context_is_preserved_and_linked_within_brand(team, client_for):
    from apps.context_hub.models import ContextDocument
    from apps.context_hub.services import approve, new_version

    actor = team["people"]["manager"]
    doc = ContextDocument.objects.create(workspace=team["ws"], brand=team["brand"], title="Claims")
    v1 = new_version(actor, doc, {"content": "Only verified claims."})
    approve(actor, v1)
    v2 = new_version(actor, doc, {"content": "Updated verified claims."})
    v1.refresh_from_db()
    assert (
        v1.content == "Only verified claims." and v1.status == "approved" and v2.version_number == 2
    )
    c = client_for(actor)
    assert (
        c.patch(
            url(team, "context-versions/" + str(v1.pk)), {"content": "Overwrite"}, format="json"
        ).status_code
        == 403
    )
    r = c.post(
        url(team, "context-links"),
        {
            "brand": str(team["brand"].pk),
            "creative": str(team["creative"].pk),
            "document_version": str(v1.pk),
        },
        format="json",
    )
    assert r.status_code == 201


def test_assignment_cannot_be_smuggled_through_generic_patch(team, client_for):
    c = client_for(team["people"]["editor"])
    r = c.patch(
        url(team, "creatives/" + str(team["creative"].pk)),
        {"owner": str(team["people"]["manager"].pk)},
        format="json",
    )
    assert r.status_code == 403


def test_notifications_are_private_and_mark_all_read_is_scoped(team, client_for):
    from apps.notifications.models import Notification

    user = team["people"]["editor"]
    other = team["people"]["reviewer"]
    for i, recipient in enumerate([user, other]):
        Notification.objects.create(
            workspace=team["ws"],
            brand=team["brand"],
            user=recipient,
            title="Private",
            kind="assignment",
            dedupe_key="private" + str(i),
        )
    c = client_for(user)
    assert len(c.get(url(team, "notifications")).json()["results"]) == 1
    assert c.post(url(team, "notifications/mark-all-read"), {}, format="json").status_code == 200
    assert Notification.objects.get(user=user).read_at
    assert not Notification.objects.get(user=other).read_at
