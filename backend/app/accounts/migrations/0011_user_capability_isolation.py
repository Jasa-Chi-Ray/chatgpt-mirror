from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0010_user_authorization_version_gatewayrevocation")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="mcp_isolation",
            field=models.BooleanField(default=True, verbose_name="MCP 隔离"),
        ),
        migrations.AddField(
            model_name="user",
            name="skills_isolation",
            field=models.BooleanField(default=True, verbose_name="Skills 隔离"),
        ),
        migrations.AddField(
            model_name="user",
            name="capability_account_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="capability_policy_initialized",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="mcp_allowlist",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="user",
            name="skills_allowlist",
            field=models.JSONField(default=list),
        ),
    ]
