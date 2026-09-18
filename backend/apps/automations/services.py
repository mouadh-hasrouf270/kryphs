from django.db import transaction

from apps.automations.models import AutomationRule, AutomationRun, AutomationRunStep
from apps.common.models import Job
from apps.context_hub.models import CreativeProposal
from apps.notifications.models import Notification


def dispatch(event, obj):
    for rule in AutomationRule.objects.filter(
        workspace=obj.workspace, brand=obj.brand, enabled=True, event=event.action
    ):
        Job.objects.get_or_create(
            idempotency_key=f"automation:{rule.pk}:{event.pk}",
            defaults=dict(
                workspace=obj.workspace,
                brand=obj.brand,
                type="automation",
                payload={"rule": str(rule.pk), "event": str(event.pk), "creative": str(obj.pk)},
                created_by=event.actor,
            ),
        )


@transaction.atomic
def execute(job):
    from apps.creatives.models import Creative

    rule = AutomationRule.objects.get(pk=job.payload["rule"], workspace=job.workspace)
    if not rule.enabled:
        return
    creative = Creative.objects.get(
        pk=job.payload["creative"], workspace=job.workspace, brand=rule.brand
    )
    run, created = AutomationRun.objects.get_or_create(
        rule=rule,
        event_id=job.payload["event"],
        defaults={"workspace": job.workspace, "brand": job.brand},
    )
    if not created:
        return
    allowed = {"creative_type", "outcome", "status"}
    if any(k not in allowed or getattr(creative, k) != v for k, v in rule.conditions.items()):
        run.status = "skipped"
    elif rule.action == "refresh_recommendation":
        CreativeProposal.objects.create(
            workspace=job.workspace,
            brand=job.brand,
            title="Refresh: " + creative.title,
            source=creative,
            proposed_change="Review a refresh based on the recorded signal.",
            rationale=f"Automation {rule.pk}; event {run.event_id}",
        )
        run.status = "succeeded"
    elif rule.action == "notify":
        if creative.owner_id:
            Notification.objects.get_or_create(
                dedupe_key=f"automation:{run.pk}",
                defaults=dict(
                    workspace=job.workspace,
                    brand=job.brand,
                    user=creative.owner,
                    kind=rule.event,
                    title=creative.title,
                    link=f"/creatives/{creative.pk}",
                ),
            )
        run.status = "succeeded"
    else:
        raise ValueError("Unsupported automation action")
    run.save()
    AutomationRunStep.objects.create(
        workspace=job.workspace, brand=job.brand, run=run, action=rule.action, status=run.status
    )
