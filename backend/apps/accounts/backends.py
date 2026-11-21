from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.exceptions import PermissionDenied
from django.dispatch import receiver

from . import throttle


class ThrottledModelBackend(ModelBackend):
    """ModelBackend that refuses to check passwords while the caller is locked out.

    Covers every ``authenticate()`` call, including the Django admin login,
    so no sign-in path can be used to brute-force passwords.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(self.get_user_model().USERNAME_FIELD)
        if throttle.is_locked(username or "", throttle.client_ip(request)):
            # Django turns this into a failed login and stops trying other backends.
            raise PermissionDenied("Too many failed sign-in attempts.")
        return super().authenticate(request, username=username, password=password, **kwargs)

    @staticmethod
    def get_user_model():
        from django.contrib.auth import get_user_model

        return get_user_model()


@receiver(user_login_failed, dispatch_uid="surfacex.accounts.count_failed_login")
def _count_failed_login(sender, credentials, request=None, **kwargs):
    username = credentials.get("username", "") if isinstance(credentials, dict) else ""
    throttle.record_failure(str(username), throttle.client_ip(request))


@receiver(user_logged_in, dispatch_uid="surfacex.accounts.reset_failed_logins")
def _reset_failed_logins(sender, request, user, **kwargs):
    throttle.reset_user(user.get_username(), throttle.client_ip(request))
