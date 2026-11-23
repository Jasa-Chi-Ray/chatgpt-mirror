from django.db import migrations, models
import django.utils.timezone


def initialize_mutex(apps, schema_editor):
    apps.get_model("accounts", "LoginGuardMutex").objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0017_user_multiple_sessions")]
    operations = [
        migrations.CreateModel(name="LoginGuardMutex", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("touched_at", models.DateTimeField(default=django.utils.timezone.now)),
        ]),
        migrations.CreateModel(name="LoginFailureState", fields=[
            ("key", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("account_digest", models.CharField(max_length=64, db_index=True)),
            ("ip", models.GenericIPAddressField()),
            ("failures", models.PositiveIntegerField(default=0)),
            ("fingerprint", models.JSONField(default=dict)),
            ("fingerprint_anchor", models.CharField(max_length=40, blank=True, db_index=True)),
            ("blocked_until", models.DateTimeField(null=True, db_index=True)),
            ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
        ]),
        migrations.AddField(model_name="visitlog", name="failure_count", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="visitlog", name="cooldown_seconds", field=models.PositiveIntegerField(default=0)),
        migrations.RunPython(initialize_mutex, migrations.RunPython.noop),
    ]
