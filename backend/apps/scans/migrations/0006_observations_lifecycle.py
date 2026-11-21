# Generated manually for observations, evidence, audit, scan windows.

from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0005_target_groups_schedules"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="scanrun",
            name="window_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional scan window length in seconds; null means no deadline.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="scanrun",
            name="deadline_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="scanrun",
            name="eta_seconds",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="scanrun",
            name="resume_available",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="scanbatch",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                    ("paused", "Paused"),
                ],
                db_index=True,
                default="queued",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="Observation",
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
                ("target_address", models.CharField(db_index=True, max_length=255)),
                (
                    "entity_type",
                    models.CharField(
                        choices=[
                            ("host", "Host"),
                            ("port", "Port"),
                            ("http", "HTTP endpoint"),
                            ("tech", "Technology"),
                            ("cert", "TLS certificate"),
                            ("signature", "Signature match"),
                        ],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("entity_key", models.CharField(db_index=True, max_length=512)),
                (
                    "lifecycle",
                    models.CharField(
                        choices=[
                            ("NEW", "New"),
                            ("CHANGED", "Changed"),
                            ("MISSING", "Missing"),
                            ("FLAKY", "Flaky"),
                            ("GONE", "Gone"),
                            ("UNCHANGED", "Unchanged"),
                        ],
                        db_index=True,
                        default="NEW",
                        max_length=16,
                    ),
                ),
                ("attrs", models.JSONField(blank=True, default=dict)),
                (
                    "source",
                    models.CharField(
                        choices=[("scanner", "Scanner"), ("import", "Import")],
                        default="scanner",
                        max_length=16,
                    ),
                ),
                ("miss_streak", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="observations",
                        to="scans.scanrun",
                    ),
                ),
                (
                    "target",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="observations",
                        to="scans.target",
                    ),
                ),
            ],
            options={
                "ordering": ("entity_type", "entity_key", "id"),
            },
        ),
        migrations.CreateModel(
            name="FingerprintEvidence",
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
                ("kind", models.CharField(default="summary", max_length=32)),
                ("summary", models.CharField(blank=True, default="", max_length=500)),
                ("ciphertext", models.TextField(blank=True, default="")),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "observation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="evidence",
                        to="scans.observation",
                    ),
                ),
            ],
            options={
                "ordering": ("id",),
            },
        ),
        migrations.CreateModel(
            name="AuditLog",
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
                ("action", models.CharField(db_index=True, max_length=64)),
                ("object_type", models.CharField(blank=True, default="", max_length=64)),
                ("object_id", models.CharField(blank=True, default="", max_length=64)),
                ("summary", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-id",),
            },
        ),
        migrations.AddConstraint(
            model_name="observation",
            constraint=models.UniqueConstraint(
                fields=("run", "entity_key"),
                name="scans_observation_run_key_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="observation",
            index=models.Index(
                fields=("run", "lifecycle"),
                name="scans_obser_run_id_lifecycle_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="observation",
            index=models.Index(
                fields=("target_address", "entity_type"),
                name="scans_obser_target__entity_idx",
            ),
        ),
        # Index names are normalized in 0007_observation_index_names.
    ]
