# Generated by Django 3.0.6 on 2021-02-27 17:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0004_auto_20201228_1115'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gamesession',
            name='finished_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='gamesession',
            name='started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
