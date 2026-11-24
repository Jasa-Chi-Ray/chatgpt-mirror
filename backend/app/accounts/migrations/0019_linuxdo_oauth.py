from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('accounts', '0018_login_security_guard')]
    operations = [
        migrations.CreateModel(name='OAuthIdentity', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('provider', models.CharField(max_length=20)),
            ('subject', models.CharField(max_length=64)),
            ('username', models.CharField(max_length=150, blank=True)),
            ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE, related_name='oauth_identities')),
        ], options={'constraints': [
            models.UniqueConstraint(fields=('provider', 'subject'), name='oauth_provider_subject_unique'),
            models.UniqueConstraint(fields=('provider', 'user'), name='oauth_provider_user_unique'),
        ]}),
        migrations.CreateModel(name='OAuthFlow', fields=[
            ('state_digest', models.CharField(max_length=64, primary_key=True, serialize=False)),
            ('browser_digest', models.CharField(max_length=64)),
            ('intent', models.CharField(max_length=10)),
            ('session_digest', models.CharField(max_length=64, blank=True)),
            ('fingerprint', models.JSONField(default=dict)),
            ('stage', models.CharField(max_length=12, default='started')),
            ('result_digest', models.CharField(max_length=64, null=True, unique=True)),
            ('profile', models.JSONField(default=dict)),
            ('expires_at', models.DateTimeField(db_index=True)),
            ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.CASCADE)),
        ]),
    ]
