import pytest

from apps.accounts.models import User
from apps.creatives.models import Creative
from apps.creatives.services import new_version, transition
from apps.requests_app.models import CreativeRequest, RequestDeliverable
from apps.workspaces.models import WorkspaceMembership


def url(team, route):
    return f"/api/v1/{route}/?workspace={team['ws'].pk}"


def make_deliverable(team, client_for):
    c = client_for(team["people"]["manager"])
    result = c.post(
        url(team, "requests"),
        {
            "title": "Private production",
            "brand": str(team["brand"].pk),
            "deliverables": [{"title": "Inline video"}],
        },
        format="json",
    )
    assert result.status_code == 201, result.content
    request_id = result.json()["id"]
    result = c.post(
        url(team, "deliverables"),
        {
            "request": request_id,
            "title": "Added later",
            "quantity": 1,
            "hook": "Opening",
            "script": "Full script",
            "notes": "Production notes",
            "requirements": "Keep this",
        },
        format="json",
    )
    assert result.status_code == 201, result.content
    return CreativeRequest.objects.get(pk=request_id), RequestDeliverable.objects.get(
        pk=result.json()["id"]
    )


def test_standalone_sequence_and_brief_are_server_managed(team, client_for):
    req, d = make_deliverable(team, client_for)
    assert (
        d.sequence == 2
        and d.hook == "Opening"
        and d.script == "Full script"
        and d.notes == "Production notes"
    )
    c = client_for(team["people"]["manager"])
    response = c.patch(
        url(team, f"deliverables/{d.pk}"), {"sequence": 99, "notes": "Updated"}, format="json"
    )
    assert response.status_code == 200
    d.refresh_from_db()
    assert d.sequence == 2 and d.notes == "Updated"
    r = c.post(url(team, "deliverables"), {"request": str(req.pk), "title": "Third"}, format="json")
    assert r.status_code == 201 and r.json()["sequence"] == 3


def test_unrelated_request_is_not_listed_or_retrievable(team, client_for):
    c = client_for(team["people"]["viewer"])
    req = team["request"]
    assert str(req.pk) not in {r["id"] for r in c.get(url(team, "requests")).json()["results"]}
    assert c.get(url(team, f"requests/{req.pk}")).status_code == 404


def test_creator_owner_admin_and_brand_revocation(team, client_for):
    req = team["request"]
    admin = User.objects.create_superuser("admin@example.test", "test")
    for user in [team["people"]["requester"], team["people"]["editor"], admin]:
        c = client_for(user)
        assert c.get(url(team, f"requests/{req.pk}")).status_code == 200
        assert str(req.pk) in {r["id"] for r in c.get(url(team, "requests")).json()["results"]}
    member = WorkspaceMembership.objects.get(user=team["people"]["editor"])
    member.brand_restricted = True
    member.save()
    member.brands.add(team["restricted"])
    assert client_for(member.user).get(url(team, f"requests/{req.pk}")).status_code == 404


def test_requester_team_edit_duplicate_and_primary_sync(team, client_for):
    from apps.requests_app.assignments import sync_primary
    from apps.requests_app.services import assign

    req = team["request"]
    d = RequestDeliverable.objects.create(
        workspace=team["ws"], brand=team["brand"], request=req, sequence=1, title="Team"
    )
    requester = client_for(team["people"]["requester"])
    data = {
        "deliverable": str(d.pk),
        "user": str(team["people"]["viewer"].pk),
        "role": "filming_responsible",
        "notes": "Saturday",
    }
    made = requester.post(url(team, "deliverable-assignments"), data, format="json")
    assert made.status_code == 201, made.content
    assert (
        requester.post(url(team, "deliverable-assignments"), data, format="json").status_code == 400
    )
    path = url(team, f"deliverable-assignments/{made.json()['id']}")
    updated = requester.patch(path, {"role": "scriptwriter", "notes": "Monday"}, format="json")
    assert updated.status_code == 200 and updated.json()["notes"] == "Monday"
    assert requester.patch(path, {"role": "editor"}, format="json").status_code == 403
    assign(team["people"]["manager"], d, team["people"]["editor"])
    d.refresh_from_db()
    sync_primary(d)
    sync_primary(d)
    assert d.assignments.filter(role="editor", user=d.assigned_editor).count() == 1
    assign(team["people"]["manager"], d, team["people"]["manager"])
    assert d.assignments.filter(role="editor", user=team["people"]["manager"]).count() == 1
    assert not d.assignments.filter(role="editor", user=team["people"]["editor"]).exists()
    assert d.assignments.get(role="scriptwriter").notes == "Monday"


def test_editor_assignment_backfill_is_repeatable(team):
    import importlib

    from django.apps import apps

    d = RequestDeliverable.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        request=team["request"],
        sequence=1,
        title="Existing",
        assigned_editor=team["people"]["editor"],
    )
    migration = importlib.import_module(
        "apps.requests_app.migrations.0004_backfill_primary_editor_assignments"
    )
    migration.backfill(apps, None)
    migration.backfill(apps, None)
    assert d.assignments.count() == 1
    assert d.assignments.get().user == d.assigned_editor


