from django.apps import apps
from django.db import models, transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.audit.services import record
from apps.common.resources import APPEND_ONLY, DEFINITIONS, HIDDEN, PROTECTED, READ_ONLY
from apps.common.serializers import serializer_for
from apps.workspaces.models import Workspace, WorkspaceMembership
from apps.workspaces.policies import membership, permissions, require, scope


class ScopedViewSet(viewsets.ModelViewSet):
    resource = ""
    http_method_names = ["get", "post", "patch", "head", "options"]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        self.check_write()
        key = request.headers.get("Idempotency-Key") if self.resource == "requests" else None
        if key:
            import hashlib
            import json

            if len(key) > 100:
                raise ValidationError("Idempotency key is too long.")
            digest = hashlib.sha256(json.dumps(request.data, sort_keys=True).encode()).hexdigest()
            from apps.requests_app.models import CreativeRequest

            existing = (
                self.get_queryset().filter(requester=request.user, submission_key=key).first()
            )
            if existing:
                if existing.submission_hash != digest:
                    raise ValidationError(
                        "This submission key was already used for different request data."
                    )
                return Response(self.get_serializer(existing).data, status=201)
        result = super().create(request, *args, **kwargs)
        if key:
            CreativeRequest.objects.filter(pk=result.data["id"]).update(
                submission_key=key, submission_hash=digest
            )
        return result

    def partial_update(self, request, *args, **kwargs):
        self.check_write()
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        if self.resource != "notifications":
            raise ValidationError("Unsupported action.")
        updated = self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"updated": updated})

    @property
    def workspace_id(self):
        ws = self.request.query_params.get("workspace") or self.request.headers.get(
            "X-Workspace-ID"
        )
        if not ws:
            raise ValidationError({"workspace": "Select a workspace."})
        membership(self.request.user, ws)
        return ws

    def get_queryset(self):
        model = apps.get_model(DEFINITIONS[self.resource][0])
        require(self.request.user, self.workspace_id, DEFINITIONS[self.resource][2])
        qs = scope(model.objects.all(), self.request.user, self.workspace_id)
        if self.resource == "notifications":
            qs = qs.filter(user=self.request.user)
        for f in model._meta.fields:
            if f.name in HIDDEN or f.name == "workspace":
                continue
            if f.name in self.request.query_params and (
                f.is_relation or f.choices or f.name in ["priority", "outcome", "object_id"]
            ):
                try:
                    qs = qs.filter(**{f.name: self.request.query_params[f.name]})
                except (ValueError, TypeError):
                    raise ValidationError("Invalid filter.") from None
        if self.request.query_params.get("mine") == "true":
            if self.resource == "requests":
                qs = qs.filter(Q(owner=self.request.user) | Q(requester=self.request.user))
            elif self.resource == "creatives":
                qs = qs.filter(owner=self.request.user)
        q = self.request.query_params.get("q", "").strip()[:200]
        if q:
            condition = Q()
            for f in model._meta.fields:
                if isinstance(f, (models.CharField, models.TextField)) and f.name not in HIDDEN:
                    condition |= Q(**{f.name + "__icontains": q})
            qs = qs.filter(condition)
        return qs.order_by("-created_at")

    def get_serializer_class(self):
        if self.resource == "deliverable-assignments":
            from apps.requests_app.serializers import RequestDeliverableAssignmentSerializer

            return RequestDeliverableAssignmentSerializer
        if self.resource == "requests":
            from apps.requests_app.serializers import (
                CreativeRequestCreateSerializer,
                CreativeRequestUpdateSerializer,
            )

            return (
                CreativeRequestUpdateSerializer
                if self.action == "partial_update"
                else CreativeRequestCreateSerializer
            )
        if self.resource == "deliverables":
            from apps.requests_app.serializers import RequestDeliverableSerializer

            return RequestDeliverableSerializer
        return serializer_for(apps.get_model(DEFINITIONS[self.resource][0]))

    def get_serializer_context(self):
        return super().get_serializer_context() | {"workspace": self.workspace_id}

    def check_write(self):
        if self.resource == "deliverable-assignments":
            granted = permissions(self.request.user, self.workspace_id)
            if not {"assign_editors", "create_requests"} & granted:
                raise PermissionDenied("You cannot manage deliverable assignments.")
            return
        if self.resource in READ_ONLY:
            raise PermissionDenied("This history is managed through domain actions.")
        require(self.request.user, self.workspace_id, DEFINITIONS[self.resource][1])

    @transaction.atomic
    def perform_create(self, serializer):
        self.check_write()
        if self.resource == "deliverable-assignments":
            from apps.requests_app.assignments import save_assignment

            serializer.instance = save_assignment(self.request.user, serializer.validated_data)
            return
        kwargs = {"workspace_id": self.workspace_id}
        model = serializer.Meta.model
        for field in ["author", "actor", "created_by"]:
            if any(f.name == field for f in model._meta.fields):
                kwargs[field] = self.request.user
        if self.resource == "requests":
            from apps.requests_app.services import create_request

            serializer.instance = create_request(
                self.request.user,
                dict(
                    serializer.validated_data, workspace=Workspace.objects.get(pk=self.workspace_id)
                ),
            )
            return
        if self.resource == "creatives":
            from apps.creatives.services import create_creative

            serializer.instance = create_creative(
                self.request.user,
                dict(
                    serializer.validated_data, workspace=Workspace.objects.get(pk=self.workspace_id)
                ),
            )
            return
        if self.resource == "performance":
            from apps.performance.services import normalized

            kwargs["metrics"] = normalized(serializer.validated_data)
        if self.resource == "deliverables":
            from django.db.models import Max

            from apps.requests_app.models import CreativeRequest

            # Sequence is server-owned. Lock the parent row so two concurrent
            # creates cannot intentionally receive the same next position on
            # databases that support row-level locking. SQLite serializes writes
            # and the database unique constraint remains the final safeguard.
            parent = CreativeRequest.objects.select_for_update().get(
                pk=serializer.validated_data["request"].pk
            )
            if parent.requester_id != self.request.user.pk and "assign_editors" not in permissions(
                self.request.user, self.workspace_id
            ):
                raise PermissionDenied("Only the requester or manager may add deliverables.")
            kwargs["request"] = parent
            kwargs["sequence"] = (parent.deliverables.aggregate(n=Max("sequence"))["n"] or 0) + 1
        obj = serializer.save(**kwargs)
        if self.resource == "deliverables":
            from apps.requests_app.assignments import sync_primary
            from apps.requests_app.services import recalculate_deliverable, recalculate_request

            sync_primary(obj)
            recalculate_deliverable(obj)
            recalculate_request(obj.request)
        record(self.request.user, obj, "created")

    @transaction.atomic
    def perform_update(self, serializer):
        self.check_write()
        if self.resource == "deliverable-assignments":
            from apps.requests_app.assignments import save_assignment

            serializer.instance = save_assignment(
                self.request.user, serializer.validated_data, serializer.instance
            )
            return
        if self.resource in APPEND_ONLY:
            raise PermissionDenied("Append a new record to preserve history.")
        obj = serializer.instance
        if (
            self.resource == "deliverables"
            and obj.request.requester_id != self.request.user.pk
            and "assign_editors" not in permissions(self.request.user, self.workspace_id)
        ):
            raise PermissionDenied("Only the requester or manager may edit deliverables.")
        if self.resource == "requests":
            from apps.requests_app.services import update_request

            serializer.instance = update_request(self.request.user, obj, serializer.validated_data)
            return
        if (
            self.resource == "requests"
            and obj.requester_id != self.request.user.pk
            and "assign_editors" not in permissions(self.request.user, self.workspace_id)
        ):
            raise PermissionDenied("Only the requester or manager may edit this request.")
        if self.resource == "creatives":
            from apps.creatives.services import editor_access

            editor_access(self.request.user, obj)
        obj = serializer.save()
        if self.resource == "deliverables":
            from apps.requests_app.assignments import sync_primary
            from apps.requests_app.services import recalculate_deliverable, recalculate_request

            sync_primary(obj)
            recalculate_deliverable(obj)
            recalculate_request(obj.request)
        record(self.request.user, obj, "updated")

    @action(detail=True, methods=["post"], url_path="actions/(?P<operation>[^/.]+)")
    def domain_action(self, request, pk=None, operation=None):
        obj = self.get_object()
        data = request.data
        if self.resource == "deliverable-assignments" and operation == "remove":
            from apps.requests_app.assignments import remove_assignment

            remove_assignment(request.user, obj)
            return Response(status=204)
        elif self.resource == "deliverables" and operation == "create-creative":
            from apps.creatives.models import Creative
            from apps.creatives.services import create_creative

            values = {**data, "deliverable": str(obj.pk), "title": data.get("title") or obj.title}
            serializer = serializer_for(Creative)(
                data=values, context=self.get_serializer_context()
            )
            serializer.is_valid(raise_exception=True)
            creative = create_creative(
                request.user, dict(serializer.validated_data, workspace=obj.workspace)
            )
            return Response(serializer_for(Creative)(creative).data, status=201)
        elif self.resource in ["requests", "deliverables", "creatives"] and operation == "assign":
            from apps.requests_app.services import assign

            editor = get_object_or_404(User, pk=data.get("editor"), is_active=True)
            obj = assign(request.user, obj, editor)
        elif (
            self.resource in ["requests", "deliverables", "creatives"]
            and operation == "start-production"
        ):
            from apps.requests_app.services import start

            obj = start(request.user, obj)
        elif self.resource == "creatives" and operation == "new-version":
            from apps.creatives.services import new_version

            version = new_version(request.user, obj, str(data.get("notes", "")))
            return Response(serializer_for(type(version))(version).data, status=201)
        elif self.resource == "creatives" and operation in ["submit", "approve", "request-changes"]:
            from apps.creatives.services import transition

            obj = transition(request.user, obj, operation, str(data.get("feedback", "")))
        elif self.resource == "creatives" and operation == "related":
            from apps.creatives.services import related

            obj = related(request.user, obj, data)
        elif self.resource == "creatives" and operation == "outcome":
            from apps.performance.services import outcome

            outcome(request.user, obj, data.get("outcome"), str(data.get("reason", "")))
            obj.refresh_from_db()
        elif self.resource == "creatives" and operation == "publish":
            from apps.integrations.services import enqueue_publish

            job = enqueue_publish(request.user, obj, data)
            return Response({"id": str(job.pk), "state": job.state}, status=202)
        elif self.resource == "creatives" and operation == "upload":
            from apps.storage.services import upload_local

            asset = upload_local(
                request.user, obj, request.FILES.get("file"), data.get("role", "master")
            )
            return Response({"id": str(asset.pk)}, status=201)
        elif self.resource == "storage/objects" and operation == "download":
            from apps.storage.services import local_path

            if obj.provider != "local":
                raise ValidationError("Use your authorized Google Drive account for this asset.")
            return FileResponse(
                local_path(obj).open("rb"),
                as_attachment=True,
                filename=obj.filename,
                content_type=obj.mime_type,
            )
        elif self.resource == "storage/connections" and operation == "connect":
            from apps.storage.google import begin_oauth

            require(request.user, obj.workspace_id, "manage_storage_connections")
            return Response(
                {
                    "url": begin_oauth(
                        request, obj, data.get("scope", "file"), bool(data.get("youtube", False))
                    )
                }
            )
        elif self.resource == "storage/connections" and operation == "disconnect":
            require(request.user, obj.workspace_id, "manage_storage_connections")
            obj.credentials_encrypted = ""
            obj.status = "disconnected"
            obj.save()
            record(request.user, obj, "integration_disconnected")
        elif self.resource == "storage/connections" and operation in ["sync", "test", "organize"]:
            require(request.user, obj.workspace_id, "manage_storage_connections")
            from apps.common.jobs import enqueue

            job = enqueue("drive_" + operation, obj, request.user, {"connection": str(obj.pk)})
            return Response({"id": str(job.pk)}, status=202)
        elif self.resource == "storage/connections" and operation == "transfer":
            from apps.storage.services import enqueue_transfer

            job = enqueue_transfer(request.user, obj, data)
            return Response({"id": str(job.pk), "status": job.status}, status=202)
        elif self.resource == "ad-connections" and operation == "sync":
            require(request.user, obj.workspace_id, "manage_performance")
            from apps.common.jobs import enqueue
            from apps.performance.providers import CAPABILITIES

            if not CAPABILITIES.get(obj.provider, {}).get("performance_sync"):
                raise ValidationError(
                    "Performance synchronization is not supported for this provider. Use manual snapshots."
                )
            job = enqueue("performance_sync", obj, request.user, {"connection": str(obj.pk)})
            return Response({"id": str(job.pk)}, status=202)
        elif self.resource == "ad-connections" and operation == "credentials":
            require(request.user, obj.workspace_id, "manage_deployments")
            from apps.integrations.crypto import seal

            credentials = data.get("credentials")
            if not isinstance(credentials, dict) or not credentials.get("access_token"):
                raise ValidationError("An access token is required.")
            obj.credentials_encrypted = seal(credentials)
            obj.status = "connected"
            obj.save()
            record(request.user, obj, "credentials_changed", notify=False)
        elif self.resource == "experiments" and operation in ["start", "complete", "cancel"]:
            from apps.experiments.services import transition

            obj = transition(request.user, obj, operation, data)
        elif self.resource == "context" and operation == "new-version":
            from apps.context_hub.services import new_version

            version = new_version(request.user, obj, data)
            return Response(serializer_for(type(version))(version).data, status=201)
        elif self.resource == "proposals" and operation in ["accept", "reject"]:
            from apps.context_hub.services import decide_proposal

            obj = decide_proposal(request.user, obj, operation)
        elif self.resource == "context-versions" and operation == "approve":
            from apps.context_hub.services import approve

            obj = approve(request.user, obj)
        elif self.resource == "notifications" and operation == "read":
            obj.read_at = timezone.now()
            obj.save(update_fields=["read_at"])
        elif self.resource == "feedback" and operation == "resolve":
            require(request.user, obj.workspace_id, "comment_creatives")
            obj.resolved = True
            obj.resolved_at = timezone.now()
            obj.save()
        elif self.resource == "jobs" and operation == "retry":
            require(request.user, obj.workspace_id, "manage_automations")
            if obj.status != "failed" or obj.type not in [
                "drive_sync",
                "drive_test",
                "drive_organize",
                "google_upload",
                "performance_sync",
                "automation",
            ]:
                raise ValidationError("This job cannot be safely retried automatically.")
            if obj.type == "google_upload":
                from apps.storage.models import Upload

                upload = Upload.objects.get(pk=obj.payload["upload"], workspace=obj.workspace)
                if upload.status == "initializing" and not upload.session_encrypted:
                    raise ValidationError(
                        "Upload initialization is uncertain. Reconcile with Google before creating another upload."
                    )
            obj.status = "queued"
            obj.available_at = timezone.now()
            obj.attempts = 0
            obj.save()
            record(request.user, obj, "job_retried")
        elif operation == "archive" and hasattr(obj, "archived_at"):
            self.check_write()
            obj.archived_at = timezone.now()
            obj.save()
            if self.resource == "creatives":
                from apps.requests_app.services import rollup

                rollup(obj)
            record(request.user, obj, "archived")
        else:
            raise ValidationError("Unsupported action for this resource.")
        return Response(self.get_serializer(obj).data)


