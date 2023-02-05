import uuid
from typing import Union

from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import (
    make_password,
    check_password,
)


class GameModes(models.TextChoices):
    SINGLE = 's', 'single'
    IRONWALL = 'i', 'ironwall'
    TUGOFWAR = 't', 'tugofwar'
    ENDLESS = 'e', 'endless'


User = get_user_model()
_DEPRECATED_SESSION_ID_LENGTH = 64


class Player(models.Model):
    """Stores profile data i.e. player stats and displayed name for user"""
    displayed_name = models.CharField(max_length=50)
    user = models.OneToOneField(User, blank=True, null=True,
                                on_delete=models.CASCADE)

    def __str__(self):
        return self.displayed_name

    def save(self, *args, **kwargs):
        is_created = self._state.adding
        super().save(*args, **kwargs)
        if is_created:
            Stats.objects.create_player_stats(player=self)


class StatsQuerySet(models.QuerySet):
    def overall(self):
        return self.filter(mode=None)

    def for_gamemode(self, mode: str):
        return self.filter(mode=mode)

    def updated_from_result(self, result):
        for stats in self:
            stats.update_from_result(score=result.score, speed=result.speed)
        return self

    def create_player_stats(self, player):
        modes = GameModes.values
        stats = [Stats(mode=mode, player=player) for mode in (None, *modes)]
        return self.bulk_create(stats)


class Stats(models.Model):
    """Stores overall and per-mode stats for each player"""
    mode: str = models.CharField(max_length=1,
                                 choices=GameModes.choices, null=True)
    player: int = models.ForeignKey('Player',
                                    related_name='stats',
                                    on_delete=models.CASCADE)
    avg_score: int = models.IntegerField(default=0)
    best_score: int = models.IntegerField(default=0)
    avg_speed: float = models.FloatField(default=0)
    best_speed: float = models.FloatField(default=0)
    games_played: int = models.PositiveIntegerField(default=0)

    objects = StatsQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('mode', 'player'),
                name='unique_player_mode_stats',
            ),
        ]

    def update_from_result(self, score: int, speed: float) -> None:
        def new_avg(old_avg: Union[int, float], value: Union[int, float], n: int) -> float:
            return (old_avg*n + value) / (n + 1)

        self.best_score = max(self.best_score, score)
        self.avg_score = round(
            new_avg(self.avg_score, score, self.games_played))
        self.best_speed = max(self.best_speed, speed)
        self.avg_speed = new_avg(self.avg_speed, speed, self.games_played)
        self.games_played += 1


class SessionPlayerResult(models.Model):
    """Stores game session results per player"""
    session = models.ForeignKey('GameSession',
                                on_delete=models.CASCADE,
                                related_name='players')
    player = models.ForeignKey('Player', on_delete=models.CASCADE,
                               related_name='sessions', blank=True, null=True)
    team = models.CharField(default='none', blank=True, max_length=255)
    score = models.IntegerField()
    speed = models.FloatField()
    mistake_ratio = models.FloatField()
    winner = models.BooleanField()
    correct_words = models.PositiveIntegerField()
    incorrect_words = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('session', 'player'),
                name='unique_players_for_game',
            ),
        ]


class GameSession(models.Model):
    """Stores information about sessions"""
    mode = models.CharField(max_length=1, choices=GameModes.choices)
    name = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=384, blank=True)
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

    def save(self, *args, **kwargs):
        if self._state.adding and self.is_private:
            self.set_password(self.password)
        super().save(*args, **kwargs)

    def set_password(self, password: str):
        self.password = make_password(password)

    def check_password(self, password: str):
        return check_password(password, self.password)
