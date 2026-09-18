from django.apps import apps
from django.contrib import admin

from apps.common.resources import DEFINITIONS, HIDDEN


class OperationsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if f.name not in HIDDEN]


for label, _, _ in DEFINITIONS.values():
    model = apps.get_model(label)
    if not admin.site.is_registered(model):
        admin.site.register(
            model,
            type(
                model.__name__ + "Admin",
                (OperationsAdmin,),
                {
                    "list_display": ["id", "created_at"],
                    "list_filter": ["workspace"],
                    "search_fields": [
                        f.name
                        for f in model._meta.fields
                        if f.name in ["title", "name", "code", "action"]
                    ],
                },
            ),
        )
