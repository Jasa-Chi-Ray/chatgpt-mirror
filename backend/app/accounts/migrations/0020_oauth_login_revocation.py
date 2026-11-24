from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0019_linuxdo_oauth')]

    operations = [
        migrations.AddField(
            model_name='pendinglogin', name='oauth_identity',
            field=models.ForeignKey(to='accounts.oauthidentity', null=True, editable=False,
                on_delete=django.db.models.deletion.CASCADE, related_name='pending_logins'),
        ),
        migrations.AddField(
            model_name='oauthflow', name='admitted_session',
            field=models.BooleanField(default=False),
        ),
    ]
