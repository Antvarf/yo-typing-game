from django.core.exceptions import ValidationError
from django.db import (
    transaction,
    IntegrityError,
)
from django.test import TestCase
from django.contrib.auth import get_user_model

from base.models import (
    Player,
    GameSession,
    GameModes,
)


class PlayerTestCase(TestCase):
    """Tests for Player model coverage.

    Ensures that:
        * Players with empty displayed_name cannot be created (min length == 1)
        * User pointer is unique and can be null (on multiple rows)
    """

    def setUp(self):
        User = get_user_model()
        users = [
            {"username": "test_user_1", "password": "test_user_1_password"},
        ]
        self._users = list(User.objects.create_user(**user) for user in users)

    def test_user_relation(self):
        """Test that for user field:
            * User field values are unique
            * NULL values for multiple rows are possible
        """
        player1 = Player.objects.create(displayed_name="A", user=self._users[0])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                user_duplicate = Player.objects.create(displayed_name="B",
                                                       user=self._users[0])

        anon_player1 = Player.objects.create(displayed_name="C")
        anon_player2 = Player.objects.create(displayed_name="D")

    def test_displayed_name(self):
        """Test that for displayed_name field:
            * Minimum length allowed is 1
            ? Maximum length allowed is 50
            * Duplicates are allowed
        """
        p1 = Player.objects.create(displayed_name="A")
        p1_duplicate = Player.objects.create(displayed_name=p1.displayed_name)
        p2 = Player.objects.create(displayed_name="A"*50)
        with self.assertRaises(ValidationError):
            p1.displayed_name = ""
            p1.full_clean()
        with self.assertRaises(ValidationError):
            p2.displayed_name += "A"
            p2.full_clean()

    def test_stats_creation(self):
        """Tests that for every player created:
            * Overall stats are automatically created and properly initialized
            * For each mode stats are also created and properly initialized
        """
        def stats_equal_zero(stats):
            return not any([
                stats.avg_score,
                stats.avg_speed,
                stats.best_score,
                stats.best_speed,
                stats.games_played,
            ])
        player = Player.objects.create(displayed_name="A")
        stats_qs = player.stats.all()

        overall_stats = stats_qs.overall().get()
        self.assertTrue(stats_equal_zero(overall_stats))

        modes = GameModes.values
        for mode in modes:
            mode_stats = stats_qs.for_gamemode(mode).get()
            self.assertTrue(stats_equal_zero(mode_stats))


class GameSessionTestCase(TestCase):
    """Test that for each GameSession row:
        * only valid gamemodes (GAMEMODES_CHOICES) are allowed
        * name can't be blank or longer than 50 chars
        * password can be blank ONLY if room is not private
        * is_private is set to False when not provided
        * players_max is 0 when not provided (no restriction)
        * players_now is 0 after the session is created
        * creator of the session can be NULL if creator is anonymous
        * session_ids are unique
        * is_finished is False when creating
        * created_at
        * started_at is NULL until session is started
        * finished_at is NULL until session is finished
    """
    def setUp(self):
        self.game_session = GameSession.objects.create(
            mode=GameModes.SINGLE,
            name="Test session 1",
        )

    def test_gamemodes(self):
        """Test that mode field:
            * accepts defined values for GameMode
            * doesn't accept blank values
            * doesn't accept values longer than 1
            * doesn't accept values outside of GameMode.values()
        """
        modes = GameModes.values
        for mode in modes:
            self.game_session.mode = mode
            self.game_session.full_clean()
            self.game_session.save()
        invalid_modes = ('', '`', 'mode_name_too_long')
        for mode in invalid_modes:
            with self.assertRaises(ValidationError):
                self.game_session.mode = mode
                self.game_session.full_clean()

    def test_name(self):
        """Test that name field:
            * can't have duplicate rows
            * can't be blank or longer than 50 characters
        """
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate_session = GameSession.objects.create(
                    name=self.game_session.name,
                    mode=self.game_session.mode,
                )
        for name in ('', 'A'*51):
            with self.assertRaises(ValidationError):
                self.game_session.name = name
                self.game_session.full_clean()

    def test_private_rooms(self):
        pass

class SessionPlayerResultTestcase(TestCase):
    pass
