from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.models import Activity, AuditEvent
from apps.automations.models import AutomationRule, AutomationRun
from apps.common.jobs import claim, run_once
from apps.common.models import Job
from apps.creatives.models import CreativeFeedback, CreativeVersion
from apps.creatives.services import new_version, related, transition
from apps.experiments.models import Experiment, ExperimentArm
from apps.experiments.services import transition as experiment_transition
from apps.integrations.crypto import seal, unseal
from apps.integrations.models import AdConnection, PublishJob, PublishStep
from apps.integrations.services import MetaPublishingProvider, destination_url, provider
from apps.notifications.models import Notification
from apps.performance.models import Deployment, OutcomeHistory, PerformanceSnapshot
from apps.performance.services import fatigue, normalized, outcome
from apps.requests_app.models import RequestDeliverable
from apps.requests_app.services import start
from apps.storage.google import ProviderFailure, safe_session, upsert
from apps.storage.models import StorageConnection, StorageObject
from apps.storage.services import master, upload_local


def test_full_lifecycle_and_immutable_history(team):
    c = team["creative"]
    people = team["people"]
    start(people["editor"], c)
    v1 = new_version(people["editor"], c, "Original")
    transition(people["editor"], c, "submit")
    with pytest.raises(ValidationError):
        transition(people["reviewer"], c, "request-changes", "")
    transition(people["reviewer"], c, "request-changes", "Change the hook")
    v2 = new_version(people["editor"], c, "New hook")
    transition(people["editor"], c, "submit")
    transition(people["reviewer"], c, "approve")
    c.refresh_from_db()
    v1.refresh_from_db()
    v2.refresh_from_db()
    assert v1.status == "changes_requested" and v2.status == "approved"
    assert c.approved_version_id == v2.pk and v2.version_number == 2
    assert CreativeFeedback.objects.count() == 2
    assert AuditEvent.objects.filter(action="approved").exists()
    assert Activity.objects.count() > 0 and Notification.objects.count() > 0
    with pytest.raises(ValidationError):
        transition(people["reviewer"], c, "approve")


def test_sibling_does_not_approve_whole_request(team):
    req = team["request"]
    c = team["creative"]
    p = team["people"]
    d1 = RequestDeliverable.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        request=req,
        sequence=1,
        title="One",
        status="in_production",
    )
    RequestDeliverable.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        request=req,
        sequence=2,
        title="Two",
        status="in_production",
    )
    c.deliverable = d1
    c.save()
    new_version(p["editor"], c)
    transition(p["editor"], c, "submit")
    transition(p["reviewer"], c, "approve")
    req.refresh_from_db()
    d1.refresh_from_db()
    assert req.status == "in_production" and d1.status == "approved"


def test_unassigned_editor_cannot_submit(team):
    from apps.accounts.models import User
    from apps.workspaces.models import WorkspaceMembership

    other = User.objects.create_user("other@example.test", "PassWord!123")
    WorkspaceMembership.objects.create(workspace=team["ws"], user=other, role="editor")
    with pytest.raises(PermissionDenied):
        new_version(other, team["creative"])


def test_version_unique_constraint(team):
    v = new_version(team["people"]["editor"], team["creative"])
    with pytest.raises(IntegrityError), transaction.atomic():
        CreativeVersion.objects.create(
            workspace=team["ws"],
            brand=team["brand"],
            creative=team["creative"],
            editor=team["people"]["editor"],
            version_number=v.version_number,
        )


def test_upload_signature_and_deterministic_master(team):
    c = team["creative"]
    p = team["people"]
    version = new_version(p["editor"], c)
    c.refresh_from_db()
    with pytest.raises(ValidationError):
        upload_local(
            p["editor"], c, SimpleUploadedFile("fake.png", b"<script>alert(1)</script>"), "master"
        )
    buffer = BytesIO()
    Image.new("RGB", (10, 20)).save(buffer, "PNG")
    obj = upload_local(p["editor"], c, SimpleUploadedFile("image.png", buffer.getvalue()), "master")
    assert obj.width == 10 and obj.height == 20 and obj.checksum
    with pytest.raises(ValidationError):
        master(version)
    transition(p["editor"], c, "submit")
    transition(p["reviewer"], c, "approve")
    version.refresh_from_db()
    assert master(version) == obj
    c.refresh_from_db()
    with pytest.raises(ValidationError):
        upload_local(p["editor"], c, SimpleUploadedFile("image.png", buffer.getvalue()), "master")


def test_drive_identity_survives_rename_and_move(team):
    connection = StorageConnection.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        name="Test fixture",
        created_by=team["people"]["manager"],
    )
    a = upsert(
        connection, {"id": "confirmed-provider-file", "name": "Before", "parents": ["folder-1"]}
    )
    b = upsert(
        connection, {"id": "confirmed-provider-file", "name": "After", "parents": ["folder-2"]}
    )
    assert a.pk == b.pk and b.filename == "After" and b.parents == ["folder-2"]
    assert StorageObject.objects.count() == 1


