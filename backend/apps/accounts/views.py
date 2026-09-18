from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User, UserProfile
from apps.workspaces.models import WorkspaceMembership
from apps.workspaces.policies import permissions


class LoginThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        if request.method != "POST":
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def user_payload(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    memberships = WorkspaceMembership.objects.filter(
        user=user, active=True, workspace__active=True
    ).select_related("workspace")
    workspaces = [
        {
            "id": str(m.workspace_id),
            "name": m.workspace.name,
            "role": m.role,
            "permissions": sorted(permissions(user, m.workspace_id)),
        }
        for m in memberships
    ]
    if user.is_superuser:
        from apps.workspaces.models import Workspace

        workspaces = [
            {
                "id": str(w.pk),
                "name": w.name,
                "role": "platform_admin",
                "permissions": sorted(permissions(user, w.pk)),
            }
            for w in Workspace.objects.filter(active=True)
        ]
    return {
        "id": str(user.pk),
        "email": user.email,
        "display_name": user.display_name,
        "is_superuser": user.is_superuser,
        "must_change_password": user.must_change_password,
        "profile": ProfileSerializer(profile).data,
        "workspaces": workspaces,
    }


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        exclude = ["user"]

    def validate_timezone(self, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValidationError("Unknown timezone.") from None
        return value


@method_decorator(ensure_csrf_cookie, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class SessionView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def get(self, request):
        return Response(
            user_payload(request.user) if request.user.is_authenticated else {"user": None}
        )

    def post(self, request):
        user = authenticate(
            request,
            email=str(request.data.get("email", "")).lower(),
            password=request.data.get("password", ""),
        )
        if not user:
            raise ValidationError("Invalid email or password.")
        login(request, user)
        return Response(user_payload(user))

    def delete(self, request):
        logout(request)
        return Response(status=204)


class MeView(APIView):
    def get(self, request):
        return Response(user_payload(request.user))

    def patch(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(profile, data=request.data.get("profile", {}), partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if "display_name" in request.data:
            request.user.display_name = str(request.data["display_name"])[:150]
            request.user.save(update_fields=["display_name"])
        return Response(user_payload(request.user))

    def post(self, request):
        if not request.user.check_password(request.data.get("old_password", "")):
            raise ValidationError("Current password is incorrect.")
        password = request.data.get("new_password", "")
        validate_password(password, request.user)
        request.user.set_password(password)
        request.user.must_change_password = False
        request.user.save()
        update_session_auth_hash(request, request.user)
        from apps.audit.services import security_event

        security_event(request.user, "password_changed")
        return Response({"detail": "Password changed."})


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        form = PasswordResetForm({"email": request.data.get("email", "")})
        if form.is_valid():
            form.save(
                request=request,
                use_https=not settings.DEBUG,
                email_template_name="registration/password_reset_email.html",
                subject_template_name="registration/password_reset_subject.txt",
            )
        return Response({"detail": "If the account exists, reset instructions have been sent."})


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        try:
            user = User.objects.get(
                pk=force_str(urlsafe_base64_decode(request.data.get("uid", "")))
            )
        except (ValueError, User.DoesNotExist, DjangoValidationError):
            raise ValidationError("Invalid reset link.") from None
        if not default_token_generator.check_token(user, request.data.get("token", "")):
            raise ValidationError("Invalid or expired reset link.")
        form = SetPasswordForm(user, request.data)
        if not form.is_valid():
            raise ValidationError(form.errors)
        form.save()
        user.must_change_password = False
        user.save(update_fields=["must_change_password"])
        from apps.audit.services import security_event

        security_event(user, "password_reset")
        return Response({"detail": "Password reset."})
