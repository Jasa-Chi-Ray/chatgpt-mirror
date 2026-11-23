from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0016_user_hide_suggestions")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="allow_multiple_sessions",
            field=models.BooleanField(default=False, verbose_name="允许多会话登录"),
        ),
        migrations.CreateModel(
            name="LoginSession",
            fields=[
                ("key", models.CharField(editable=False, max_length=64, primary_key=True, serialize=False)),
                ("key_digest", models.CharField(editable=False, max_length=64, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
