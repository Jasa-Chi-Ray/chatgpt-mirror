from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_user_ui_visibility")]

    operations = [
        migrations.AddField(
            model_name="visitlog",
            name="browser_ip",
            field=models.GenericIPAddressField(
                null=True, blank=True, verbose_name="浏览器检测IP（参考）"
            ),
        ),
    ]
