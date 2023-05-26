# Generated by Django 4.2.1 on 2023-05-25 10:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0017_remove_gamesession_no_password_for_public_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='gamesession',
            name='cant_be_finished_without_being_started',
        ),
        migrations.AddConstraint(
            model_name='gamesession',
            constraint=models.CheckConstraint(check=models.Q(('started_at', None), models.Q(('finished_at', None), _negated=True), _negated=True), name='cant_be_finished_without_being_started', violation_error_message="Session can't be finished if it wasn't yet started"),
        ),
    ]