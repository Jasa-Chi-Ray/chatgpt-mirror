from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_user_allow_admin_view_conversation_titles")]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="start_at",
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name="开始时间"),
        ),
        migrations.AddField(
            model_name="announcement",
            name="end_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="结束时间"),
        ),
        migrations.AddField(
            model_name="announcement",
            name="display_timezone",
            field=models.CharField(default="Asia/Shanghai", max_length=64, verbose_name="显示时区"),
        ),
    ]
