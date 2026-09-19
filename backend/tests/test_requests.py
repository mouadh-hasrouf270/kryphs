import pytest

from apps.catalog.models import Campaign, Platform, Product
from apps.creatives.models import Creative
from apps.requests_app.models import CreativeRequest, RequestDeliverable
from apps.requests_app.services import recalculate_deliverable, recalculate_request


def url(team, route):
    return f"/api/v1/{route}/?workspace={team['ws'].pk}"


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"objective": "Awareness", "details": "Full brief"},
        {"priority": "urgent"},
        {"due_date": "2027-01-01T10:00:00Z"},
    ],
)
def test_request_real_fields(team, client_for, extra):
    c = client_for(team["people"]["requester"])
    r = c.post(
        url(team, "requests"),
        {"title": "حملة جديدة", "brand": str(team["brand"].pk), **extra},
        format="json",
    )
    assert r.status_code == 201, r.content


def test_request_atomic_children_platform_edit_and_catalog(team, client_for):
    p1 = Platform.objects.get_or_create(slug="meta", defaults={"name": "Meta"})[0]
    p2 = Platform.objects.get_or_create(slug="tiktok", defaults={"name": "TikTok"})[0]
    product = Product.objects.create(workspace=team["ws"], brand=team["brand"], name="Product")
    campaign = Campaign.objects.create(workspace=team["ws"], brand=team["brand"], name="Campaign")
    c = client_for(team["people"]["manager"])
    data = {
        "title": "Full aggregate",
        "brand": str(team["brand"].pk),
        "platforms": [str(p1.pk), str(p2.pk)],
        "product": str(product.pk),
        "campaign": str(campaign.pk),
        "owner": str(team["people"]["editor"].pk),
        "deliverables": [
            {
                "title": "Video",
                "quantity": 1,
                "platform": str(p1.pk),
                "requirements": "Arabic",
                "duration_target": 30,
            },
            {"title": "Image", "creative_type": "image"},
        ],
    }
    r = c.post(url(team, "requests"), data, format="json")
    assert r.status_code == 201, r.content
    obj = CreativeRequest.objects.get(pk=r.json()["id"])
    assert obj.deliverables.count() == 2
    child = obj.deliverables.get(sequence=1)
    assert child.quantity == 1 and child.duration_target == 30 and child.requirements == "Arabic"
    assert child.assigned_editor == team["people"]["editor"]
    for ids in [[str(p2.pk)], []]:
        r = c.patch(url(team, f"requests/{obj.pk}"), {"platforms": ids}, format="json")
        assert r.status_code == 200, r.content
        assert c.get(url(team, f"requests/{obj.pk}")).json()["platforms"] == ids
    data["deliverables"][1]["quantity"] = 0
    count = CreativeRequest.objects.count()
    assert c.post(url(team, "requests"), data, format="json").status_code == 400
    assert CreativeRequest.objects.count() == count


@pytest.mark.parametrize("field", ["product", "campaign", "platforms", "owner"])
def test_invalid_relation_is_validation_error(team, client_for, field):
    c = client_for(team["people"]["manager"])
    data = {
        "title": "Invalid",
        "brand": str(team["brand"].pk),
        field: ["invalid"] if field == "platforms" else "invalid",
    }
    assert c.post(url(team, "requests"), data, format="json").status_code == 400


@pytest.mark.parametrize("model,field", [(Product, "product"), (Campaign, "campaign")])
def test_catalog_brand_must_match(team, client_for, model, field):
    other = model.objects.create(workspace=team["ws"], brand=team["restricted"], name="Other")
    r = client_for(team["people"]["requester"]).post(
        url(team, "requests"),
        {"title": "Wrong brand", "brand": str(team["brand"].pk), field: str(other.pk)},
        format="json",
    )
    assert r.status_code == 400


def test_requester_cannot_assign_nested_editor(team, client_for):
    r = client_for(team["people"]["requester"]).post(
        url(team, "requests"),
        {
            "title": "No assignment",
            "brand": str(team["brand"].pk),
            "deliverables": [
                {"title": "Video", "assigned_editor": str(team["people"]["editor"].pk)}
            ],
        },
        format="json",
    )
    assert r.status_code == 403


