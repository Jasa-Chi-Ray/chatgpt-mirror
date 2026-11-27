from django.db import migrations, models
from django.utils import timezone
import django.db.models.deletion
import uuid

class Migration(migrations.Migration):
    dependencies=[('accounts','0020_oauth_login_revocation')]
    operations=[
        migrations.CreateModel(name='RetiredUsername',fields=[
            ('name',models.CharField(max_length=200,primary_key=True,serialize=False)),
            ('retired_at',models.DateTimeField(default=timezone.now)),
        ]),
        migrations.CreateModel(name='UserWorkModeSync',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('revision',models.UUIDField(default=uuid.uuid4)),
            ('next_attempt_at',models.DateTimeField(default=timezone.now,db_index=True)),
            ('attempts',models.PositiveIntegerField(default=0)),
            ('user',models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,to='accounts.user')),
        ]),
    ]
