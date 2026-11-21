from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scans", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="QueueState",
            fields=[
                (
                    "name",
                    models.CharField(max_length=32, primary_key=True, serialize=False),
                ),
                (
                    "broker_epoch",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name="scanbatch",
            name="queue_recovery_required",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
