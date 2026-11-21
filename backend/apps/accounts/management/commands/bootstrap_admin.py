from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from apps.accounts.mfa import new_totp_secret, provisioning_uri
from apps.accounts.models import UserProfile


class Command(BaseCommand):
    help = "Create local admin user if missing. Optional --enable-mfa prints TOTP secret once."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--password", default="changeme")
        parser.add_argument("--enable-mfa", action="store_true")

    def handle(self, *args, **options):
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
        else:
            self.stdout.write(f"User '{username}' already exists")

        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"role": UserProfile.Role.ADMIN},
        )
        if profile.role != UserProfile.Role.ADMIN:
            profile.role = UserProfile.Role.ADMIN
            profile.save(update_fields=["role"])

        if options["enable_mfa"]:
            secret = new_totp_secret()
            profile.mfa_secret = secret
            profile.mfa_enabled = True
            profile.save(update_fields=["mfa_secret", "mfa_enabled"])
            uri = provisioning_uri(secret, username)
            self.stdout.write(self.style.WARNING("MFA enabled. Store this secret once:"))
            self.stdout.write(f"secret={secret}")
            self.stdout.write(f"otpauth={uri}")
        elif created:
            self.stdout.write(
                "MFA is off by default. Enable with: "
                "python manage.py bootstrap_admin --enable-mfa"
            )
