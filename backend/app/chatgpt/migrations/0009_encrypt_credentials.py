import app.fields
from django.db import migrations


def encrypt_existing_credentials(apps, schema_editor):
    account_model = apps.get_model("chatgpt", "ChatgptAccount")
    for account in account_model.objects.all().iterator():
        account.save(update_fields=[
            "access_token",
            "session_token",
            "extra_cookies",
            "refresh_token",
            "refresh_client_id",
        ])


class Migration(migrations.Migration):
    dependencies = [("chatgpt", "0008_chatgptaccount_refresh_client_id")]

    operations = [
        migrations.AlterField(
            model_name="chatgptaccount",
            name="access_token",
            field=app.fields.EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name="chatgptaccount",
            name="session_token",
            field=app.fields.EncryptedTextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="chatgptaccount",
            name="extra_cookies",
            field=app.fields.EncryptedJSONField(blank=True, default=list, verbose_name="额外 Cookie"),
        ),
        migrations.AlterField(
            model_name="chatgptaccount",
            name="refresh_token",
            field=app.fields.EncryptedTextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="chatgptaccount",
            name="refresh_client_id",
            field=app.fields.EncryptedTextField(blank=True, null=True),
        ),
        migrations.RunPython(encrypt_existing_credentials, migrations.RunPython.noop),
    ]