class SchemaView(APIView):
    def get(self, request):
        workspace = request.query_params.get("workspace")
        granted = permissions(request.user, workspace)
        result = {}
        labels = {info[0].lower(): route for route, info in DEFINITIONS.items()}
        for route, (label, write, read) in DEFINITIONS.items():
            if read not in granted:
                continue
            model = apps.get_model(label)
            fields = []
            ser = serializer_for(model)(context={"request": request, "workspace": workspace})
            for name, field in ser.fields.items():
                if name in HIDDEN or name in PROTECTED:
                    continue
                if model._meta.model_name == "requestdeliverable" and name == "sequence":
                    continue
                mf = model._meta.get_field(name)
                kind = "text"
                choices = []
                related = None
                if mf.is_relation:
                    related = labels.get(
                        mf.related_model._meta.label.lower(),
                        "users" if mf.related_model == User else "platforms",
                    )
                    kind = "multi" if mf.many_to_many else "relation"
                elif mf.choices:
                    kind = "select"
                    choices = [{"value": k, "label": v} for k, v in mf.choices]
                elif isinstance(mf, models.BooleanField):
                    kind = "boolean"
                elif isinstance(mf, models.JSONField):
                    kind = "json"
                elif isinstance(mf, models.DateTimeField):
                    kind = "datetime"
                elif isinstance(mf, (models.IntegerField, models.DecimalField)):
                    kind = "number"
                elif isinstance(mf, models.TextField):
                    kind = "textarea"
                fields.append(
                    {
                        "name": name,
                        "kind": kind,
                        "required": field.required,
                        "choices": choices,
                        "related": related,
                        "default": mf.get_default() if mf.has_default() else None,
                    }
                )
            result[route] = {
                "fields": fields,
                "can_create": write in granted and route not in READ_ONLY,
                "can_edit": write in granted and route not in READ_ONLY | APPEND_ONLY,
                "permission": write,
            }
        return Response(result)


