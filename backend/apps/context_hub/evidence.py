from django.db.models import Count
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.creatives.models import Creative
from apps.performance.models import Deployment, PerformanceSnapshot
from apps.performance.services import fatigue
from apps.workspaces.policies import require, scope


class EvidenceView(APIView):
    def get(self, request):
        workspace = request.query_params.get("workspace")
        require(request.user, workspace, "view_analytics")
        creatives = scope(
            Creative.objects.filter(archived_at__isnull=True), request.user, workspace
        )
        for field in ["brand", "product", "campaign", "creative_type", "outcome"]:
            if request.query_params.get(field):
                creatives = creatives.filter(**{field: request.query_params[field]})
        if request.query_params.get("q"):
            creatives = creatives.filter(title__icontains=request.query_params["q"][:200])
        rows = []
        signals = []
        for creative in creatives.order_by("-created_at")[:100]:
            deployments = scope(
                Deployment.objects.filter(creative=creative), request.user, workspace
            )
            snapshots = scope(
                PerformanceSnapshot.objects.filter(deployment__in=deployments),
                request.user,
                workspace,
            )
            currencies = list(snapshots.values_list("currency", flat=True).distinct())
            # Do not add overlapping windows or mix currencies into fictitious totals.
            recent = snapshots.order_by("-interval_end").first()
            rows.append(
                {
                    "id": str(creative.pk),
                    "title": creative.title,
                    "creative_type": creative.creative_type,
                    "outcome": creative.outcome,
                    "sample_size": snapshots.count(),
                    "latest_metrics": recent.metrics if recent else {},
                    "currency": recent.currency if recent else None,
                    "interval_start": recent.interval_start if recent else None,
                    "interval_end": recent.interval_end if recent else None,
                    "currencies": currencies,
                }
            )
            for deployment in deployments:
                recent_two = list(
                    snapshots.filter(deployment=deployment).order_by("-interval_end")[:2]
                )
                found = fatigue(recent_two, creative.workspace.settings.get("fatigue", {}))
                if found:
                    signals.append(
                        {
                            "creative_id": str(creative.pk),
                            "title": creative.title,
                            "deployment_id": str(deployment.pk),
                            "signals": found,
                        }
                    )
        groups = list(
            creatives.values("creative_type", "outcome")
            .annotate(sample_size=Count("id"))
            .order_by("creative_type", "outcome")
        )
        return Response(
            {
                "results": rows,
                "groups": groups,
                "fatigue": signals,
                "limitations": "Observational evidence. Sample sizes and observation windows are shown; results do not establish causality.",
            }
        )
