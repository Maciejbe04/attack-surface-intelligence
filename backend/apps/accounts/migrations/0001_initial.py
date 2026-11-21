import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("admin", "Admin"),
                            ("operator", "Operator"),
                            ("analyst", "Analyst"),
                            ("viewer", "Viewer"),
                        ],
                        default="viewer",
                        max_length=32,
                    ),
                ),
                ("mfa_enabled", models.BooleanField(default=False)),
                ("mfa_secret", models.CharField(blank=True, default="", max_length=64)),
                (
                    "mfa_enforced",
                    models.BooleanField(
                        default=False,
                        help_text="When true, user must complete MFA before console access.",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
