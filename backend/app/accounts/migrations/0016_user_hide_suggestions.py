from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_announcement_block_chatgpt_login")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="hide_suggestions",
            field=models.BooleanField(default=False, verbose_name="隐藏建议"),
        ),
    ]
