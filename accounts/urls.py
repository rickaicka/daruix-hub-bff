from django.urls import include, path
from rest_framework.routers import DefaultRouter

from accounts.views.auth import LoginView, LogoutView, MeView, RefreshView
from accounts.views.hub_module_favorite import HubModuleFavoriteView, HubMenuItemFavoriteView
from accounts.views.permissioning import (
    GroupPermissionViewSet,
    PermissionViewSet,
    UserGroupViewSet,
    MyPermissionsView,
)
from accounts.views.hub_admin import (
    AdminClientViewSet,
    AdminEmployeeViewSet,
    AdminGroupPermissionViewSet,
    AdminHubModuleViewSet,
    AdminPermissionViewSet,
    AdminSupplierViewSet,
    AdminUserGroupViewSet,
    AdminUserViewSet,
    HubAdminOptionsView,
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

router.register(
    r"hub-admin/usuarios",
    AdminUserViewSet,
    basename="hub-admin-usuarios",
)
router.register(
    r"hub-admin/modulos",
    AdminHubModuleViewSet,
    basename="hub-admin-modulos",
)
router.register(
    r"hub-admin/permissoes",
    AdminPermissionViewSet,
    basename="hub-admin-permissoes",
)
router.register(
    r"hub-admin/grupos",
    AdminUserGroupViewSet,
    basename="hub-admin-grupos",
)
router.register(
    r"hub-admin/grupo-permissoes",
    AdminGroupPermissionViewSet,
    basename="hub-admin-grupo-permissoes",
)
router.register(
    r"hub-admin/clientes",
    AdminClientViewSet,
    basename="hub-admin-clientes",
)
router.register(
    r"hub-admin/colaboradores",
    AdminEmployeeViewSet,
    basename="hub-admin-colaboradores",
)
router.register(
    r"hub-admin/fornecedores",
    AdminSupplierViewSet,
    basename="hub-admin-fornecedores",
)

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/me/permissions/", MyPermissionsView.as_view(), name="auth-me-permissions"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),

    path("hub-admin/opcoes/", HubAdminOptionsView.as_view(), name="hub-admin-opcoes"),
    path(
        "hub/modulos/<slug:slug>/favorito/",
        HubModuleFavoriteView.as_view(),
        name="hub-module-favorite",
    ),
    path("", include(router.urls)),
]

urlpatterns += [
    path(
        "hub/funcionalidades/<slug:slug>/favorito/",
        HubMenuItemFavoriteView.as_view(),
        name="hub-menu-item-favorite",
    ),
]