from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views.auth import LoginView, LogoutView, MeView
from accounts.views.permissioning import (
    GroupPermissionViewSet,
    PermissionViewSet,
    UserGroupViewSet,
    MyPermissionsView,
)

app_name = "accounts"

router = DefaultRouter()
router.register(
    r"permissionamento/permissoes",
    PermissionViewSet,
    basename="permission",
)
router.register(
    r"permissionamento/grupos",
    UserGroupViewSet,
    basename="user-group",
)
router.register(
    r"permissionamento/grupo-permissoes",
    GroupPermissionViewSet,
    basename="group-permission",
)

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/me/permissions/", MyPermissionsView.as_view(), name="auth-me-permissions"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),

    path("", include(router.urls)),
]