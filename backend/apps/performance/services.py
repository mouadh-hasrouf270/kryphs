from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.services import record
from apps.performance.models import OutcomeHistory
from apps.workspaces.policies import require, validate_scope


def normalized(data):
    def n(key):
        return Decimal(str(data.get(key, 0)))

    def ratio(a, b, scale=1):
        return float(a / b * scale) if b else None

    return {
        "ctr": ratio(n("clicks"), n("impressions"), 100),
        "cpc": ratio(n("spend"), n("clicks")),
        "cpm": ratio(n("spend"), n("impressions"), 1000),
        "cpa": ratio(n("spend"), n("conversions")),
        "roas": ratio(n("revenue"), n("spend")),
        "frequency": ratio(n("impressions"), n("reach")),
    }


def fatigue(snapshots, settings=None):
    cfg = {
        "minimum_impressions": 100,
        "ctr_drop": 0.25,
        "roas_drop": 0.25,
        "cpa_rise": 0.30,
        "frequency": 2.5,
    } | (settings or {})
    if len(snapshots) < 2:
        return []
    recent, previous = snapshots[:2]
    if recent.currency != previous.currency or recent.provider != previous.provider:
        return []
    spans = [(x.interval_end - x.interval_start).total_seconds() for x in [recent, previous]]
    if not max(spans) or abs(spans[0] - spans[1]) / max(spans) > 0.2:
        return []
    if min(recent.impressions, previous.impressions) < cfg["minimum_impressions"]:
        return []
    result = []
    for metric, threshold, sign in [
        ("ctr", cfg["ctr_drop"], -1),
        ("roas", cfg["roas_drop"], -1),
        ("cpa", cfg["cpa_rise"], 1),
    ]:
        a, b = recent.metrics.get(metric), previous.metrics.get(metric)
        if a is not None and b and sign * (a - b) / b >= threshold:
            result.append({"metric": metric, "change_percent": round((a - b) / b * 100, 2)})
    if result and (recent.metrics.get("frequency") or 0) >= cfg["frequency"]:
        result.append({"metric": "frequency", "value": recent.metrics["frequency"]})
    return result


@transaction.atomic
def outcome(actor, creative, value, reason):
    require(actor, creative.workspace_id, "mark_winner")
    validate_scope(actor, creative.workspace_id, creative.brand)
    if (
        value not in ["winner", "loser", "neutral", "fatigued", "refresh_requested"]
        or not reason.strip()
    ):
        raise ValidationError("Choose an outcome and provide supporting reasoning.")
    obj = OutcomeHistory.objects.create(
        workspace=creative.workspace,
        brand=creative.brand,
        creative=creative,
        outcome=value,
        reason=reason,
        actor=actor,
    )
    creative.outcome = value
    creative.save(update_fields=["outcome", "updated_at"])
    event = record(actor, creative, value, {"reason": reason})
    from apps.automations.services import dispatch

    dispatch(event, creative)
    return obj
