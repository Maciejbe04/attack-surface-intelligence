from django.core.management.base import BaseCommand

from apps.mfa import services


class Command(BaseCommand):
    help = (
        "Re-encrypt MFA secrets with the current APP_DATA_KEY. Run after rotating the key "
        "while the old one is still listed in APP_DATA_KEY_PREVIOUS."
    )

    def handle(self, *args, **options):
        rotated = services.rotate_encryption()
        self.stdout.write(self.style.SUCCESS(f"Re-encrypted {rotated} MFA secret(s)."))
