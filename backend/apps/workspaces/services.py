from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_email
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit.services import record
from apps.catalog.models import Brand
from apps.workspaces.models import WorkspaceMembership
from apps.workspaces.policies import ALL, ROLES, membership, require


def save_member(actor, workspace, data):
    require(actor, workspace, "manage_users")
    acting = membership(actor, workspace)
    if acting and acting.brand_restricted:
        raise PermissionDenied(
            "An unrestricted workspace manager is required to change memberships."
        )
    role = data.get("role", "viewer")
    if role not in ROLES:
        raise ValidationError("Invalid role.")
    email = str(data.get("email", "")).lower()
    validate_email(email)
    user = User.objects.filter(email=email).first()
    if not user:
        password = data.get("password", "")
        validate_password(password)
        user = User.objects.create_user(
            email, password, display_name=data.get("name", ""), must_change_password=True
        )
    member, _ = WorkspaceMembership.objects.get_or_create(
        workspace_id=workspace, user=user, defaults={"role": role}
    )
    member.role = role
    member.active = bool(data.get("active", True))
    member.brand_restricted = bool(data.get("brand_restricted", False))
    overrides = data.get("permission_overrides", member.permission_overrides)
    if not isinstance(overrides, dict) or any(
        k not in ALL or not isinstance(v, bool) for k, v in overrides.items()
    ):
        raise ValidationError(
            "Permission overrides must use known permission names and boolean values."
        )
    if member.user_id == actor.pk and overrides != member.permission_overrides:
        raise ValidationError("Another manager must change your own permissions.")
    member.permission_overrides = overrides
    ids = data.get("brands", [])
    brands = Brand.objects.filter(workspace_id=workspace, pk__in=ids)
    if brands.count() != len(set(ids)):
        raise ValidationError("Invalid brand selection.")
    if member.user_id == actor.pk and (
        role != "manager" or not member.active or member.brand_restricted
    ):
        raise ValidationError("Ask another manager to change your own administrative access.")
    member.save()
    member.brands.set(brands)
    record(
        actor,
        member,
        "membership_changed",
        {
            "user_id": str(user.pk),
            "role": role,
            "active": member.active,
            "brand_restricted": member.brand_restricted,
            "permission_overrides": member.permission_overrides,
        },
        notify=False,
    )
    return member
