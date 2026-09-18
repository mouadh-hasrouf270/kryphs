from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import MeView, PasswordResetConfirmView, PasswordResetView, SessionView
from apps.common.resources import DEFINITIONS
from apps.common.views import (
    DirectoryView,
    MembersView,
    OverviewView,
    SchemaView,
    ScopedViewSet,
    SearchView,
    WorkspaceView,
    health,
    platforms,
    readiness,
)
from apps.context_hub.evidence import EvidenceView
from apps.storage.google import callback

router = DefaultRouter()
for route in DEFINITIONS:
    cls = type(route.replace("/", "_") + "ViewSet", (ScopedViewSet,), {"resource": route})
    router.register(route, cls, basename=route.replace("/", "-"))

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/session/", SessionView.as_view()),
    path("api/v1/auth/reset/", PasswordResetView.as_view()),
    path("api/v1/auth/reset-confirm/", PasswordResetConfirmView.as_view()),
    path("api/v1/me/", MeView.as_view()),
    path("api/v1/schema/", SchemaView.as_view()),
    path("api/v1/users/", DirectoryView.as_view()),
    path("api/v1/workspaces/", WorkspaceView.as_view()),
    path("api/v1/workspaces/<uuid:workspace>/members/", MembersView.as_view()),
    path("api/v1/overview/", OverviewView.as_view()),
    path("api/v1/search/", SearchView.as_view()),
    path("api/v1/evidence/", EvidenceView.as_view()),
    path("api/v1/platforms/", platforms),
    path("api/v1/health/", health),
    path("api/v1/ready/", readiness),
    path("api/v1/", include(router.urls)),
]
urlpatterns.insert(0, path("api/v1/google/callback/", callback))
