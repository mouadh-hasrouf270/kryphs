import pytest

from apps.creatives.services import new_version, transition
from apps.performance.models import Deployment
from apps.requests_app.models import CreativeRequest, RequestDeliverable


def endpoint(team, route):
    return f"/api/v1/{route}/?workspace={team['ws'].pk}"


@pytest.mark.parametrize(
    "role", ["editor", "reviewer", "requester", "media_buyer", "manager", "viewer"]
)
def test_tasks_are_role_specific(team, client_for, role):
    p = team["people"]
    creative = team["creative"]
    d = RequestDeliverable.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        request=team["request"],
        sequence=1,
        title="Assigned task",
        assigned_editor=p["editor"],
        status="assigned",
    )
    creative.deliverable = d
    creative.save()
    new_version(p["editor"], creative)
    transition(p["editor"], creative, "submit")
    if role == "media_buyer":
        transition(p["reviewer"], creative, "approve")
    r = client_for(p[role]).get(endpoint(team, "tasks"))
    assert r.status_code == 200, r.content
    ids = {row["id"] for row in r.json()["results"]}
    if role == "viewer":
        assert not ids
    elif role == "requester":
        assert str(team["request"].pk) in ids
    elif role == "editor":
        # Submitted work leaves the production queue until changes are requested.
        transition(p["reviewer"], creative, "request-changes", "Fix hook")
        rows = client_for(p[role]).get(endpoint(team, "tasks")).json()["results"]
        assert str(creative.pk) in {row["id"] for row in rows}
    else:
        assert str(creative.pk) in ids


def test_duplicate_request_submission_returns_same_aggregate(team, client_for):
    c = client_for(team["people"]["requester"])
    data = {
        "brand": str(team["brand"].pk),
        "title": "One submission",
        "deliverables": [{"title": "One item"}],
    }
    a = c.post(endpoint(team, "requests"), data, format="json", HTTP_IDEMPOTENCY_KEY="same-key")
    b = c.post(endpoint(team, "requests"), data, format="json", HTTP_IDEMPOTENCY_KEY="same-key")
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] == b.json()["id"]
    assert CreativeRequest.objects.get(pk=a.json()["id"]).deliverables.count() == 1
    data["title"] = "Changed"
    assert (
        c.post(
            endpoint(team, "requests"), data, format="json", HTTP_IDEMPOTENCY_KEY="same-key"
        ).status_code
        == 400
    )


def test_confirmed_deployment_identity_is_immutable(team, client_for):
    p = team["people"]
    v = new_version(p["editor"], team["creative"])
    transition(p["editor"], team["creative"], "submit")
    transition(p["reviewer"], team["creative"], "approve")
    dep = Deployment.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        title="Receipt",
        creative=team["creative"],
        version=v,
        provider="meta",
        ad_id="confirmed-id",
    )
    c = client_for(p["media_buyer"])
    for field, value in [
        ("ad_id", "replacement"),
        ("provider", "manual"),
        ("campaign_id", "changed"),
    ]:
        assert (
            c.patch(
                endpoint(team, f"deployments/{dep.pk}"), {field: value}, format="json"
            ).status_code
            == 400
        )
    assert (
        c.patch(
            endpoint(team, f"deployments/{dep.pk}"), {"title": "Better label"}, format="json"
        ).status_code
        == 200
    )


def test_reset_unavailable_is_explicit_without_account_enumeration(team, client_for, settings):
    settings.PASSWORD_RESET_ENABLED = False
    c = client_for(team["people"]["manager"])
    for email in ["manager@example.test", "missing@example.test"]:
        assert c.post("/api/v1/auth/reset/", {"email": email}, format="json").status_code == 503


def test_proposal_acceptance_is_single_and_historical(team, client_for):
    from apps.context_hub.models import CreativeProposal

    obj = CreativeProposal.objects.create(
        workspace=team["ws"], brand=team["brand"], title="Variant idea", source=team["creative"]
    )
    c = client_for(team["people"]["manager"])
    result = c.post(endpoint(team, f"proposals/{obj.pk}/actions/accept"), {}, format="json")
    assert result.status_code == 200, result.content
    obj.refresh_from_db()
    assert obj.resulting_creative_id
    assert (
        c.post(endpoint(team, f"proposals/{obj.pk}/actions/accept"), {}, format="json").status_code
        == 400
    )
