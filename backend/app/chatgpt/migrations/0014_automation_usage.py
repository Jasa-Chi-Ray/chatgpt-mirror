from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("chatgpt", "0013_chatgptaccount_web_identity_version"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="chatgptaccount", name="automation_owner", field=models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, related_name="automated_accounts", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="chatgptaccount", name="usage_snapshot", field=models.JSONField(default=dict, blank=True)),
        migrations.AddField(model_name="chatgptaccount", name="usage_checked_at", field=models.BigIntegerField(null=True, blank=True)),
        migrations.AddField(model_name="chatgptaccount", name="usage_next_check_at", field=models.BigIntegerField(default=0, db_index=True)),
        migrations.CreateModel(name="AccountUsageSchedule", fields=[("id", models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False, serialize=False)), ("next_dispatch_at", models.BigIntegerField(default=0)), ("lease_until", models.BigIntegerField(default=0)), ("lease_token", models.CharField(max_length=32, blank=True))]),
    ]
