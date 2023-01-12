from django.db import models
from django.contrib.auth.models import User


SESSION_ID_LENGTH = 64
GAMEMODES = [
    ("s", "single"),
    ("i", "ironwall"),
    ("t", "tugofwar"),
    ("e", "endless"),
    ]


class Player(User):
    best_classic_score = models.PositiveIntegerField(default=0)
    best_endless_score = models.PositiveIntegerField(default=0)
    best_ironwall_score = models.PositiveIntegerField(default=0)
    best_tugofwar_score = models.PositiveIntegerField(default=0)

    avg_classic_score = models.PositiveIntegerField(default=0)
    avg_endless_score = models.PositiveIntegerField(default=0)
    avg_ironwall_score = models.PositiveIntegerField(default=0)
    avg_tugofwar_score = models.PositiveIntegerField(default=0)

    games_played = models.PositiveIntegerField(default=0)
    classic_played = models.PositiveIntegerField(default=0)
    endless_played = models.PositiveIntegerField(default=0)
    ironwall_played = models.PositiveIntegerField(default=0)
    tugofwar_played = models.PositiveIntegerField(default=0)

    best_speed = models.FloatField(default=0)
    avg_speed = models.FloatField(default=0)

    nickname = models.CharField(max_length=255)
    score = models.PositiveIntegerField(default=0)


class SessionPlayerResult(models.Model):
    username = models.CharField(max_length=255)
    score = models.IntegerField()
    speed = models.FloatField()
    mistake_ratio = models.FloatField()
    player = models.ForeignKey(
        "Player",
        on_delete=models.CASCADE,
        related_name="sessions",
        blank=True,
        null=True,
        )
    team = models.CharField(default="none", blank=True, max_length=255)
    winner = models.BooleanField()
    correct_words = models.PositiveIntegerField()
    incorrect_words = models.PositiveIntegerField()
    session = models.ForeignKey(
        "GameSession",
        on_delete=models.CASCADE,
        related_name="players",
        )


class GameSession(models.Model):
    mode = models.CharField(max_length=1, choices=GAMEMODES)
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
