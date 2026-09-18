from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.models import Job
from apps.creatives.models import Creative
from apps.performance.models import Deployment
from apps.requests_app.models import CreativeRequest, RequestDeliverable
from apps.workspaces.policies import membership, require, scope


class TasksView(APIView):
    def get(self, request):
        ws = request.query_params.get("workspace")
        require(request.user, ws, "view_creatives")
        member = membership(request.user, ws)
        role = member.role if member else "manager"
        now = timezone.now()
        requests = scope(CreativeRequest.objects.all(), request.user, ws)
        deliverables = scope(RequestDeliverable.objects.select_related("request"), request.user, ws)
        creatives = scope(Creative.objects.select_related("request"), request.user, ws).filter(
            archived_at__isnull=True
        )
        result = []

        def add(query, kind, reason):
            for obj in query.order_by("created_at")[:100]:
                parent = obj.request if kind in ["deliverable", "creative"] else obj
                due = getattr(obj, "due_date", None) or getattr(parent, "due_date", None)
                route = (
                    f"/requests/{obj.request_id}"
                    if kind == "deliverable"
                    else f"/requests/{obj.pk}"
                    if kind == "request"
                    else f"/creatives/{obj.pk}"
                    if kind == "creative"
                    else "/operations"
                )
                result.append(
                    {
                        "id": str(obj.pk),
                        "kind": kind,
                        "title": getattr(obj, "title", None) or getattr(obj, "type", kind),
                        "status": obj.status,
                        "reason": reason,
                        "due_date": due,
                        "overdue": bool(due and due < now),
                        "priority": getattr(parent, "priority", "normal"),
                        "href": route,
                    }
                )

        active = ["new", "assigned", "in_production", "changes_requested", "refresh_requested"]
        if role == "editor":
            add(
                deliverables.filter(assigned_editor=request.user, status__in=active),
                "deliverable",
                "assigned_work",
            )
            add(
                creatives.filter(owner=request.user, status__in=active), "creative", "assigned_work"
            )
        elif role == "reviewer":
            add(creatives.filter(status="ready_for_review"), "creative", "review_queue")
        elif role == "requester":
            add(
                requests.filter(requester=request.user).filter(
                    Q(status__in=active + ["ready_for_review"])
                    | Q(completed_at__gte=now - timedelta(days=7))
                ),
                "request",
                "my_requests",
            )
        elif role == "media_buyer":
            deployments = scope(Deployment.objects.all(), request.user, ws)
            add(
                creatives.filter(status="approved").exclude(
                    pk__in=deployments.values("creative_id")
                ),
                "creative",
                "approved_undeployed",
            )
            add(
                creatives.filter(outcome__in=["fatigued", "refresh_requested"]),
                "creative",
                "fatigue_attention",
            )
            jobs = scope(Job.objects.all(), request.user, ws)
            add(
                jobs.filter(type__in=["publish", "google_upload"], status="failed"),
                "job",
                "publish_attention",
            )
            for dep in deployments.filter(state="active").filter(
                Q(last_sync__isnull=True) | Q(last_sync__lt=now - timedelta(days=2))
            )[:100]:
                result.append(
                    {
                        "id": str(dep.pk),
                        "kind": "deployment",
                        "title": dep.title,
                        "status": dep.state,
                        "reason": "stale_sync",
                        "href": "/performance",
                        "overdue": False,
                    }
                )
        elif role == "manager":
            add(requests.filter(owner__isnull=True, status__in=active), "request", "unassigned")
            add(
                deliverables.filter(
                    Q(assigned_editor__isnull=True)
                    | Q(due_date__lt=now)
                    | Q(status="changes_requested")
                ).exclude(status__in=["approved", "published"]),
                "deliverable",
                "needs_attention",
            )
            add(
                creatives.filter(status__in=["ready_for_review", "changes_requested"]),
                "creative",
                "review_queue",
            )
        # Production responsibilities add discoverability, not mutation permissions.
        assigned = (
            deliverables.filter(assignments__user=request.user)
            .exclude(status__in=["approved", "published"])
            .distinct()
        )
        existing = {row["id"] for row in result if row["kind"] == "deliverable"}
        add(assigned.exclude(pk__in=existing), "deliverable", "production_assignment")
        result.sort(
            key=lambda row: (not row.get("overdue", False), row.get("priority") != "urgent")
        )
        counts = {
            key: sum(row["kind"] == key for row in result)
            for key in ["request", "deliverable", "creative", "job", "deployment"]
        }
        return Response(
            {"role": role, "results": result, "counts": counts, "limited": len(result) >= 100}
        )
