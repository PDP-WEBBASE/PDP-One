from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsManagerOrReadOnly(BasePermission):
    """Authenticated users may read run history; staff users may start extraction."""

    message = "اجرای استخراج فقط برای مدیران مجاز است."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
