# Generated by Django 3.0.6 on 2020-09-06 15:29

from django.conf import settings
import django.contrib.auth.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0011_update_proxy_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='Player',
            fields=[
                ('user_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL)),
                ('score', models.PositiveIntegerField(default=0)),
                ('speed', models.FloatField(default=0)),
                ('nickname', models.CharField(max_length=255)),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'abstract': False,
            },
            bases=('auth.user',),
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='GameSession',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mode', models.CharField(choices=[('s', 'single'), ('i', 'ironwall'), ('t', 'tugofwar'), ('e', 'endless')], max_length=1)),
                ('players', models.PositiveIntegerField(blank=True, default=0)),
                ('session_id', models.CharField(max_length=64, unique=True)),
                ('creator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sessions_created', to='base.Player')),
            ],
        ),
    ]
