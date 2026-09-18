from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import User, UserProfile


@admin.register(User)
class AccountAdmin(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "display_name", "is_active", "is_superuser"]
    search_fields = ["email", "display_name"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "email",
                    "password",
                    "display_name",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
        ("History", {"fields": ("date_joined", "last_login")}),
    )
    readonly_fields = ["date_joined", "last_login"]
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.audit.services import security_event

        security_event(obj, "account_permissions_changed", actor=request.user)


@admin.register(UserProfile)
class ProfileAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False
