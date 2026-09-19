from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0011_user_capability_isolation")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="model_isolation",
            field=models.BooleanField(default=True, verbose_name="模型隔离"),
        ),
        migrations.AddField(
            model_name="user",
            name="model_policies",
            field=models.JSONField(default=list),
        ),
    ]
