# Generated by Django 4.1.6 on 2023-02-09 20:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0011_rename_winner_sessionplayerresult_is_winner_and_more'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='sessionplayerresult',
            constraint=models.CheckConstraint(check=models.Q(('speed__gte', 0)), name='non_negative_speed'),
        ),
    ]
