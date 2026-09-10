from rest_framework.permissions import BasePermission


class IsSuperUser(BasePermission):
    """Restrict security-sensitive administration to the root administrator."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )
