# Generated by Django 4.1.6 on 2023-02-07 12:27

from django.db import migrations, models


def reassign_teams(apps, schema_editor):
    SessionPlayerResult = apps.get_model('base', 'SessionPlayerResult')
    SessionPlayerResult.objects.filter(team='none').update(
        team='',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0010_alter_gamesession_password_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='sessionplayerresult',
            old_name='winner',
            new_name='is_winner',
        ),
        migrations.AlterField(
            model_name='sessionplayerresult',
            name='team',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.RunPython(
            reassign_teams,
            reverse_code=migrations.RunPython.noop
        ),
    ]
