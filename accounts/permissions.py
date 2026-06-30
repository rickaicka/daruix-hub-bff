from rest_framework.permissions import BasePermission

from accounts.services.permission_service import user_has_permission


class HasSGOWebPermission(BasePermission):
    message = "Você não tem permissão para acessar este recurso."

    def has_permission(self, request, view):
        required_permission = getattr(view, "required_permission", None)

        if not required_permission:
            return False

        return user_has_permission(request.user, required_permission)