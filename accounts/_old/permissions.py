from rest_framework.permissions import BasePermission

from accounts._old.services.permission_service import user_has_permission


class HasHubPermission(BasePermission):
    """
    Uso em uma view:

    required_permission = "employee.purchase_orders.view"
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        required_permission = getattr(view, "required_permission", None)

        if hasattr(view, "get_required_permission"):
            required_permission = view.get_required_permission()

        if not required_permission:
            return True

        return user_has_permission(request.user, required_permission)