def test_bound_creative_and_parent_start(team, client_for):
    c = client_for(team["people"]["manager"])
    r = c.post(
        url(team, "requests"),
        {
            "title": "Bound",
            "brand": str(team["brand"].pk),
            "deliverables": [{"title": "A"}, {"title": "B"}],
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    obj = CreativeRequest.objects.get(pk=r.json()["id"])
    assert (
        c.post(
            url(team, "creatives"),
            {"title": "Bypass", "brand": str(team["brand"].pk), "request": str(obj.pk)},
            format="json",
        ).status_code
        == 400
    )
    assert (
        c.post(
            url(team, f"requests/{obj.pk}/actions/assign"),
            {"editor": str(team["people"]["editor"].pk)},
            format="json",
        ).status_code
        == 200
    )
    assert (
        c.post(
            url(team, f"requests/{obj.pk}/actions/start-production"), {}, format="json"
        ).status_code
        == 200
    )
    assert set(obj.deliverables.values_list("status", flat=True)) == {"in_production"}
    child = obj.deliverables.first()
    editor = client_for(team["people"]["editor"])
    r = editor.post(
        url(team, f"deliverables/{child.pk}/actions/create-creative"), {}, format="json"
    )
    assert r.status_code == 201, r.content
    creative = Creative.objects.get(pk=r.json()["id"])
    assert creative.request == obj and creative.deliverable == child and creative.brand == obj.brand
    creative.status = "approved"
    creative.save()
    recalculate_deliverable(child)
    recalculate_request(obj)
    assert obj.status == "in_production"


@pytest.mark.parametrize(
    "quantity,states,expected",
    [
        (1, ["approved"], "approved"),
        (2, ["approved"], "in_production"),
        (3, ["approved"], "in_production"),
        (3, ["approved"] * 3, "approved"),
        (2, ["approved", "in_production"], "in_production"),
        (2, ["approved", "changes_requested"], "changes_requested"),
        (2, ["published"] * 2, "published"),
        (2, ["ready_for_review"], "in_production"),
        (2, ["ready_for_review", "approved"], "ready_for_review"),
    ],
)
def test_quantity(team, quantity, states, expected):
    # Legacy quantities now become individual deliverables; preserve request precedence.
    children = []
    for i in range(quantity):
        child = RequestDeliverable.objects.create(
            workspace=team["ws"],
            brand=team["brand"],
            request=team["request"],
            sequence=i + 1,
            quantity=1,
        )
        children.append(child)
        if i < len(states):
            Creative.objects.create(
                workspace=team["ws"],
                brand=team["brand"],
                request=team["request"],
                deliverable=child,
                code=f"Q-{i}",
                status=states[i],
            )
        recalculate_deliverable(child)
    assert recalculate_request(team["request"]).status == expected
    if expected == "approved":
        from django.utils import timezone

        Creative.objects.filter(deliverable__in=children).update(archived_at=timezone.now())
        for child in children:
            recalculate_deliverable(child)
        assert recalculate_request(team["request"]).status == "approved"


def test_add_deliverable_after_request_creation_assigns_sequence_server_side(team, client_for):
    """Request-detail Add Deliverable must not require a client sequence."""
    c = client_for(team["people"]["manager"])
    created = c.post(
        url(team, "requests"),
        {"title": "Add children later", "brand": str(team["brand"].pk)},
        format="json",
    )
    assert created.status_code == 201, created.content
    request_id = created.json()["id"]

    first = c.post(
        url(team, "deliverables"),
        {
            "request": request_id,
            "brand": str(team["brand"].pk),
            "title": "Video 9:16",
            "creative_type": "video",
            "quantity": 1,
        },
        format="json",
    )
    assert first.status_code == 201, first.content
    assert first.json()["sequence"] == 1

    # A client-provided sequence is ignored: ordering belongs to the server.
    second = c.post(
        url(team, "deliverables"),
        {
            "request": request_id,
            "brand": str(team["brand"].pk),
            "title": "Static 1:1",
            "creative_type": "image",
            "quantity": 1,
            "sequence": 99,
        },
        format="json",
    )
    assert second.status_code == 201, second.content
    assert second.json()["sequence"] == 2

    rows = RequestDeliverable.objects.filter(request_id=request_id).order_by("sequence")
    assert list(rows.values_list("sequence", flat=True)) == [1, 2]
