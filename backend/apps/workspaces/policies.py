from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.workspaces.models import Workspace, WorkspaceMembership

ALL = set(
    "create_requests assign_editors submit_version review_version approve_version create_products create_campaigns manage_projects view_analytics view_creatives edit_creatives comment_creatives mark_winner manage_performance manage_deployments manage_experiments manage_automations publish_ads manage_lineage manage_boards manage_taxonomy manage_naming manage_workspaces manage_clips manage_storage_connections view_storage_connections manage_content_index manage_source_materials manage_context manage_users view_audit_log".split()
)
READ = {"view_creatives", "view_storage_connections"}
ROLES = {
    "manager": ALL,
    "media_buyer": READ
    | set(
        "create_requests comment_creatives view_analytics mark_winner manage_performance manage_deployments manage_experiments publish_ads manage_lineage".split()
    ),
    "editor": READ
    | set(
        "submit_version edit_creatives comment_creatives manage_clips manage_content_index manage_source_materials".split()
    ),
    "reviewer": READ
    | set("review_version approve_version comment_creatives manage_context".split()),
    "requester": READ | {"create_requests", "comment_creatives", "manage_source_materials"},
    "viewer": {"view_creatives"},
}


def membership(user, workspace):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied("Authentication required.")
    try:
        ws = Workspace.objects.get(pk=workspace, active=True)
    except (Workspace.DoesNotExist, ValueError, DjangoValidationError):
        raise PermissionDenied("Workspace unavailable.") from None
    if user.is_superuser:
        return None
    member = WorkspaceMembership.objects.filter(workspace=ws, user=user, active=True).first()
    if not member:
        raise PermissionDenied("Workspace unavailable.")
    return member


def permissions(user, workspace):
    member = membership(user, workspace)
    if member is None:
        return ALL
    result = ROLES.get(member.role, set()).copy()
    for key, allowed in member.permission_overrides.items():
        if key in ALL:
            result.add(key) if allowed else result.discard(key)
    return result


def require(user, workspace, permission):
    if getattr(user, "must_change_password", False):
        raise PermissionDenied(
            "Change your temporary password from My profile before accessing workspace data."
        )
    if permission not in permissions(user, workspace):
        raise PermissionDenied("Missing permission: " + permission)


def scope(queryset, user, workspace):
    if getattr(user, "must_change_password", False):
        raise PermissionDenied(
            "Change your temporary password from My profile before accessing workspace data."
        )
    member = membership(user, workspace)
    queryset = queryset.filter(workspace_id=workspace)
    if member and member.brand_restricted:
        if queryset.model._meta.label == "catalog.Brand":
            return queryset.filter(pk__in=member.brands.values("pk"))
        if any(f.name == "brand" for f in queryset.model._meta.fields):
            queryset = queryset.filter(brand_id__in=member.brands.values("pk"))
    label = queryset.model._meta.label
    if label == "requests_app.CreativeRequest":
        return queryset.filter(pk__in=visible_requests(user, workspace).values("pk"))
    if label in ["requests_app.RequestDeliverable", "requests_app.RequestSourceMaterial"]:
        return queryset.filter(request_id__in=visible_requests(user, workspace).values("pk"))
    if label == "requests_app.RequestDeliverableAssignment":
        return queryset.filter(
            deliverable__request_id__in=visible_requests(user, workspace).values("pk")
        )
    if label == "requests_app.SourceMaterialUsage":
        return queryset.filter(
            source__request_id__in=visible_requests(user, workspace).values("pk")
        )
    if (
        label in ["audit.Activity", "audit.AuditEvent"]
        and member
        and member.role not in ["manager", "reviewer"]
    ):
        from django.db.models import CharField, Q, Value
        from django.db.models.functions import Cast, Replace

        from apps.requests_app.models import RequestDeliverable, RequestDeliverableAssignment

        visible = visible_requests(user, workspace)
        # Audit stores string UUIDs; SQLite's UUID columns store hex without hyphens.
        queryset = queryset.annotate(_object_hex=Replace("object_id", Value("-"), Value("")))
        queryset = queryset.filter(
            ~Q(
                object_type__in=[
                    "creativerequest",
                    "requestdeliverable",
                    "requestdeliverableassignment",
                ]
            )
            | Q(
                object_type="creativerequest",
                _object_hex__in=visible.annotate(
                    hex_id=Replace(Cast("pk", CharField()), Value("-"), Value(""))
                ).values("hex_id"),
            )
            | Q(
                object_type="requestdeliverable",
                _object_hex__in=RequestDeliverable.objects.filter(request__in=visible)
                .annotate(hex_id=Replace(Cast("pk", CharField()), Value("-"), Value("")))
                .values("hex_id"),
            )
            | Q(
                object_type="requestdeliverableassignment",
                _object_hex__in=RequestDeliverableAssignment.objects.filter(
                    deliverable__request__in=visible
                )
                .annotate(hex_id=Replace(Cast("pk", CharField()), Value("-"), Value("")))
                .values("hex_id"),
            )
        )
    return queryset


def visible_requests(user, workspace):
    from django.db.models import Q

    from apps.requests_app.models import CreativeRequest

    member = membership(user, workspace)
    queryset = CreativeRequest.objects.filter(workspace_id=workspace)
    if member and member.brand_restricted:
        queryset = queryset.filter(brand_id__in=member.brands.values("pk"))
    if member and member.role not in ["manager", "reviewer"]:
        queryset = queryset.filter(
            Q(requester=user)
            | Q(owner=user)
            | Q(deliverables__assigned_editor=user)
            | Q(deliverables__assignments__user=user)
        ).distinct()
    return queryset


def validate_scope(user, workspace, brand):
    member = membership(user, workspace)
    if brand and str(brand.workspace_id) != str(workspace):
        raise ValidationError({"brand": "Brand belongs to another workspace."})
    if (
        member
        and member.brand_restricted
        and (not brand or not member.brands.filter(pk=brand.pk).exists())
    ):
        raise PermissionDenied("Brand unavailable.")
