from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsSystemAdministratorOrReadOnly(BasePermission):
    """Allow everyone authenticated to read; only staff users may change system settings."""

    message = "تغییر تنظیمات منابع فقط برای مدیر سامانه مجاز است."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