def test_encryption_and_provider_registry():
    encrypted = seal({"refresh_token": "secret-example"})
    assert "secret-example" not in encrypted
    assert unseal(encrypted)["refresh_token"] == "secret-example"
    for name in ["mock", "test", "tiktok", "google_ads"]:
        with pytest.raises(ProviderFailure):
            provider(name)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://localhost/a",
        "https://127.0.0.1/",
        "https://user:pass@example.com",
        "javascript:alert(1)",
    ],
)
def test_destination_validation(url):
    with pytest.raises(ValidationError):
        destination_url(url)


def test_session_url_allowlist():
    assert safe_session("https://www.googleapis.com/upload?x=y")
    with pytest.raises(ProviderFailure):
        safe_session("https://evil.example/upload")


def test_performance_normalization_and_history(team):
    assert normalized(
        {"spend": 10, "impressions": 1000, "clicks": 20, "conversions": 2, "revenue": 30}
    ) == {"ctr": 2.0, "cpc": 0.5, "cpm": 10.0, "cpa": 5.0, "roas": 3.0, "frequency": None}
    assert normalized({})["roas"] is None
    c = team["creative"]
    actor = team["people"]["manager"]
    outcome(actor, c, "winner", "Strong results")
    outcome(actor, c, "fatigued", "CTR fell")
    assert OutcomeHistory.objects.count() == 2


def test_fatigue_compares_compatible_windows(team):
    c = team["creative"]
    v = new_version(team["people"]["editor"], c)
    d = Deployment.objects.create(
        workspace=team["ws"], brand=team["brand"], creative=c, version=v, title="Manual"
    )
    now = timezone.now()
    base = PerformanceSnapshot.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        deployment=d,
        interval_start=now - timedelta(days=2),
        interval_end=now - timedelta(days=1),
        impressions=1000,
        metrics={"ctr": 4, "roas": 3, "cpa": 10},
    )
    recent = PerformanceSnapshot.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        deployment=d,
        interval_start=now - timedelta(days=1),
        interval_end=now,
        impressions=1000,
        metrics={"ctr": 2, "roas": 2, "cpa": 15, "frequency": 3},
    )
    assert len(fatigue([recent, base])) == 4
    recent.currency = "EUR"
    assert fatigue([recent, base]) == []


def test_experiment_requires_arms_and_learning(team):
    actor = team["people"]["manager"]
    c = team["creative"]
    child = related(actor, c, {"title": "Variant", "hypothesis": "New hook"})
    exp = Experiment.objects.create(workspace=team["ws"], brand=team["brand"], title="Hook test")
    with pytest.raises(ValidationError):
        experiment_transition(actor, exp, "start", {})
    for creative, control in [(c, True), (child, False)]:
        ExperimentArm.objects.create(
            workspace=team["ws"],
            brand=team["brand"],
            experiment=exp,
            creative=creative,
            control=control,
            name=creative.title,
        )
    experiment_transition(actor, exp, "start", {})
    with pytest.raises(ValidationError):
        experiment_transition(actor, exp, "complete", {})
    result = experiment_transition(
        actor, exp, "complete", {"learning": "Sample was too small for a firm conclusion."}
    )
    assert result.status == "completed"


def test_automation_idempotency(team):
    actor = team["people"]["manager"]
    c = team["creative"]
    rule = AutomationRule.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        name="Notify",
        event="approved",
        action="notify",
        created_by=actor,
    )
    job = Job.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        type="automation",
        payload={"rule": str(rule.pk), "event": "event-1", "creative": str(c.pk)},
        idempotency_key="automation-test",
    )
    from apps.automations.services import execute

    execute(job)
    execute(job)
    assert AutomationRun.objects.count() == 1
    assert Notification.objects.filter(kind="approved").count() == 1


def test_job_atomic_claim_and_retry(team):
    j = Job.objects.create(workspace=team["ws"], type="unsupported", idempotency_key="one")
    assert claim().pk == j.pk
    assert claim() is None
    j.status = "queued"
    j.save(update_fields=["status"])
    assert run_once()
    j.refresh_from_db()
    assert j.status == "queued" and j.attempts == 2 and j.available_at > timezone.now()


def test_uncertain_meta_write_is_never_replayed(team):
    c = team["creative"]
    v = new_version(team["people"]["editor"], c)
    connection = AdConnection.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        name="Fixture",
        provider="meta",
        created_by=team["people"]["manager"],
    )
    job = PublishJob.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        creative=c,
        version=v,
        connection=connection,
        provider="meta",
        requested_by=team["people"]["manager"],
        idempotency_key="test",
    )
    PublishStep.objects.create(
        workspace=team["ws"],
        brand=team["brand"],
        job=job,
        operation="ad.create",
        sequence=1,
        status="running",
    )
    with patch("apps.integrations.services.httpx.post") as network:
        with pytest.raises(ProviderFailure):
            MetaPublishingProvider().step(
                job, "ad.create", 1, "https://graph.facebook.com/unused", {}, {}
            )
        network.assert_not_called()


def test_deadline_notifications_deduplicate(team):
    from apps.notifications.services import scan_deadlines

    request = team["request"]
    request.due_date = timezone.now() - timedelta(hours=1)
    request.save()
    assert scan_deadlines() == 2
    assert scan_deadlines() == 0
    assert Notification.objects.filter(kind="overdue").count() == 2
