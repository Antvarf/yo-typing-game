from django.core.exceptions import ValidationError
from django.db import (
    transaction,
    IntegrityError,
)
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from base.models import (
    Player,
    GameSession,
    GameModes, SessionPlayerResult,
)


class PlayerTestCase(TestCase):
    """Tests for Player model coverage.

    Ensures that:
        * Players with empty displayed_name cannot be created (min length == 1)
        * User pointer is unique and can be null (on multiple rows)
        * Saving player only creates initial stats when player is being created
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
            * Stats aren't created when
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

    def test_defaults(self):
        """Tests that when not specified:
            * is_private is set to False when not provided
            * players_max is 0 when not provided (no player limit)
            * players_now is 0 after the session is created
            * creator of the session is NULL if not specified
            * session_id is autogenerated
            * is_finished is False when creating
            * created_at is roughly equal to the moment of creation
            * started_at is NULL until session is started
            * finished_at is NULL until session is finished
        """
        stamp_before = timezone.now()
        session = GameSession.objects.create(
            mode=GameModes.SINGLE,
            name="Default session"
        )
        stamp_after = timezone.now()
        self.assertFalse(session.is_private)
        self.assertEqual(session.players_max, 0)
        self.assertEqual(session.players_now, 0)
        self.assertIsNone(session.creator)
        self.assertLessEqual(stamp_before, session.created_at)
        self.assertLessEqual(session.created_at, stamp_after)
        self.assertIsNone(session.started_at)
        self.assertIsNone(session.finished_at)

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
            * can have duplicate rows
            * can't be longer than 50 characters
        """
        duplicate_name_session = GameSession.objects.create(
            name=self.game_session.name,
            mode=self.game_session.mode,
        )
        for name in ('A'*51,):
            with self.assertRaises(ValidationError):
                self.game_session.name = name
                self.game_session.full_clean()

    def test_password_constraints(self):
        """Test that:
            * password must be set for private rooms
            * password can't be set for non-private rooms
            * private room with password can be saved
        """
        with self.assertRaises(ValidationError):
            self.game_session.is_private = True
            self.game_session.password = ''
            self.game_session.full_clean()

        with self.assertRaises(ValidationError):
            self.game_session.is_private = False
            self.game_session.set_password('hehenotempty')
            self.game_session.full_clean()

        self.game_session.is_private = True
        self.game_session.set_password('password')
        self.game_session.full_clean()
        self.game_session.save()

    def test_check_password(self):
        """Test that:
            * password check result is True for correct passwords
            * password check result is False for incorrect passwords
        """
        password = 'hehehehe'
        wrong_password = password+'A'
        self.game_session.is_private = True
        self.game_session.set_password(password)
        self.assertTrue(self.game_session.check_password(password))
        self.assertFalse(self.game_session.check_password(wrong_password))

    def test_session_id(self):
        """Tests that session_id field:
            * Can't be assigned directly and is autogenereated
            * Doesn't allow for duplicate values
        """
        duplicate_uuid_session = GameSession(
            mode=GameModes.SINGLE,
            session_id=self.game_session.session_id,
            name='duolingo is after me',
        )
        with self.assertRaises(ValidationError):
            duplicate_uuid_session.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate_uuid_session.save()


