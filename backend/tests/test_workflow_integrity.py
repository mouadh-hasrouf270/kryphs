import pytest
from rest_framework.exceptions import ValidationError

from apps.creatives.models import Creative
from apps.creatives.services import create_creative
from apps.requests_app.assignments import remove_assignment
from apps.requests_app.models import RequestDeliverable
from apps.requests_app.services import assign, recalculate_request, start


def children(team):
    return [
        RequestDeliverable.objects.create(
            workspace=team["ws"],
            brand=team["brand"],
            request=team["request"],
            sequence=i,
            title="Same title",
        )
        for i in [1, 2]
    ]


def test_assignment_readiness_and_removal(team):
    a, b = children(team)
    manager, editor = team["people"]["manager"], team["people"]["editor"]
    assign(manager, a, editor)
    assert recalculate_request(team["request"]).status == "new"
    assign(manager, b, editor)
    assert recalculate_request(team["request"]).status == "assigned"
    remove_assignment(manager, b.assignments.get(role="editor"))
    b.refresh_from_db()
    assert b.assigned_editor_id is None and b.status == "new"
    assert recalculate_request(team["request"]).status == "new"
    start(manager, a)
    assert recalculate_request(team["request"]).status == "in_production"


@pytest.mark.parametrize("invalid", ["missing", "inactive", "membership", "brand"])
def test_manager_cannot_start_without_valid_editor(team, invalid):
    from apps.workspaces.models import WorkspaceMembership

    a, _ = children(team)
    assign(team["people"]["manager"], a, team["people"]["editor"])
    a.refresh_from_db()
    if invalid == "missing":
        a.assigned_editor = None
        a.save()
    elif invalid == "inactive":
        a.assigned_editor.is_active = False
        a.assigned_editor.save()
    else:
        member = WorkspaceMembership.objects.get(user=a.assigned_editor)
        if invalid == "membership":
            member.active = False
        else:
            member.brand_restricted = True
        member.save()
    with pytest.raises(ValidationError, match="editor"):
        start(team["people"]["manager"], a)


def test_one_creative_including_archived_and_database_constraint(team):
    from django.db import IntegrityError, transaction
    from django.utils import timezone

    a, _ = children(team)
    assign(team["people"]["manager"], a, team["people"]["editor"])
    data = dict(workspace=team["ws"], deliverable=a, title="One")
    first = create_creative(team["people"]["editor"], data)
    first.archived_at = timezone.now()
    first.save()
    with pytest.raises(ValidationError, match="already"):
        create_creative(team["people"]["editor"], data)
    with pytest.raises(IntegrityError), transaction.atomic():
        Creative.objects.create(workspace=team["ws"], deliverable=a, code="duplicate")


def test_tasks_merge_responsibilities_not_titles(team, client_for):
    from apps.requests_app.assignments import save_assignment

    a, b = children(team)
    manager, editor = team["people"]["manager"], team["people"]["editor"]
    for d in [a, b]:
        assign(manager, d, editor)
        save_assignment(manager, dict(deliverable=d, user=editor, role="filming_responsible"))
    response = client_for(editor).get(f"/api/v1/tasks/?workspace={team['ws'].pk}")
    rows = [r for r in response.json()["results"] if r["kind"] == "deliverable"]
    assert len(rows) == 2 and {r["id"] for r in rows} == {str(a.pk), str(b.pk)}
    assert all(set(r["assignment_roles"]) == {"editor", "filming_responsible"} for r in rows)


def test_direct_api_duplicate_and_quantity_rejection(team, client_for):
    a, _ = children(team)
    assign(team["people"]["manager"], a, team["people"]["editor"])
    editor = client_for(team["people"]["editor"])
    path = f"/api/v1/creatives/?workspace={team['ws'].pk}"
    data = {"title": "Execution", "deliverable": str(a.pk)}
    assert editor.post(path, data, format="json").status_code == 201
    assert editor.post(path, data, format="json").status_code == 400
    manager = client_for(team["people"]["manager"])
    assert (
        manager.patch(
            f"/api/v1/deliverables/{a.pk}/?workspace={team['ws'].pk}",
            {"quantity": 2},
            format="json",
        ).status_code
        == 400
    )


@pytest.mark.django_db(transaction=True)
def test_legacy_migration_splits_without_deleting_history(team):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.creatives.models import CreativeVersion

    target = [("creatives", "0003_alter_creative_options_and_more")]
    MigrationExecutor(connection).migrate([("creatives", "0002_initial")])
    try:
        d = children(team)[0]
        d.quantity = 3
        d.assigned_editor = team["people"]["editor"]
        d.save()
        assign(team["people"]["manager"], d, team["people"]["editor"])
        originals = []
        for i in range(2):
            c = Creative.objects.create(
                workspace=team["ws"],
                brand=team["brand"],
                request=team["request"],
                deliverable=d,
                code=f"legacy-{i}",
                title=str(i),
            )
            v = CreativeVersion.objects.create(
                workspace=team["ws"],
                brand=team["brand"],
                creative=c,
                editor=team["people"]["editor"],
                version_number=1,
            )
            originals.append((c.pk, v.pk))
        MigrationExecutor(connection).migrate(target)
        d.refresh_from_db()
        assert d.quantity == 1 and d.legacy_quantity == 3
        assert team["request"].deliverables.count() == 4  # original two plus two executions
        assert Creative.objects.filter(pk__in=[p[0] for p in originals]).count() == 2
        assert CreativeVersion.objects.filter(pk__in=[p[1] for p in originals]).count() == 2
        assert (
            Creative.objects.filter(pk__in=[p[0] for p in originals])
            .values("deliverable")
            .distinct()
            .count()
            == 2
        )
        assert team["request"].deliverables.filter(assignments__role="editor").count() == 3
    finally:
        MigrationExecutor(connection).migrate(target)


def test_filming_only_cannot_start_even_as_superuser(team):
    from apps.accounts.models import User
    from apps.requests_app.assignments import save_assignment

    a, _ = children(team)
    save_assignment(
        team["people"]["manager"],
        dict(deliverable=a, user=team["people"]["editor"], role="filming_responsible"),
    )
    admin = User.objects.create_superuser("root@example.test", "test")
    for actor in [admin, team["people"]["manager"]]:
        with pytest.raises(ValidationError, match="editor"):
            start(actor, a)


def test_editor_loss_preserves_work_and_can_be_repaired(team):
    from apps.creatives.services import new_version
    from apps.requests_app.assignments import save_assignment

    a, _ = children(team)
    manager, editor = team["people"]["manager"], team["people"]["editor"]
    team_assignment = save_assignment(
        manager, dict(deliverable=a, user=editor, role="editor", notes="Keep notes")
    )
    c = create_creative(editor, dict(workspace=team["ws"], deliverable=a, title="Execution"))
    new_version(editor, c)
    save_assignment(manager, {"role": "filming_responsible"}, instance=team_assignment)
    a.refresh_from_db()
    assert a.status == "in_production" and a.assigned_editor_id is None
    assert a.assignments.get().notes == "Keep notes"
    from apps.creatives.services import editor_access

    with pytest.raises(ValidationError, match="editor"):
        editor_access(manager, c)
    # A missing primary can be restored without rewriting downstream history.
    a.status = "approved"
    a.save()
    assign(manager, a, editor)
    a.refresh_from_db()
    assert a.status == "approved" and a.assigned_editor == editor
