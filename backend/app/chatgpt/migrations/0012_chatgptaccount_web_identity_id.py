from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chatgpt", "0011_account_health_notifications")]
    operations = [migrations.AddField(
        model_name="chatgptaccount", name="web_identity_id",
        field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
    )]
