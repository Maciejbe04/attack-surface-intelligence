from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session auth without CSRF checks (demo / competition deployments)."""

    def enforce_csrf(self, request):
        return
