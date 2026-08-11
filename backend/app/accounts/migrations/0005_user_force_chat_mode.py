from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_user_quotas")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="force_chat_mode",
            field=models.BooleanField(default=True, verbose_name="自动退出 Work 模式"),
        ),
    ]
