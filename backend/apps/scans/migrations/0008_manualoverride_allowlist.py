# Generated manually for overrides + allowlist

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("scans", "0007_observation_index_names"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManualOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entity_key", models.CharField(db_index=True, max_length=512)),
                ("target_address", models.CharField(blank=True, default="", max_length=255)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("notes", models.TextField(blank=True, default="")),
                ("notes_ciphertext", models.TextField(blank=True, default="")),
                ("attrs_patch", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="manual_overrides",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-updated_at", "id")},
        ),
        migrations.CreateModel(
            name="AllowlistEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.CharField(max_length=255)),
                ("entry_type", models.CharField(choices=[("ip", "IP address"), ("cidr", "CIDR range"), ("domain", "Domain")], max_length=16)),
                ("enabled", models.BooleanField(default=True)),
                ("comment", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="allowlist_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("value", "id")},
        ),
        migrations.AddConstraint(
            model_name="manualoverride",
            constraint=models.UniqueConstraint(fields=("owner", "entity_key"), name="scans_manualoverride_owner_key_uniq"),
        ),
        migrations.AddConstraint(
            model_name="allowlistentry",
            constraint=models.UniqueConstraint(fields=("owner", "value"), name="scans_allowlist_owner_value_uniq"),
        ),
    ]
