import app.fields
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chatgpt", "0010_chatgptaccount_login_count")]

    operations = [
        migrations.CreateModel(
            name="AccountHealthSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("enabled", models.BooleanField(default=False)),
                ("interval_minutes", models.PositiveIntegerField(default=5)),
                ("recipient", models.EmailField(blank=True, max_length=254)),
                ("smtp_host", models.CharField(blank=True, max_length=253)),
                ("smtp_port", models.PositiveIntegerField(default=465)),
                ("smtp_security", models.CharField(default="ssl", max_length=8)),
                ("smtp_username", models.EmailField(blank=True, max_length=254)),
                ("smtp_password", app.fields.EncryptedTextField(blank=True, default="")),
                ("imap_host", models.CharField(blank=True, max_length=253)),
                ("imap_port", models.PositiveIntegerField(default=993)),
                ("imap_security", models.CharField(default="ssl", max_length=8)),
                ("imap_username", models.CharField(blank=True, max_length=254)),
                ("imap_password", app.fields.EncryptedTextField(blank=True, default="")),
                ("revision", models.PositiveIntegerField(default=0)),
                ("last_sent_at", models.DateTimeField(blank=True, null=True)),
                ("last_mail_error", models.CharField(blank=True, max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name="AccountHealthState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("next_check_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("first_failure_at", models.DateTimeField(blank=True, null=True)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("notified", models.BooleanField(default=False)),
                ("detail", models.CharField(blank=True, max_length=200)),
                ("lease_until", models.DateTimeField(blank=True, null=True)),
                ("lease_token", models.CharField(blank=True, max_length=32)),
                ("account", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to="chatgpt.chatgptaccount")),
            ],
        ),
    ]