def test_editor_and_filming_assignments_visibility_and_no_escalation(team, client_for):
    req, d = make_deliverable(team, client_for)
    manager = client_for(team["people"]["manager"])
    for role, user in [
        ("editor", team["people"]["editor"]),
        ("filming_responsible", team["people"]["viewer"]),
    ]:
        r = manager.post(
            url(team, "deliverable-assignments"),
            {
                "deliverable": str(d.pk),
                "user": str(user.pk),
                "role": role,
                "notes": "Outdoor Saturday",
            },
            format="json",
        )
        assert r.status_code == 201, r.content
        assert r.json()["relation_labels"]["user"] == user.email
        assert client_for(user).get(url(team, f"requests/{req.pk}")).status_code == 200
        assert str(d.pk) in {
            row["id"] for row in client_for(user).get(url(team, "tasks")).json()["results"]
        }
    d.refresh_from_db()
    assert d.assigned_editor == team["people"]["editor"]
    rows = manager.get(url(team, "deliverable-assignments") + "&deliverable=" + str(d.pk)).json()[
        "results"
    ]
    assert len(rows) == 2 and all(row["notes"] == "Outdoor Saturday" for row in rows)
    viewer = client_for(team["people"]["viewer"])
    assert (
        viewer.post(
            url(team, f"deliverables/{d.pk}/actions/start-production"), {}, format="json"
        ).status_code
        == 403
    )
    assert (
        viewer.post(
            url(team, "deliverable-assignments"),
            {"deliverable": str(d.pk), "user": str(team["people"]["viewer"].pk), "role": "editor"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        client_for(team["people"]["media_buyer"]).get(url(team, f"requests/{req.pk}")).status_code
        == 404
    )
    assert (
        client_for(team["people"]["reviewer"]).get(url(team, f"requests/{req.pk}")).status_code
        == 200
    )
    assert (
        client_for(team["people"]["manager"]).get(url(team, f"requests/{req.pk}")).status_code
        == 200
    )
    filming = next(row for row in rows if row["role"] == "filming_responsible")
    assert (
        manager.post(
            url(team, f"deliverable-assignments/{filming['id']}/actions/remove"), {}, format="json"
        ).status_code
        == 204
    )
    assert viewer.get(url(team, f"requests/{req.pk}")).status_code == 404


def test_assignment_rejects_foreign_inactive_and_brand_restricted_users(team, client_for):
    _, d = make_deliverable(team, client_for)
    c = client_for(team["people"]["manager"])
    foreign = User.objects.create_user("foreign@example.test", "test")
    WorkspaceMembership.objects.create(user=foreign, workspace=team["other"], role="editor")
    member = WorkspaceMembership.objects.get(user=team["people"]["viewer"])
    member.brand_restricted = True
    member.save()
    member.brands.add(team["restricted"])
    for user in [foreign, team["people"]["viewer"]]:
        r = c.post(
            url(team, "deliverable-assignments"),
            {"deliverable": str(d.pk), "user": str(user.pk), "role": "filming_responsible"},
            format="json",
        )
        assert r.status_code in [400, 403]
    team["people"]["editor"].is_active = False
    team["people"]["editor"].save()
    assert (
        c.post(
            url(team, "deliverable-assignments"),
            {"deliverable": str(d.pk), "user": str(team["people"]["editor"].pk), "role": "editor"},
            format="json",
        ).status_code
        == 400
    )


def test_file_history_labels_scoping_and_generic_create_disabled(team, client_for):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.storage.models import CreativeFile
    from apps.storage.services import upload_local

    c = team["creative"]
    p = team["people"]
    editor = client_for(p["editor"])
    v1 = new_version(p["editor"], c)
    c.refresh_from_db()
    first = upload_local(
        p["editor"],
        c,
        SimpleUploadedFile("master-v1.mp4", b"\x00\x00\x00\x18ftypmp42" + b"0" * 30),
        "master",
    )
    transition(p["editor"], c, "submit")
    transition(p["reviewer"], c, "request-changes", "New opening")
    v2 = new_version(p["editor"], c)
    c.refresh_from_db()
    upload_local(
        p["editor"],
        c,
        SimpleUploadedFile("master-v2.mp4", b"\x00\x00\x00\x18ftypmp42" + b"1" * 30),
        "master",
    )
    for stage in ["draft", "approved"]:
        if stage == "approved":
            transition(p["editor"], c, "submit")
            transition(p["reviewer"], c, "approve")
        rows = editor.get(url(team, "files") + "&creative=" + str(c.pk)).json()["results"]
        assert len(rows) == 2
        assert {r["relation_labels"]["storage_object"] for r in rows} == {
            "master-v1.mp4",
            "master-v2.mp4",
        }
        assert all("Creative" in r["relation_labels"]["version"] for r in rows)
    assert CreativeFile.objects.get(version=v1).active
    assert (
        editor.post(
            url(team, "files"),
            {
                "creative": str(c.pk),
                "version": str(v1.pk),
                "storage_object": str(first.pk),
                "role": "master",
            },
            format="json",
        ).status_code
        == 403
    )
    other = Creative.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        code="OTHER-VERSION",
        title="Different creative",
        owner=p["editor"],
    )
    foreign_version = new_version(p["editor"], other)
    invalid = editor.post(
        url(team, "comments"),
        {
            "creative": str(c.pk),
            "version": str(foreign_version.pk),
            "brand": str(team["brand"].pk),
            "body": "Wrong version",
        },
        format="json",
    )
    assert invalid.status_code == 400 and "version" in invalid.json()
    versions = editor.get(url(team, "versions") + "&creative=" + str(c.pk)).json()["results"]
    assert {row["id"] for row in versions} == {str(v1.pk), str(v2.pk)}
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        CreativeFile.objects.create(
            workspace=team["ws"],
            brand=team["brand"],
            creative=c,
            version=v1,
            storage_object=first,
            role="master",
        )
