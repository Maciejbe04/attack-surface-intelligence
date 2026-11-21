from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from rest_framework.authentication import SessionAuthentication
from rest_framework.request import Request


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    Session auth without CSRF, with an X-Sessionid header fallback.

    Some browsers drop the session cookie after login (seen on Firefox against
    bare http://IP hosts). The SPA stores sessionid from the login JSON body and
    sends it as X-Sessionid so auth still works.
    """

    header_names = ("HTTP_X_SESSIONID", "HTTP_X_SESSION_ID")

    def enforce_csrf(self, request: Request) -> None:
        return

    def authenticate(self, request: Request):
        user_auth = super().authenticate(request)
        if user_auth is not None:
            return user_auth

        session_key = ""
        for name in self.header_names:
            session_key = str(request.META.get(name, "")).strip()
            if session_key:
                break
        if not session_key:
            return None

        store = SessionStore(session_key=session_key)
        user_id = store.get("_auth_user_id")
        if not user_id:
            return None

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
        if not user.is_active:
            return None

        session_hash = store.get("_auth_user_hash")
        if session_hash:
            try:
                if user.get_session_auth_hash() != session_hash:
                    return None
            except Exception:
                return None

        request.session = store
        return (user, session_key)
