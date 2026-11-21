from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.mfa import services


class Command(BaseCommand):
    help = "Remove MFA from a user who lost their authenticator. Prints no secrets."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--yes", action="store_true", help="Confirm the reset.")

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Add --yes to confirm. The user will be able to sign in with a password only.")
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError("User not found.")
        if services.admin_reset(user):
            self.stdout.write(self.style.WARNING(f"MFA removed for '{user.get_username()}'. Ask them to enroll again."))
        else:
            self.stdout.write(f"'{user.get_username()}' had no MFA configured.")
