# Generated by Django 4.1.5 on 2023-01-30 01:15

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def generate_displayed_names(apps, schema_editor):
    Player = apps.get_model('base', 'Player')
    Player.objects.filter(displayed_name="").update(displayed_name="Player")


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('base', '0007_stats_transfer'),
    ]

    operations = [
        migrations.RenameField(
            model_name='player',
            old_name='nickname',
            new_name='displayed_name',
        ),
        migrations.AlterField(
            model_name='player',
            name='displayed_name',
            field=models.CharField(default='Player', max_length=50),
            preserve_default=False,
        ),
        migrations.RunPython(generate_displayed_names),
        migrations.AlterField(
            model_name='player',
            name='user',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
    ]