from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.workspaces.policies import require, validate_scope


@transaction.atomic
def transition(actor, experiment, action, data):
    require(actor, experiment.workspace_id, "manage_experiments")
    validate_scope(actor, experiment.workspace_id, experiment.brand)
    experiment = type(experiment).objects.get(pk=experiment.pk)
    target = {"start": "running", "complete": "completed", "cancel": "cancelled"}.get(action)
    if target not in {"draft": ["running", "cancelled"], "running": ["completed", "cancelled"]}.get(
        experiment.status, []
    ):
        raise ValidationError("Invalid experiment transition.")
    if target == "running" and (
        experiment.arms.count() < 2 or experiment.arms.filter(control=True).count() != 1
    ):
        raise ValidationError("Add at least two arms with exactly one control.")
    if target == "completed":
        if not data.get("learning", "").strip():
            raise ValidationError("Record the learning before completion.")
        for field in ["learning", "conclusion", "next_action", "limitations"]:
            setattr(experiment, field, data.get(field, ""))
        if data.get("winner"):
            winner = experiment.arms.filter(pk=data["winner"]).first()
            if not winner:
                raise ValidationError("Winner must be an arm of this experiment.")
            experiment.winner = winner
        experiment.end_date = timezone.now()
    if target == "running":
        experiment.start_date = timezone.now()
    experiment.status = target
    experiment.save()
    record(actor, experiment, "experiment_" + target)
    return experiment
