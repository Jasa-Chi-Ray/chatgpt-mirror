from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_announcement_schedule")]
    operations = [
        migrations.CreateModel(
            name="VisitorSession",
            fields=[
                ("sid", models.CharField(max_length=32, primary_key=True, serialize=False)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="PendingLogin",
            fields=[
                ("digest", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("password_digest", models.CharField(max_length=64)),
                ("csrf_digest", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("visitor", models.BooleanField(default=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