class SessionPlayerResultTestcase(TestCase):
    """Tests that:
        * session can't be NULL (is required)
        * player can be null or a Player instance
        * session and player pointers are unique together
        * team can be blank, can't be longer than 50 characters
        * score can have negative and positive values
        * score is required
        * speed can't have negative values
        * mistake ratio can't have negative values
        * is_winner accepts True or False
        * correct_words, incorrect_words can't have negative values
        * results are deleted with the deletion of player or session
        """
    def setUp(self):
        self.player = Player.objects.create(displayed_name="test_player_1")
        self.session = GameSession.objects.create(
            mode=GameModes.SINGLE,
            name='test_session_1',
        )
        self.player2 = Player.objects.create(displayed_name="test_player_2")
        self.session2 = GameSession.objects.create(
            mode=GameModes.SINGLE,
            name='test_session_2',
        )
        self.result = SessionPlayerResult.objects.create(
            session=self.session,
            player=self.player,
            score=0,
            speed=0,
            mistake_ratio=0,
            is_winner=True,
            correct_words=0,
            incorrect_words=0,
        )
        self.result2 = SessionPlayerResult.objects.create(
            session=self.session2,
            player=self.player2,
            score=0,
            speed=0,
            mistake_ratio=0,
            is_winner=True,
            correct_words=0,
            incorrect_words=0,
        )

    def test_session_field(self):
        """
            * Session field can't be NULL and is required
        """
        self.result.session = None
        with self.assertRaises(ValidationError):
            self.result.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.result.save()

    def test_player_field(self):
        """
            * Player field can be NULL
        """
        self.result.player = None
        self.result.full_clean()
        self.result.save()

    def test_unique_session_player(self):
        """
            * session and player should be unique together
        """
        self.result2.player = self.result.player
        self.result2.session = self.result.session
        with self.assertRaises(ValidationError):
            self.result2.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.result2.save()

        self.result2.player = self.player2
        self.result2.session = self.session
        self.result2.full_clean()
        self.result2.save()

        self.result2.player = self.player
        self.result2.session = self.session2
        self.result2.full_clean()
        self.result2.save()

    def test_team_field(self):
        good_names = ('', 'Weskers', 'A'*50)
        bad_names = ('A'*51,)
        for team_name in good_names:
            self.result.team = team_name
            self.result.full_clean()
            self.result.save()
        for team_name in bad_names:
            self.result.team = team_name
            with self.assertRaises(ValidationError):
                self.result.full_clean()
            # Database-enforced max_length doesn't work with sqlite3
            # with self.assertRaises(IntegrityError):
            #     with transaction.atomic():
            #         self.result.save()

    def test_score_required(self):
        result = SessionPlayerResult(
            session=self.session,
            player=self.player,
            speed=0,
            mistake_ratio=0,
            is_winner=True,
            correct_words=0,
            incorrect_words=0,
        )
        with self.assertRaises(ValidationError):
            result.full_clean()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                result.save()

    def test_score_values(self):
        for score in (-9000, 0, 9000):
            self.result.score = score
            self.result.full_clean()
            self.result.save()

    def test_speed_values(self):
        good_values = (0, 5, 9000)
        bad_values = (-1, -1000)
        for speed in good_values:
            self.result.speed = speed
            self.result.full_clean()
            self.result.save()
        for speed in bad_values:
            self.result.speed = speed
            with self.assertRaises(ValidationError):
                self.result.full_clean()
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self.result.save()

    def test_mistake_ratio(self):
        good_values = (0, 1, 3)
        bad_values = (-0.1, -1)
        for ratio in good_values:
            self.result.mistake_ratio = ratio
            self.result.full_clean()
            self.result.save()
        for ratio in bad_values:
            self.result.mistake_ratio = ratio
            with self.assertRaises(ValidationError):
                self.result.full_clean()
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self.result.save()

    def test_cascade_delete_from_session_and_player(self):
        pass

    # def test_correct_words(self):
    #     good_values = (0, 1, 3, 1024)
    #     bad_values = (-0.1, -1)
    #     for word_count in good_values:
    #         self.result.correct_words = word_count
    #         self.result.full_clean()
    #         self.result.save()
    #     for word_count in bad_values:
    #         self.result.correct_words = word_count
    #         with self.assertRaises(ValidationError):
    #             self.result.full_clean()
    #         with self.assertRaises(IntegrityError):
    #             with transaction.atomic():
    #                 self.result.save()
    #
    # def test_incorrect_words(self):
    #     good_values = (0, 1, 3, 1024)
    #     bad_values = (-0.1, -1)
    #     for word_count in good_values:
    #         self.result.incorrect_words = word_count
    #         self.result.full_clean()
    #         self.result.save()
    #     for word_count in bad_values:
    #         self.result.incorrect_words = word_count
    #         with self.assertRaises(ValidationError):
    #             self.result.full_clean()
    #         with self.assertRaises(IntegrityError):
    #             with transaction.atomic():
    #                 self.result.save()


class PlayerStatsTestCase(TestCase):
    """
    Tests .with_stats() queryset method of Player
    """
    @staticmethod
    def generate_session_results(players, sessions):
        results = [
            SessionPlayerResult(
                player=player,
                session=session,
                score=session.id * player.id,
                speed=session.id * 0.75 * player.id,
                mistake_ratio=session.id * 0.5 * player.id,
                correct_words=session.id * 100 * player.id,
                incorrect_words=session.id * 50 * player.id,
                is_winner=player is players[0],
            )
            for player in players
            for session in sessions
        ]
        SessionPlayerResult.objects.bulk_create(results, batch_size=1000)
        return results

    @staticmethod
    def stats_match_results(stats, results) -> bool:
        """Compares all stats with the ones calculated over given results"""
        best_score, best_speed, avg_score, avg_speed = 0, 0, 0, 0
        if len(results):
            best_score = max(r.score for r in results)
            best_speed = max(r.speed for r in results)
            avg_score = sum(r.score for r in results) // len(results)
            avg_speed = sum(r.speed for r in results) // len(results)
        return all([
            best_score == stats.best_score,
            best_speed == stats.best_speed,
            avg_score == stats.avg_score,
            avg_speed == stats.avg_speed,
        ])

    def setUp(self):
        self.player = Player.objects.create()
        self.other_player = Player.objects.create()
        for i in range(2):
            for mode in GameModes.values:
                GameSession.objects.create(mode=mode)
        self.generate_session_results(
            sessions=GameSession.objects.all(),
            players=(
               self.player,
               self.other_player,
            ),
        )

    def test_general_stats(self):
        """
        Test that .with_stats() with no arguments calculates properly over all
        results belonging only to that specific player for any mode
        """
        stats_qs = Player.objects.with_stats().get(pk=self.player.pk)
        results_qs = SessionPlayerResult.objects.filter(player=self.player)
        self.assertTrue(self.stats_match_results(stats_qs, results_qs))

    def test_mode_stats(self):
        """
        Test that .with_stats with an existing gamemode as an argument
        calculates stats for each mode appropriately
        """
        for mode in GameModes.values:
            stats_qs = Player.objects.with_stats(mode=mode)\
                                     .get(pk=self.player.pk)
            results_qs = SessionPlayerResult.objects.filter(
                player=self.player,
                mode=mode,
            )
            self.assertTrue(self.stats_match_results(stats_qs, results_qs))

    def test_invalid_mode_stats(self):
        """
        Test that .with_stats() with an undefined mode as an argument
        raises ValueError
        """
        mode = '`'
        error_message = f'`{mode}` is not a defined gamemode'
        with self.assertRaisesMessage(ValueError, error_message):
            stats_qs = self.player.with_stats(mode=mode)

    def test_multiple_players(self):
        """Test that .with_stats() works on a queryset of players"""
        players = Player.objects.all().with_stats()
        for p in players:
            results_qs = SessionPlayerResult.objects.filter(player=self.player)
            self.assertTrue(self.stats_match_results)

    def test_empty_players(self):
        """Test that .with_stats() keeps the empty queryset empty"""
        players = Player.objects.none()
        self.assertTrue(players.with_stats().empty())