class DirectoryView(APIView):
    def get(self, request):
        ws = request.query_params.get("workspace")
        membership(request.user, ws)
        users = User.objects.filter(
            is_active=True,
            id__in=WorkspaceMembership.objects.filter(workspace_id=ws, active=True).values(
                "user_id"
            ),
        )
        if request.query_params.get("brand"):
            brand = request.query_params["brand"]
            from apps.catalog.models import Brand

            get_object_or_404(scope(Brand.objects.all(), request.user, ws), pk=brand)
            eligible = (
                WorkspaceMembership.objects.filter(workspace_id=ws, active=True)
                .filter(Q(brand_restricted=False) | Q(brands__pk=brand))
                .values("user_id")
            )
            users = users.filter(pk__in=eligible)
        return Response(
            {"results": [{"id": str(u.pk), "title": str(u), "email": u.email} for u in users]}
        )


class WorkspaceView(APIView):
    def post(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied("Platform administrator required.")

        class Input(serializers.Serializer):
            name = serializers.CharField(max_length=200)
            slug = serializers.SlugField()

        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            ws = Workspace.objects.create(**data.validated_data, created_by=request.user)
            WorkspaceMembership.objects.create(workspace=ws, user=request.user, role="manager")
        return Response({"id": str(ws.pk), "name": ws.name}, status=201)


class MembersView(APIView):
    def get(self, request, workspace):
        require(request.user, workspace, "manage_users")
        return Response(
            {
                "results": [
                    {
                        "id": str(m.pk),
                        "user": str(m.user_id),
                        "email": m.user.email,
                        "name": str(m.user),
                        "role": m.role,
                        "active": m.active,
                        "brand_restricted": m.brand_restricted,
                        "brands": list(m.brands.values_list("id", flat=True)),
                    }
                    for m in WorkspaceMembership.objects.filter(
                        workspace_id=workspace
                    ).select_related("user")
                ]
            }
        )

    @transaction.atomic
    def post(self, request, workspace):
        require(request.user, workspace, "manage_users")
        from apps.workspaces.services import save_member

        member = save_member(request.user, workspace, request.data)
        return Response({"id": str(member.pk)}, status=201)


class OverviewView(APIView):
    def get(self, request):
        ws = request.query_params.get("workspace")
        permissions(request.user, ws)
        from apps.audit.models import Activity
        from apps.creatives.models import Creative
        from apps.requests_app.models import CreativeRequest

        creatives = scope(Creative.objects.all(), request.user, ws).filter(archived_at__isnull=True)
        requests = scope(CreativeRequest.objects.all(), request.user, ws)
        m = membership(request.user, ws)
        if m and m.role == "editor":
            creatives = creatives.filter(owner=request.user)
            requests = requests.filter(owner=request.user)
        if m and m.role == "requester":
            requests = requests.filter(requester=request.user)
        counts = {
            "requests": requests.exclude(status__in=["approved", "published"]).count(),
            "production": creatives.filter(status="in_production").count(),
            "review": creatives.filter(status="ready_for_review").count(),
            "approved": creatives.filter(status="approved").count(),
            "overdue": requests.filter(due_date__lt=timezone.now())
            .exclude(status__in=["approved", "published"])
            .count(),
            "winners": creatives.filter(outcome="winner").count(),
        }
        from datetime import timedelta

        from apps.creatives.models import CreativeFeedback
        from apps.performance.models import Deployment
        from apps.requests_app.models import RequestDeliverable

        role = m.role if m else "manager"
        deliverables = scope(RequestDeliverable.objects.all(), request.user, ws)
        if role == "editor":
            deliverables = deliverables.filter(assigned_editor=request.user)
            counts.update(
                my_deliverables=deliverables.exclude(status__in=["approved", "published"]).count(),
                changes=creatives.filter(status="changes_requested").count(),
                due_today=deliverables.filter(due_date__date=timezone.now().date())
                .exclude(status__in=["approved", "published"])
                .count(),
            )
            cards = ["my_deliverables", "changes", "due_today", "review"]
        elif role == "reviewer":
            counts.update(
                aging_review=creatives.filter(
                    status="ready_for_review",
                    current_version__submitted_at__lt=timezone.now() - timedelta(days=2),
                ).count(),
                recently_reviewed=scope(CreativeFeedback.objects.all(), request.user, ws)
                .filter(author=request.user, created_at__gte=timezone.now() - timedelta(days=7))
                .count(),
            )
            cards = ["review", "aging_review", "recently_reviewed", "overdue"]
        elif role == "media_buyer":
            deployments = scope(Deployment.objects.all(), request.user, ws)
            counts.update(
                approved_undeployed=creatives.filter(status="approved")
                .exclude(pk__in=deployments.values("creative_id"))
                .count(),
                active_deployments=deployments.filter(state="active").count(),
                stale_sync=deployments.filter(state="active")
                .filter(
                    Q(last_sync__isnull=True) | Q(last_sync__lt=timezone.now() - timedelta(days=2))
                )
                .count(),
                fatigue_attention=creatives.filter(outcome="fatigued").count(),
            )
            cards = ["approved_undeployed", "active_deployments", "stale_sync", "fatigue_attention"]
        elif role == "requester":
            counts.update(
                my_deliverables=deliverables.filter(request__requester=request.user)
                .exclude(status__in=["approved", "published"])
                .count(),
                completed_requests=requests.filter(status__in=["approved", "published"]).count(),
            )
            cards = ["requests", "my_deliverables", "overdue", "completed_requests"]
        else:
            cards = ["requests", "production", "review", "approved"]
        activity = scope(Activity.objects.all(), request.user, ws)[:8]
        return Response(
            {
                "counts": counts,
                "cards": cards,
                "activity": serializer_for(Activity)(activity, many=True).data,
            }
        )


class SearchView(APIView):
    def get(self, request):
        ws = request.query_params.get("workspace")
        granted = permissions(request.user, ws)
        q = request.query_params.get("q", "")[:200]
        results = []
        if len(q.strip()) < 2:
            return Response({"results": []})
        for route in [
            "requests",
            "deliverables",
            "creatives",
            "versions",
            "products",
            "campaigns",
            "clips",
            "context",
            "content",
            "storage/objects",
        ]:
            label, _, read = DEFINITIONS[route]
            if read not in granted:
                continue
            model = apps.get_model(label)
            condition = Q()
            for f in model._meta.fields:
                if isinstance(f, (models.CharField, models.TextField)) and f.name not in HIDDEN:
                    condition |= Q(**{f.name + "__icontains": q})
            for obj in scope(model.objects.filter(condition), request.user, ws)[:15]:
                results.append(
                    {
                        "id": str(obj.pk),
                        "resource": route,
                        "title": str(
                            getattr(
                                obj,
                                "title",
                                getattr(
                                    obj,
                                    "name",
                                    getattr(obj, "filename", getattr(obj, "label", obj.pk)),
                                ),
                            )
                        ),
                    }
                )
        return Response({"results": results})


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def readiness(request):
    try:
        Workspace.objects.exists()
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            return Response({"status": "migrations_pending"}, status=503)
    except Exception:
        return Response({"status": "unavailable"}, status=503)
    return Response({"status": "ready"})


@api_view(["GET"])
def platforms(request):
    from apps.catalog.models import Platform

    return Response(
        {"results": [{"id": str(p.pk), "title": p.name} for p in Platform.objects.all()]}
    )
