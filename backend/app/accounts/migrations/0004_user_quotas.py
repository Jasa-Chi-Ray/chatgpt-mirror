from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_user_expired_date")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="daily_quota",
            field=models.PositiveIntegerField(default=0, verbose_name="每日配额"),
        ),
        migrations.AddField(
            model_name="user",
            name="monthly_quota",
            field=models.PositiveIntegerField(default=0, verbose_name="每月配额"),
        ),
    ]
