from django.conf import settings


class BrowserSessionRecoveryMiddleware:
    """Recover the public UI from a stale or blocking browser session cookie.

    This middleware intentionally runs before Django's SessionMiddleware.  A
    recovery request can therefore remove the incoming session cookie before
    Django attempts to load that session from the database.  The response also
    expires the browser cookie so the next normal request starts cleanly.
    """

    session_path = "/api/v1/auth/session/"
    reset_header = "HTTP_X_PDP_RESET_SESSION"
    reset_query = "pdp_reset_session"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        recovery_requested = (
            request.path == self.session_path
            and (
                request.META.get(self.reset_header) == "1"
                or request.GET.get(self.reset_query) == "1"
            )
        )

        if recovery_requested:
            request.COOKIES.pop(settings.SESSION_COOKIE_NAME, None)

        response = self.get_response(request)

        if recovery_requested:
            response.delete_cookie(
                settings.SESSION_COOKIE_NAME,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
            response["Cache-Control"] = "no-store, private"
            response["X-PDP-Session-Recovered"] = "1"

        return response
