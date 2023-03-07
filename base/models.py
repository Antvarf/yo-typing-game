import uuid

from django.db import models, transaction
from django.db.models import Q, Max, Avg, Count
from django.db.models.constraints import CheckConstraint
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import (
    make_password,
    check_password,
)
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class GameModes(models.TextChoices):
    SINGLE = 's', 'single'
    IRONWALL = 'i', 'ironwall'
    TUGOFWAR = 't', 'tugofwar'
    ENDLESS = 'e', 'endless'


User = get_user_model()


class StatsQuerySet(models.QuerySet):
    def with_stats(self, mode: str = None):
        if mode is not None:
            if mode not in GameModes.values:
                raise ValueError(f'`{mode}` is not a defined gamemode')
            condition = Q(sessions__session__mode=mode)
        else:
            condition = None
        return self.annotate(
            best_score=Max('sessions__score', default=0, filter=condition),
            best_speed=Max('sessions__speed', default=0, filter=condition),
            avg_score=Avg('sessions__score', default=0, filter=condition),
            avg_speed=Avg('sessions__speed', default=0, filter=condition),
            games_played=Count('sessions', filter=condition),
        )


class Player(models.Model):
    """Stores profile data i.e. player stats and displayed name for user"""
    displayed_name = models.CharField(max_length=50)
    user = models.OneToOneField(User, blank=True, null=True,
                                on_delete=models.CASCADE)

    objects = StatsQuerySet.as_manager()

    def __str__(self):
        return self.displayed_name


@receiver(post_save, sender=User)
def create_player_profile_for_user(sender, instance, created, **kwargs):
    if created:
        Player.objects.create(
            user=instance,
            displayed_name=instance.username,
        )


class SessionPlayerResult(models.Model):
    """Stores game session results per player"""
    session = models.ForeignKey('GameSession',
                                on_delete=models.CASCADE,
                                related_name='results')
    player = models.ForeignKey('Player', on_delete=models.SET_NULL,
                               related_name='sessions', blank=True, null=True)
    team = models.CharField(blank=True, max_length=50)
    score = models.IntegerField()
    speed = models.FloatField()
    mistake_ratio = models.FloatField()
    is_winner = models.BooleanField()
    correct_words = models.PositiveIntegerField()
    incorrect_words = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('session', 'player'),
                name='unique_players_for_game',
            ),
            models.CheckConstraint(
                check=Q(speed__gte=0),
                name="non_negative_speed",
            ),
            models.CheckConstraint(
                check=Q(mistake_ratio__gte=0),
                name="non_negative_mistake_ratio",
            )
        ]


class GameSession(models.Model):
    """Stores information about sessions"""
    mode = models.CharField(max_length=1, choices=GameModes.choices)
    name = models.CharField(max_length=50, blank=True)
    # max_length==128 since we use django.contrib.auth.hashers.make_password()
    # same as for `password` field of `User` from django.contrib.auth.models
    password = models.CharField(max_length=128, blank=True)
    is_private = models.BooleanField(default=False, blank=True)
    players_max = models.PositiveIntegerField(default=0, blank=True)
    players_now = models.PositiveIntegerField(default=0, blank=True)
    creator = models.ForeignKey(
        "Player",
        on_delete=models.CASCADE,
        related_name="sessions_created",
        blank=True,
        null=True,
        )
    session_id = models.UUIDField(
        editable=False,
        unique=True,
        default=uuid.uuid4,
        )
    is_finished = models.BooleanField(default=False, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(password='') & Q(is_private=False)
                      | ~Q(password='') & Q(is_private=True),
                name='force_password_for_private',
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding and self.is_private:
            self.set_password(self.password)
        super().save(*args, **kwargs)

    def save_results(self, results: list[dict]):
        result_objs = [
            SessionPlayerResult(session=self, **result)
            for result in results
        ]
        for obj in result_objs:
            obj.full_clean()
        self.finished_at = timezone.now()
        self.is_finished = True
        with transaction.atomic():
            SessionPlayerResult.objects.bulk_create(result_objs, batch_size=1000)
            self.save()

    def set_password(self, password: str):
        self.password = make_password(password)

    def check_password(self, password: str):
        return check_password(password, self.password)
