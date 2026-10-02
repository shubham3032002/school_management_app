from rest_framework.permissions import BasePermission


class HasPermissionCode(BasePermission):
    """Set `permission_code = "attendance.mark"` on the view."""

    def has_permission(self, request, view):
        code = getattr(view, "permission_code", None)
        if not code:
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.has_permission_code(code))
