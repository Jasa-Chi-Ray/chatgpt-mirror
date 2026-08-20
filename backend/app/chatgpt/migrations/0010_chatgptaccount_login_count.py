from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chatgpt", "0009_encrypt_credentials"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatgptaccount",
            name="login_count",
            field=models.PositiveBigIntegerField(default=0, verbose_name="被登录次数"),
        ),
    ]
