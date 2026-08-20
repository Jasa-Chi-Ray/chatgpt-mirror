from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_announcement"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="allow_admin_view_conversation_titles",
            field=models.BooleanField(default=False, verbose_name="允许管理员查看对话标题"),
        ),
    ]
