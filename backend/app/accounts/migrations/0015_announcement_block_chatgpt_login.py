from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0014_visitlog_browser_ip")]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="block_chatgpt_login",
            field=models.BooleanField(default=False, verbose_name="阻止进入 ChatGPT"),
        ),
    ]
