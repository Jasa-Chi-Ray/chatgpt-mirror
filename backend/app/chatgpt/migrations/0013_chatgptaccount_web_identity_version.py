from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chatgpt", "0012_chatgptaccount_web_identity_id")]
    operations = [migrations.AddField(
        model_name="chatgptaccount", name="web_identity_version",
        field=models.PositiveBigIntegerField(default=0),
    )]
