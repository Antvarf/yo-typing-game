from django.db import models
from django.contrib.auth.models import User


SESSION_ID_LENGTH = 64
GAMEMODE_CHOICES = [
    ('s', 'single'),
    ('i', 'ironwall'),
    ('t', 'tugofwar'),
    ('e', 'endless'),
]


class Player(models.Model):
    """Stores profile data i.e. player stats and displayed name for user"""
    nickname = models.CharField(max_length=255)
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.nickname


class StatsQuerySet(models.QuerySet):
    def overall(self):
        return self.filter(mode=None)

    def mode_stats(self, mode: str):
        return self.filter(mode=mode)

    def updated_from_result(self, result):
        for stats in self:
            stats.update_from_result(score=result.score, speed=result.speed)
        return self


class Stats(models.Model):
    """Stores overall and per-mode stats for each player"""
    mode: str = models.CharField(max_length=1,
                                 choices=GAMEMODE_CHOICES, null=True)
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
        def new_avg(old_avg: int | float, value: int | float, n: int) -> float:
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
    mode = models.CharField(max_length=1, choices=GAMEMODE_CHOICES)
    name = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=384, blank=True)
    private = models.BooleanField(default=False, blank=True)
    players_max = models.PositiveIntegerField(default=0, blank=True)
    players_now = models.PositiveIntegerField(default=0, blank=True)
    creator = models.ForeignKey(
        "Player",
        on_delete=models.CASCADE,
        related_name="sessions_created",
        blank=True,
        null=True,
        )
    session_id = models.CharField(
        max_length=SESSION_ID_LENGTH,
        unique=True,
        )
    finished = models.BooleanField(default=False, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
