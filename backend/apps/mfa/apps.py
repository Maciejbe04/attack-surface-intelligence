from django.apps import AppConfig


class MfaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mfa"
    label = "mfa"
    verbose_name = "Multi-factor authentication"

    def ready(self):
        from django.contrib import admin

        from .admin_guard import install

        install(admin.site)
