import uuid

from django.db import models, transaction, IntegrityError
from django.db.models import Q, Max, Avg, Count, Sum
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
            total_score=Sum('sessions__score', default=0, filter=condition),
            games_played=Count('sessions', filter=condition),
        )

    def authenticated_only(self):
        return self.filter(user__isnull=False)


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
    player = models.ForeignKey('Player', on_delete=models.CASCADE,
                               related_name='sessions')
    team_name = models.CharField(blank=True, max_length=50)
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
                name='non_negative_speed',
            ),
            models.CheckConstraint(
                check=Q(mistake_ratio__gte=0),
                name='non_negative_mistake_ratio',
            ),
            # models.CheckConstraint(
            #     check=~Q(session__started_at=None)
            #            & ~Q(session__finished_at=None),
            #     name='cant_exist_on_unfinished_session',
            #     violation_error_message="Results cannot be saved on session "
            #                             "that wasn't yet finished",
            # )
            # TODO: implement this constraint via database triggers?
        ]


class GameSessionQuerySet(models.QuerySet):
    def multiplayer_only(self):
        return self.filter(~Q(players_max=1))


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
    # TODO: get rid of redundant is_finished field (replace with state ?)
    is_finished = models.BooleanField(default=False, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    objects = GameSessionQuerySet.as_manager()

    class Meta:
        constraints = [
            CheckConstraint(
                check=(Q(password='') & Q(is_private=False))
                      | Q(is_private=True),
                name='no_password_for_public',
                violation_error_message="Can't set password on public Session",
            ),
            CheckConstraint(
                check=~(Q(started_at=None) & ~Q(finished_at=None)),
                name='cant_be_finished_without_being_started',
                violation_error_message="Session can't be finished if it "
                                        "wasn't yet started",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.password:
            # FIXME: perhaps we shouldn't?
            self.is_private = True  # Enforce
        if self._state.adding and self.password:
            self.set_password(self.password)
        super().save(*args, **kwargs)

    def save_results(self, results: list[dict]):
        """
        Creates result record for each player on this session.
        If called for session that wasn't yet finished, raises IntegrityError.
        """
        if not self.is_finished or self.finished_at is None:
            # Cannot implement this constraint in Django
            # because of ForeignKey relation it requires
            raise IntegrityError

        result_fields = set(
            f.name for f in SessionPlayerResult._meta.get_fields()
        )
        filtered_results = [
            {
                key: result[key]
                for key in result.keys() & result_fields
            }
            for result in results
        ]

        result_objects = list()
        for result in filtered_results:
            r = SessionPlayerResult(session=self, **result)
            r.full_clean()
            result_objects.append(r)

        with transaction.atomic():
            SessionPlayerResult.objects.bulk_create(
                result_objects,
                batch_size=1000,
            )
            self.save()

    def create_from_previous(self, new_mode: str) -> 'GameSession':
        new_session = self.__class__(
            mode=new_mode,
            name=self.name,
            is_private=self.is_private,
            players_max=self.players_max,
            creator=self.creator,
        )
        new_session.full_clean()
        new_session.save()
        return new_session

    def set_password(self, password: str):
        self.password = make_password(password)

    def check_password(self, password: str):
        return check_password(password, self.password)

    def start_game(self):
        """Marks session as started if it wasn't"""
        if self.started_at is None:
            self.started_at = timezone.now()
            self.save()

    def game_over(self):
        """
        Marks session as finished if it wasn't.
        If session wasn't yet started, should raise IntegrityError.
        """
        if not self.is_finished and self.finished_at is None:
            self.finished_at = timezone.now()
            self.is_finished = True
            self.save()
