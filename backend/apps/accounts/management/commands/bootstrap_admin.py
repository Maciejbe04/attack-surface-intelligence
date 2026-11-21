from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import UserProfile

DEFAULT_PASSWORD = "changeme"


class Command(BaseCommand):
    help = "Create the local admin user if missing. Warns when the password is weak."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--enable-mfa", action="store_true", help="Disabled (legacy plaintext MFA).")

    def handle(self, *args, **options):
        if options["enable_mfa"]:
            # The legacy path stored the TOTP secret in plaintext and printed it
            # into container logs. Use the encrypted MFA module instead.
            raise CommandError(
                "--enable-mfa is disabled: it stored the MFA secret in plaintext. "
                "Use the encrypted MFA backend (docs/mfa-backend.md)."
            )

        username = options["username"]
        password = options["password"]
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created user '{username}'"))
            self._warn_if_weak(user, password)
        else:
            self.stdout.write(f"User '{username}' already exists")

        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"role": UserProfile.Role.ADMIN},
        )
        if profile.role != UserProfile.Role.ADMIN:
            profile.role = UserProfile.Role.ADMIN
            profile.save(update_fields=["role"])

    def _warn_if_weak(self, user, password: str) -> None:
        problems = []
        if password == DEFAULT_PASSWORD:
            problems.append("it is the public default password")
        try:
            validate_password(password, user)
        except ValidationError as exc:
            problems.extend(message.rstrip(".") for message in exc.messages)
        if problems and not settings.DEBUG:
            self.stderr.write(
                self.style.WARNING(
                    f"SECURITY WARNING: weak password for '{user.get_username()}' "
                    f"({'; '.join(problems)}). Set BOOTSTRAP_ADMIN_PASSWORD in .env "
                    "before the first start, or change it in the console."
                )
            )
