from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        # Connects the failed/successful login signal receivers used for throttling.
        from . import backends  # noqa: F401
