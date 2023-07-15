import copy
import time

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from base.game_logic import (
    Event,
    PlayerMessage,
    PlayerController,
    LocalPlayer,
    GameController,
    ControllerStorage,
    GameOverError,
    GameOptions,
    InvalidModeChoiceError,
    PlayerJoinRefusedError,
    InvalidOperationError, WordListProvider,
)
from base.models import (
    GameSession,
    Player,
    GameModes,
)


class WordListProviderTestCase(TestCase):
    def setUp(self):
        self.word_provider = WordListProvider()

    def test_get_new_word_basic(self):
        words_count = len(self.word_provider.words)
        self.word_provider.get_new_word()

        self.assertEqual(len(self.word_provider.words), words_count*2)

    def test_get_new_word_overflow_gets_new_word_page(self):
        words_count = len(self.word_provider.words)

        for i in range(words_count + 1):
            self.word_provider.get_new_word()

        self.assertEqual(len(self.word_provider.words), words_count*3)


class PlayerControllerTestCase(TestCase):
    controller_cls = PlayerController

    def setUp(self):
        self.session = GameSession.objects.create(mode=GameModes.SINGLE)
        self.player = Player.objects.create(displayed_name='test_user_1')
        self.other_player = Player.objects.create(displayed_name='test_user_2')
        self.words = ['haha', 'hehe']
        self.controller = self.controller_cls(session=self.session,
                                              words=self.words)

    def test_init_defaults(self):
        """
        :survival: adds :is_out: field to LocalPlayer
        :race: adds :is_finished: field to LocalPlayer
        :teams: adds :team: field to LocalPlayer, restructures repr
        """
        self.assertEqual(self.controller.player_count, 0)
        self.assertEqual(self.controller.ready_count, 0)
        self.assertEqual(self.controller.voted_count, 0)
        self.assertEqual(self.session.players_now, 0)

        self.assertEqual(self.controller._options.game_duration, 60)
        self.assertEqual(self.controller._options.win_condition,
                         GameOptions.WIN_CONDITION_BEST_SCORE)
        self.assertEqual(self.controller._options.team_mode, False)

    def test_player_init(self):
        local_player_1 = self.controller.add_player(self.player)
        local_player_2 = self.controller.get_player(self.player)

        self.assertEqual(local_player_1, local_player_2)
        self.assertEqual(local_player_1.id, self.player.id)
        self.assertEqual(local_player_1.score, 0)
        self.assertEqual(local_player_1.speed, 0)
        self.assertEqual(local_player_1.is_ready, False)
        self.assertIsNone(local_player_1.time_left)
        self.assertEqual(local_player_1.displayed_name,
                         self.player.displayed_name)

        self.controller.remove_player(self.player)

    def test_add_player_increases_player_count(self):
        self.controller.add_player(self.player)

        self.assertEqual(self.session.players_now, 1)
        self.assertEqual(self.controller.player_count, 1)
        self.assertEqual(self.controller.ready_count, 0)
        self.assertEqual(self.controller.voted_count, 0)

    def test_remove_player_decreases_player_count(self):
        self.controller.add_player(self.player)
        self.controller.add_player(self.other_player)
        self.controller.remove_player(self.player)

        self.assertEqual(self.session.players_now, 1)
        self.assertEqual(self.controller.player_count, 1)
        self.assertEqual(self.controller.ready_count, 0)
        self.assertEqual(self.controller.voted_count, 0)

    def test_remove_player_decreases_ready_voted_counts(self):
        self.controller.add_player(self.player)
        self.controller.add_player(self.other_player)
        self.controller.set_ready_state(self.player, True)
        self.controller.set_ready_state(self.other_player, True)
        self.controller.set_player_vote(self.player, GameModes.SINGLE.label)
        self.controller.set_player_vote(self.other_player,
                                        GameModes.SINGLE.label)
        self.controller.remove_player(self.player)

        self.assertEqual(self.session.players_now, 1)
        self.assertEqual(self.controller.player_count, 1)
        self.assertEqual(self.controller.ready_count, 1)
        self.assertEqual(self.controller.voted_count, 1)

    def test_add_player_cannot_exceed_max_players(self):
        self.session.players_max = 1
        self.controller = self.controller_cls(session=self.session,
                                              words=self.words)
        self.controller.add_player(self.player)

        with self.assertRaisesMessage(PlayerJoinRefusedError,
                                      'Max players limit was reached'):
            self.controller.add_player(self.other_player)

    def test_remove_player_raises_key_error_for_nonexistent_players(self):
        with self.assertRaises(KeyError):
            self.controller.remove_player(self.player)

        self.assertEqual(self.session.players_now, 0)
        self.assertEqual(self.controller.player_count, 0)
        self.assertEqual(self.controller.ready_count, 0)
        self.assertEqual(self.controller.voted_count, 0)

    def test_get_player_raises_key_error_for_nonexistent_players(self):
        with self.assertRaises(KeyError):
            self.controller.get_player(self.player)

    def test_get_player_returns_any_player_without_args(self):
        self.controller.add_player(self.player)
        self.controller.add_player(self.other_player)
        local_player = self.controller.get_player()

        self.assertIsInstance(local_player, LocalPlayer)
        self.assertIn(local_player.id, [self.player.id, self.other_player.id])

    def test_get_player_returns_none_without_args_when_no_players(self):
        self.assertIsNone(self.controller.get_player())

    def test_set_ready_state_increases_player_count_only_once(self):
        self.controller.add_player(self.player)
        self.controller.set_ready_state(self.player, True)
        self.controller.set_ready_state(self.player, True)

        self.assertEqual(self.controller.ready_count, 1)

    def test_set_ready_state_decreases_player_count_only_once(self):
        self.controller.add_player(self.player)
        self.controller.add_player(self.other_player)
        self.controller.set_ready_state(self.player, True)
        self.controller.set_ready_state(self.other_player, True)
        self.controller.set_ready_state(self.player, False)
        self.controller.set_ready_state(self.player, False)

        self.assertEqual(self.controller.ready_count, 1)

    def test_set_ready_state_raises_key_error_for_controller(self):
        with self.assertRaises(KeyError):
            self.controller.set_ready_state(self.player, True)
        self.assertEqual(self.controller.ready_count, 0)

        with self.assertRaises(KeyError):
            self.controller.set_ready_state(self.player, False)
        self.assertEqual(self.controller.ready_count, 0)

    def test_set_player_vote_increases_voted_count_only_once(self):
        self.controller.add_player(self.player)
        self.controller.set_player_vote(self.player, GameModes.SINGLE.label)
        self.controller.set_player_vote(self.player, GameModes.SINGLE.label)

        self.assertEqual(self.controller.voted_count, 1)

    def test_set_player_vote_raises_error_for_invalid_mode_choice(self):
        self.controller.add_player(self.player)
        with self.assertRaisesMessage(InvalidModeChoiceError,
                                      'Cannot select mode `fake_mode`'):
            self.controller.set_player_vote(self.player, 'fake_mode')

        self.assertEqual(self.controller.voted_count, 0)

    def test_set_player_vote_increases_voted_count_once_per_player(self):
        self.controller.add_player(self.player)
        self.controller.set_player_vote(self.player, GameModes.SINGLE.label)
        self.controller.set_player_vote(self.player, GameModes.ENDLESS.label)

        self.assertEqual(self.controller.voted_count, 1)

    def test_set_player_vote_increases_votes_count_once_per_mode(self):
        self.controller.add_player(self.player)
        self.controller.set_player_vote(self.player, GameModes.SINGLE.label)
        self.controller.set_player_vote(self.player, GameModes.SINGLE.label)

        self.assertEqual(self.controller.votes[GameModes.SINGLE.label], 1)

    def test_set_player_vote_raises_key_error_for_nonexistent_player(self):
        with self.assertRaises(KeyError):
            self.controller.set_player_vote(self.player,
                                            GameModes.SINGLE.label)
        self.assertEqual(self.controller.voted_count, 0)

    def test_players_to_dict_without_teams(self):
        """
        If `team_mode` option is False:
            - .to_dict() only contains `players`
            - player representation does not contain `team` field
        """
        self.controller.add_player(self.player)
        dict_repr = self.controller.to_dict()
        players = dict_repr.get('players')
        player = players[0]

        self.assertFalse(self.controller._options.team_mode)
        self.assertNotIn('teams', dict_repr)

        self.assertIsInstance(dict_repr, dict)
        self.assertIsInstance(players, list)
        self.assertIsInstance(player, dict)
        self.assertNotIn('team', player)

    def test_players_to_dict_with_teams(self):
        """
        If `team_mode` option is True, .to_dict() only contains `teams`
        """
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)
        dict_repr = self.controller.to_dict()
        teams = dict_repr.get('teams')
        team_red, team_blue = teams.get('red'), teams.get('blue')
        player = (team_red['players'] or team_blue['players'])[0]

        self.assertTrue(self.controller._options.team_mode)
        self.assertNotIn('players', dict_repr)

        self.assertIsInstance(dict_repr, dict)
        self.assertIsInstance(teams, dict)
        self.assertIsInstance(team_red, dict)
        self.assertIsInstance(team_blue, dict)

        self.assertEqual(teams.keys(), {'red', 'blue'})
        self.assertIn('players', team_red)
        self.assertIn('players', team_blue)
        self.assertIsInstance(player, dict)
        self.assertIn('teamName', player)

    def test_default_add_player_with_teams_distribution(self):
        """Player is added to team with fewer players. Red is the default"""
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)
        dict_repr = self.controller.to_dict()
        team_red_before = dict_repr.get('teams').get('red')
        team_blue_before = dict_repr.get('teams').get('blue')
        red_player = team_red_before['players'][0]

        self.controller.add_player(self.other_player)
        dict_repr = self.controller.to_dict()
        team_red_after = dict_repr.get('teams').get('red')
        team_blue_after = dict_repr.get('teams').get('blue')
        blue_player = team_blue_after['players'][0]

        self.assertEqual(len(team_red_before.get('players')), 1)
        self.assertEqual(len(team_blue_before.get('players')), 0)
        self.assertEqual(len(team_red_after.get('players')), 1)
        self.assertEqual(len(team_blue_after.get('players')), 1)
        self.assertEqual(red_player['teamName'], 'red')
        self.assertEqual(blue_player['teamName'], 'blue')

    def test_set_player_team(self):
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)
        teams = self.controller.to_dict()['teams']
        red_player = teams['red']['players'][0].copy()
        self.controller.set_player_team(player=self.player, team='blue')
        teams = self.controller.to_dict()['teams']
        blue_player = teams['blue']['players'][0].copy()

        self.assertEqual(red_player['id'], blue_player['id'])
        self.assertEqual(red_player['teamName'], 'red')
        self.assertEqual(blue_player['teamName'], 'blue')
        self.assertEqual(len(self.controller.team_red.players), 0)
        self.assertEqual(len(self.controller.team_blue.players), 1)

    def test_set_player_team_with_invalid_team_raises_key_error(self):
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)

        with self.assertRaises(KeyError):
            self.controller.set_player_team(player=self.player, team='invalid')
        player = self.controller.get_player(self.player)

        self.assertEqual(player.team_name, 'red')
        self.assertEqual(len(self.controller.team_red.players), 1)
        self.assertEqual(len(self.controller.team_blue.players), 0)

    def test_set_player_team_raises_key_error_if_player_is_absent(self):
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
            ),
            words=self.words,
        )

        with self.assertRaises(KeyError):
            self.controller.set_player_team(player=self.player, team='red')

        self.assertEqual(len(self.controller.team_red.players), 0)
        self.assertEqual(len(self.controller.team_blue.players), 0)

    def test_set_player_team_changes_nothing_for_the_same_team(self):
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)
        teams_1 = self.controller.to_dict()['teams']
        red_player_1 = teams_1['red']['players'][0].copy()
        self.controller.set_player_team(player=self.player, team='red')
        teams_2 = self.controller.to_dict()['teams']
        red_player_2 = teams_2['red']['players'][0].copy()

        self.assertEqual(red_player_1, red_player_2)
        self.assertEqual(red_player_1['teamName'], 'red')
        self.assertEqual(len(self.controller.team_red.players), 1)
        self.assertEqual(len(self.controller.team_blue.players), 0)

    def test_set_player_team_raises_error_if_teams_are_disabled(self):
        self.controller.add_player(self.player)

        with self.assertRaises(InvalidOperationError):
            self.controller.set_player_team(player=self.player, team='red')

    def test_team_mode_for_survival_moves_time_left(self):
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
                win_condition=GameOptions.WIN_CONDITION_SURVIVED,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)
        teams = self.controller.to_dict()['teams']

        self.assertIn('timeLeft', teams['red'])
        self.assertIn('timeLeft', teams['blue'])
        self.assertNotIn('timeLeft', teams['red']['players'][0])

    def test_team_mode_for_race_moves_time_left(self):
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
                win_condition=GameOptions.WIN_CONDITION_BEST_TIME,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)
        teams = self.controller.to_dict()['teams']

        self.assertIn('timeLeft', teams['red'])
        self.assertIn('timeLeft', teams['blue'])
        # self.assertNotIn('timeLeft', teams['red']['players'][0])

    def test_team_mode_for_competition_moves_time_left(self):
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
                win_condition=GameOptions.WIN_CONDITION_BEST_SCORE,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)
        teams = self.controller.to_dict()['teams']

        self.assertIn('score', teams['red'])
        self.assertIn('score', teams['blue'])
        self.assertIn('score', teams['red']['players'][0])

    def test_username_gets_mangled_for_the_same_in_session(self):
        """
        If player with username same as the one provided is already present
        in the session, given username gets mangled.
        """
        self.duplicate_name_player = Player.objects.create(
            displayed_name=self.player.displayed_name
        )
        old_username = self.duplicate_name_player.displayed_name
        self.controller.add_player(self.player)
        self.controller.add_player(self.duplicate_name_player)
        self.player.refresh_from_db()
        self.duplicate_name_player.refresh_from_db()

        local_player_1 = self.controller.get_player(self.player)
        local_player_2 = self.controller.get_player(
            self.duplicate_name_player,
        )

        new_username = local_player_2.displayed_name

        self.assertNotEqual(old_username, new_username)
        self.assertEqual(old_username, local_player_1.displayed_name)
        self.assertEqual(new_username, local_player_2.displayed_name)
        self.assertEqual(old_username, self.player.displayed_name)
        self.assertEqual(old_username, self.duplicate_name_player.displayed_name)

    # TODO: test explicitly for schema name conversion

    def test_displayed_name_gets_unoccupied_if_player_left(self):
        """
        If player leaves session, his username can be used without alteration
        """
        self.duplicate_name_player = Player.objects.create(
            displayed_name=self.player.displayed_name
        )
        old_username = self.duplicate_name_player.displayed_name
        self.controller.add_player(self.player)
        self.controller.remove_player(self.player)

        self.controller.add_player(self.duplicate_name_player)
        self.player.refresh_from_db()
        self.duplicate_name_player.refresh_from_db()

        local_player_2 = self.controller.get_player(
            self.duplicate_name_player,
        )

        new_username = local_player_2.displayed_name

        self.assertEqual(old_username, new_username)
        self.assertEqual(old_username, self.player.displayed_name)
        self.assertEqual(old_username, self.duplicate_name_player.displayed_name)

    # TODO: cover results schema with tests
    def test_save_results(self):
        self.session.start_game()
        self.session.game_over()
        self.controller.add_player(self.player)
        local_player = self.controller.get_player(self.player)
        local_player.is_winner = True

        self.controller.save_results()
        self.session.results.get()

    def test_save_results_fails_if_session_is_not_finished(self):
        self.controller.add_player(self.player)
        local_player = self.controller.get_player(self.player)
        local_player.is_winner = True

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.controller.save_results()

    def test_save_results_for_teams(self):
        self.controller = self.controller_cls(
            session=self.session,
            options=GameOptions(
                team_mode=True,
            ),
            words=self.words,
        )
        self.controller.add_player(self.player)
        self.session.start_game()
        self.session.game_over()
        local_player = self.controller.get_player(self.player)
        local_player.is_winner = True
        self.controller.save_results()
        result = self.session.results.get()

        self.assertEqual(result.team_name, local_player.team_name)


class BaseTests:
    # FIXME: PEP8
    class GameControllerTestCase(TestCase):
        """
        Tests that:
            * GameController can be instanced only when given GameSession exists
              and is not yet finished or started. Exception is raised otherwise.
            * The controller class is selected based on the GameSession.mode field
            * Provides base events handlers (exposed through .player_event()):
                - 'player_joined'
                - 'player_left'
                - 'word'
                - 'player_vote'
                - 'ready_state'
              and in response sends the messages with defined logic and schema:
                - 'initial_state'
                - 'game_begins'
                - 'start_game'
                - 'new_word'
                - 'game_over'
                - 'votes_update'
                - 'new_game'
        ---
        TODO:
            * test invalid events handling
        """

        controller_cls = GameController
        game_mode = None  # Abstract test case

        def setUp(self):
            self.session_record = GameSession.objects.create(
                mode=self.game_mode,
                name='test_session_1',
            )
            self.player_record = Player.objects.create(
                displayed_name='test_player_1',
            )
            self.other_player_record = Player.objects.create(
                displayed_name='test_player_2',
            )
            self.controller = self.controller_cls(
                session_id=self.session_record.session_id,
            )

        # def test_no_multiple_controllers_for_session(self):
        #     """Only a single controller instance can exist per session"""
        #     with self.assertRaises(ControllerExistsError):
        #         controller = self.controller_cls(
        #             session_id=self.session_record.session_id,
        #         )
        #
        # def test_session_does_not_exist(self):
        #     """Exception is raised if no session with given session_id exists"""
        #     with self.assertRaises(GameSession.DoesNotExist):
        #         with transaction.atomic():
        #             self.controller_cls(session_id=self.session_record.session_id)
        #             # TODO: pass session_id that does not exist

        # def test_session_cannot_be_started_or_finished(self):
        #     """Controller can only be assigned to session at preparation stage"""
        #     self.session_record.start_game()
        #     with self.assertRaises(InvalidGameStateError):
        #         self.controller_cls(session_id=self.session_record.session_id)
        #
        #     self.session_record.save_results(list())
        #     with self.assertRaises(InvalidGameStateError):
        #         self.controller_cls(session_id=self.session_record.session_id)

        def test_player_joined_event(self):
            """
            Player can join if the session is not yet started.
            player_joined is broadcasted on success,
            """
            # TODO: split test into several
            event = Event(
                # we know: - session_id
                #          - username / auth_token -> derive Player object from that
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            players_before = self.session_record.players_now
            server_events = self.controller.player_event(event)
            self.session_record.refresh_from_db()

            initial_state_event, player_joined_event = server_events
            local_player = self.controller._get_player(self.player_record)
            player_object = initial_state_event.data['player']

            self.assertEqual(local_player.id, self.player_record.pk)
            self.assertEqual(local_player.displayed_name,
                             self.player_record.displayed_name)
            self.assertEqual(local_player.score, 0)
            self.assertEqual(local_player.speed, 0)
            self.assertEqual(local_player.correct_words, 0)
            self.assertEqual(local_player.incorrect_words, 0)
            self.assertEqual(local_player.total_word_length, 0)
            self.assertEqual(local_player.time_left, None)
            self.assertEqual(local_player.is_ready, False)
            self.assertIsNone(local_player.voted_for)

            self.assertEqual(player_object, local_player.to_dict())

            self.assertEqual(initial_state_event.type, Event.SERVER_INITIAL_STATE)
            self.assertEqual(initial_state_event.target, Event.TARGET_PLAYER)
            self.assertEqual(
                initial_state_event.data['player'],
                local_player.to_dict(),
            )
            self.assertIs(type(initial_state_event.data['words']), list)
            self.assertTrue(all(
                type(w) == str
                for w in initial_state_event.data['words']
            ))
            # TODO: add check that for two players words are the same
            # self.assertIn('players', initial_state_event.data)

            self.assertEqual(player_joined_event.target, Event.TARGET_ALL)
            self.assertEqual(player_joined_event.type, Event.SERVER_PLAYERS_UPDATE)
            # self.assertIn('players', player_joined_event.data)

            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_player_cannot_join_started_session(self):
            """
            Player can't join if the session is started.
            """
            event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            players_before = self.session_record.players_now
            self.controller._start_game()
            with self.assertRaises(PlayerJoinRefusedError):
                self.controller.player_event(event)
            self.session_record.refresh_from_db()

            self.assertEqual(self.session_record.players_now, players_before)

        def test_player_cannot_join_finished_session(self):
            """
            Player also can't join if the session is finished (at least for now)
            close_connection is expected for this case.
            """
            event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            players_before = self.session_record.players_now
            self.controller._start_game()
            self.controller._game_over()
            with self.assertRaises(PlayerJoinRefusedError):
                self.controller.player_event(event)
            self.session_record.refresh_from_db()

            # TODO: refactor when error message format is defined
            self.assertEqual(self.session_record.players_now, players_before)

        def test_player_joined_twice(self):
            """
            Player joining twice raises PlayerJoinRefusedError.
            """
            event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            players_before = self.session_record.players_now
            self.controller.player_event(event)
            with self.assertRaises(PlayerJoinRefusedError):
                self.controller.player_event(event)
            self.session_record.refresh_from_db()

            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_player_join_cannot_exceed_max_players(self):
            """
            Once session hits its .max_players limit, refuse new joins
            """
            self.session_record.players_max = 1
            self.session_record.save()
            controller = self.controller_cls(
                session_id=self.session_record.session_id,
            )
            p1_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            p2_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            controller.player_event(p1_joined_event)
            players_before = self.session_record.players_now

            with self.assertRaises(PlayerJoinRefusedError):
                controller.player_event(p2_joined_event)

            self.session_record.refresh_from_db()
            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_player_left_event(self):
            """
            Player can leave at any point in time.
            If player leaving was in the session, broadcast notification.
            """
            joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            left_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.player_record),
            )
            players_before = self.session_record.players_now
            self.controller.player_event(joined_event)
            server_events = self.controller.player_event(left_event)
            self.session_record.refresh_from_db()

            # TODO: test _get_player so we can `trust` it
            with self.assertRaises(KeyError):
                self.controller._get_player(self.player_record)

            self.assertEqual(server_events[0].target, Event.TARGET_ALL)
            self.assertEqual(server_events[0].type, Event.SERVER_PLAYERS_UPDATE)
            # self.assertIn('players', server_events[0].data)
            self.assertEqual(self.session_record.players_now, players_before)

        def test_player_leaving_was_not_present(self):
            """
            If player leaving was not in the session, do nothing.
            """
            event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.player_record)
            )
            players_before = self.session_record.players_now
            server_events = self.controller.player_event(event)
            self.session_record.refresh_from_db()

            self.assertEqual(len(server_events), 0)
            self.assertEqual(self.session_record.players_now, players_before)

        def test_ready_state_event(self):
            """
            Player can set the ready state only during the preparation stage.
            If player that's already ready sets ready to true again, nothing is to
            be done. Otherwise, if everyone else is ready, the game should begin.

            TODO: test delayed start_game event (relies on ticks)
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            ready_event = Event(
                type=Event.PLAYER_READY_STATE,
                data=PlayerMessage(player=self.player_record, payload=True)
            )
            self.controller.player_event(join_event)
            server_events = self.controller.player_event(ready_event)
            self.session_record.refresh_from_db()

            players_update_event, game_begins_event = server_events[:2]
            local_player = self.controller._get_player(self.player_record)

            self.assertEqual(local_player.is_ready, True)

            self.assertEqual(players_update_event.target, Event.TARGET_ALL)
            self.assertEqual(players_update_event.type, Event.SERVER_PLAYERS_UPDATE)
            # self.assertIn('players', players_update_event.data) # TODO: check schema in gamemodes

            self.assertEqual(game_begins_event.target, Event.TARGET_ALL)
            self.assertEqual(game_begins_event.type, Event.SERVER_GAME_BEGINS)

            if self.controller._options.start_delay <= 0:
                start_game_event = server_events[2]
                self.assertEqual(start_game_event.target, Event.TARGET_ALL)
                self.assertEqual(start_game_event.type, Event.SERVER_START_GAME)
                self.assertIsNotNone(self.session_record.started_at)
            # .started_at should be set only after SERVER_START_GAME fires

        def test_single_player_max_sets_zero_start_delay(self):
            self.session_record.players_max = 1
            self.session_record.save()
            controller = self.controller_cls(self.session_record.session_id)

            self.assertEqual(controller._options.start_delay, 0.0)

        def test_multiple_players_max_sets_positive_start_delay(self):
            self.session_record.players_max = 2
            self.session_record.save()
            controller = self.controller_cls(self.session_record.session_id)

            self.assertGreater(controller._options.start_delay, 0.0)

        def test_zero_players_max_sets_positive_start_delay(self):
            self.session_record.players_max = 0
            self.session_record.save()
            controller = self.controller_cls(self.session_record.session_id)

            self.assertGreater(controller._options.start_delay, 0.0)

        def test_cannot_set_ready_after_prep_stage(self):
            """
            Player should not be able to change the ready state during any stage
            other than preparation.
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            ready_event = Event(
                type=Event.PLAYER_READY_STATE,
                data=PlayerMessage(player=self.player_record, payload=True)
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            server_events = self.controller.player_event(ready_event)
            self.assertEqual(len(server_events), 0)

            self.controller._game_over()
            server_events = self.controller.player_event(ready_event)
            self.session_record.refresh_from_db()
            self.assertEqual(len(server_events), 0)
            self.assertIsNotNone(self.session_record.started_at)
            self.assertIsNotNone(self.session_record.finished_at)
            self.assertTrue(self.session_record.is_finished)

        def test_player_ready_for_nonexistent_player_yields_nothing(self):
            """
            If ready_state was submitted for player not present
            in the session, message should be discarded
            """
            ready_event = Event(
                type=Event.PLAYER_READY_STATE,
                data=PlayerMessage(player=self.player_record, payload=True)
            )
            server_events = self.controller.player_event(ready_event)

            self.assertEqual(len(server_events), 0)

        def test_player_word_event(self):
            """
            Player can send words only during the gameplay stage. Nothing happens
            otherwise.
            If handled, the new word should be broadcasted for every player. Scores
            should be updated accordingly.
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            initial_state_event, players_update_event_1 = \
                self.controller.player_event(join_event)
            word_event = Event(
                type=Event.PLAYER_WORD,
                data=PlayerMessage(
                    player=self.player_record,
                    payload=initial_state_event.data['words'][0],
                ),
            )

            self.controller._start_game()
            new_word_event, players_update_event_2 = \
                self.controller.player_event(word_event)
            local_player = self.controller._get_player(self.player_record)

            self.assertEqual(new_word_event.type, Event.SERVER_NEW_WORD)
            self.assertEqual(new_word_event.target, Event.TARGET_ALL)
            self.assertIs(type(new_word_event.data), str)

            self.assertEqual(players_update_event_2.type,
                             Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(players_update_event_2.target, Event.TARGET_ALL)

            self.assertGreater(local_player.speed, 0)
            self.assertEqual(local_player.correct_words, 1)

        def test_player_cannot_submit_words_while_prep(self):
            """
            Any word event during PREPARATION stage is discarded
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            word_event = Event(
                type=Event.PLAYER_WORD,
                data=PlayerMessage(player=self.player_record, payload='test_word')
            )
            self.controller.player_event(join_event)
            server_events = self.controller.player_event(word_event)

            self.assertEqual(len(server_events), 0)

        def test_player_cannot_submit_words_while_voting(self):
            """Any word event during VOTING stage is discarded"""
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            word_event = Event(
                type=Event.PLAYER_WORD,
                data=PlayerMessage(player=self.player_record, payload='test_word')
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            self.controller._game_over()
            server_events = self.controller.player_event(word_event)
            # i don't believe that anybody feels the way i do about you now

            self.assertEqual(len(server_events), 0)

        def test_player_vote_event(self):
            """
            Player can supply his vote only during the voting stage. Message should
            be discarded otherwise.
            When handled, the mode voted for should be one of the available ones.
            If selected option is outside of voting scope, return available modes.
            If selected option is one of the available ones, add to the votes.
            Don't add duplicate votes, on every proper vote selection check if
            everyone has voted/check voting timeout if it is set.
            ------------------
            TODO: test timeout
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            vote_event = Event(
                type=Event.PLAYER_MODE_VOTE,
                data=PlayerMessage(player=self.player_record,
                                   payload=GameModes.labels[0]),
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            self.controller._game_over()
            server_events = self.controller.player_event(vote_event)

            self.assertEqual(server_events[0].type, Event.SERVER_VOTES_UPDATE)
            self.assertEqual(server_events[0].target, Event.TARGET_ALL)
            self.assertTrue(issubclass(type(server_events[0].data), list))
            self.assertEqual(set(GameModes.labels),
                             set(i['mode'] for i in server_events[0].data))
            self.assertTrue(all(
                i.keys() == {'mode', 'voteCount'}
                for i in server_events[0].data
            ))

        def test_player_cannot_submit_vote_while_preparation(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            vote_event = Event(
                type=Event.PLAYER_MODE_VOTE,
                data=PlayerMessage(player=self.player_record,
                                   payload=GameModes.labels[0])
            )
            self.controller.player_event(join_event)
            server_events = self.controller.player_event(vote_event)

            self.assertEqual(len(server_events), 0)

        def test_player_cannot_submit_vote_while_playing(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            vote_event = Event(
                type=Event.PLAYER_MODE_VOTE,
                data=PlayerMessage(player=self.player_record,
                                   payload=GameModes.labels[0]),
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            server_events = self.controller.player_event(vote_event)

            self.assertEqual(len(server_events), 0)

        def test_player_cannot_vote_for_undefined_modes(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            vote_event = Event(
                type=Event.PLAYER_MODE_VOTE,
                data=PlayerMessage(player=self.player_record,
                                   payload=GameModes.labels[0] + 'lolidontexist'),
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            self.controller._game_over()
            server_events = self.controller.player_event(vote_event)

            self.assertEqual(server_events[0].type, Event.SERVER_MODES_AVAILABLE)
            self.assertEqual(server_events[0].target, Event.TARGET_PLAYER)
            self.assertIs(type(server_events[0].data), list)
            self.assertTrue(all(
                type(w) == str
                for w in server_events[0].data
            ))

        def test_player_cant_vote_twice_for_the_same_mode(self):
            p1_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            p2_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            vote_event = Event(
                type=Event.PLAYER_MODE_VOTE,
                data=PlayerMessage(player=self.player_record,
                                   payload=GameModes.labels[0]),
            )
            self.controller.player_event(p1_joined_event)
            self.controller.player_event(p2_joined_event)
            self.controller._start_game()
            self.controller._game_over()

            server_events_1 = self.controller.player_event(vote_event)
            server_events_2 = self.controller.player_event(vote_event)

            self.assertEqual(server_events_1, server_events_2)  # vote counts are eq

        def test_new_game_event_schema(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            vote_event = Event(
                type=Event.PLAYER_MODE_VOTE,
                data=PlayerMessage(player=self.player_record,
                                   payload=GameModes.labels[0]),
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            self.controller._game_over()
            _, new_game_event = self.controller.player_event(vote_event)

            self.assertEqual(new_game_event.type, Event.SERVER_NEW_GAME)
            self.assertEqual(new_game_event.target, Event.TARGET_ALL)
            self.assertIsInstance(new_game_event.data, str)

        def test_no_session_creation_for_duplicate_votes(self):
            """
            If last vote needed is submitted multiple times,
            only one new session is created. New votes aren't
            distributed after session creation.
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            vote_event = Event(
                type=Event.PLAYER_MODE_VOTE,
                data=PlayerMessage(player=self.player_record,
                                   payload=GameModes.labels[0]),
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            self.controller._game_over()

            server_events_1 = self.controller.player_event(vote_event)

            count_before = GameSession.objects.count()
            server_events_2 = self.controller.player_event(vote_event)
            count_after = GameSession.objects.count()

            self.assertEqual(count_before, count_after)
            self.assertEqual(server_events_1[0].type, Event.SERVER_VOTES_UPDATE)
            self.assertEqual(server_events_1[1].type, Event.SERVER_NEW_GAME)
            self.assertEqual(len(server_events_2), 0)

        def test_tick_without_host_yields_nothing(self):
            """If host was not set on session, ticks don't trigger"""
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            tick_event = Event(
                type=Event.TRIGGER_TICK,
                data=PlayerMessage(player=self.player_record),
            )
            self.controller.player_event(join_event)
            self.controller._start_game()

            players_update_event = self.controller.player_event(tick_event)

            self.assertEqual(len(players_update_event), 0)

        def test_tick_from_wrong_player_yields_nothing(self):
            """If tick is triggered by non-host player, it is ignored"""
            join_event_1 = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            join_event_2 = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            wrong_tick_event = Event(
                type=Event.TRIGGER_TICK,
                data=PlayerMessage(player=self.other_player_record),
            )
            self.controller.player_event(join_event_1)
            self.controller.player_event(join_event_2)
            self.controller._start_game()

            self.controller.set_host(self.player_record)
            players_update_event = self.controller.player_event(wrong_tick_event)

            self.assertEqual(len(players_update_event), 0)

        def test_tick_before_game_start_yields_nothing(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            ready_event = Event(
                type=Event.PLAYER_READY_STATE,
                data=PlayerMessage(player=self.player_record, payload=True)
            )
            tick_event = Event(
                type=Event.TRIGGER_TICK,
                data=PlayerMessage(player=self.player_record),
            )
            self.controller._options.start_delay = 1
            self.controller.player_event(join_event)
            players_update_event, game_begins_event = \
                self.controller.player_event(ready_event)

            self.controller.set_host(self.player_record)
            tick_response_events = self.controller.player_event(tick_event)

            self.assertEqual(players_update_event.type,
                             Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(game_begins_event.type,
                             Event.SERVER_GAME_BEGINS)
            self.assertEqual(game_begins_event.data,
                             self.controller._options.start_delay)
            self.assertEqual(len(tick_response_events), 0)

        def test_tick_after_game_start_returns_start_game(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            ready_event = Event(
                type=Event.PLAYER_READY_STATE,
                data=PlayerMessage(player=self.player_record, payload=True)
            )
            tick_event = Event(
                type=Event.TRIGGER_TICK,
                data=PlayerMessage(player=self.player_record),
            )
            self.controller._options.start_delay = 0.2
            self.controller.player_event(join_event)
            players_update_event, game_begins_event = \
                self.controller.player_event(ready_event)
            time.sleep(self.controller._options.start_delay)

            self.controller.set_host(self.player_record)
            tick_response_events = self.controller.player_event(tick_event)

            self.assertEqual(players_update_event.type,
                             Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(game_begins_event.type,
                             Event.SERVER_GAME_BEGINS)
            self.assertEqual(game_begins_event.data,
                             self.controller._options.start_delay)
            self.assertEqual(tick_response_events[0].type, Event.SERVER_START_GAME)
            self.assertEqual(tick_response_events[0].target, Event.TARGET_ALL)

        def test_tick_while_playing_updates_players(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            tick_event = Event(
                type=Event.TRIGGER_TICK,
                data=PlayerMessage(player=self.player_record),
            )
            self.controller.player_event(join_event)
            self.controller._start_game()

            self.controller.set_host(self.player_record)
            players_update_event_1, = self.controller.player_event(tick_event)
            players_data_1 = copy.deepcopy(players_update_event_1.data)

            time.sleep(0.5)

            players_update_event_2, = self.controller.player_event(tick_event)
            players_data_2 = copy.deepcopy(players_update_event_2.data)

            self.assertEqual(players_update_event_1.type,
                             Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(players_update_event_2.type,
                             Event.SERVER_PLAYERS_UPDATE)
            # self.assertNotEqual(players_data_1, players_data_2)
            # TODO: test per mode

        def test_tick_while_voting_does_nothing(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            tick_event = Event(
                type=Event.TRIGGER_TICK,
                data=PlayerMessage(player=self.player_record),
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            self.controller._game_over()

            self.controller.set_host(self.player_record)
            server_events = self.controller.player_event(tick_event)

            self.assertEqual(len(server_events), 0)

        def test_player_leaving_can_start_game(self):
            """
            If everyone but the player leaving was ready, then
            the process should be considered finished.
            """
            p1_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            p2_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            p1_ready_event = Event(
                type=Event.PLAYER_READY_STATE,
                data=PlayerMessage(player=self.player_record, payload=True),
            )
            p2_left_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.other_player_record),
            )
            players_before = self.session_record.players_now
            self.controller.player_event(p1_joined_event)
            self.controller.player_event(p2_joined_event)
            self.controller.player_event(p1_ready_event)
            server_events = self.controller.player_event(p2_left_event)
            self.session_record.refresh_from_db()

            self.assertEqual(server_events[0].target, Event.TARGET_ALL)
            self.assertEqual(server_events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(server_events[1].target, Event.TARGET_ALL)
            self.assertEqual(server_events[1].type, Event.SERVER_GAME_BEGINS)
            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_player_leaving_can_end_voting(self):
            """
            If everyone but the player leaving has voted, then end the vote stage.
            """
            p1_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            p2_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            p1_vote_event = Event(
                type=Event.PLAYER_MODE_VOTE,
                data=PlayerMessage(
                    player=self.player_record,
                    payload=GameModes.labels[0],
                ),
            )
            p2_left_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.other_player_record),
            )

            players_before = self.session_record.players_now
            self.controller.player_event(p1_joined_event)
            self.controller.player_event(p2_joined_event)
            self.controller._start_game()
            self.controller._game_over()
            self.controller.player_event(p1_vote_event)
            server_events = self.controller.player_event(p2_left_event)
            self.session_record.refresh_from_db()

            self.assertEqual(server_events[0].target, Event.TARGET_ALL)
            self.assertEqual(server_events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(server_events[1].target, Event.TARGET_ALL)
            self.assertEqual(server_events[1].type, Event.SERVER_NEW_GAME)
            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_game_begins_is_not_fired_while_playing(self):
            """
            Test that if session is not in PREPARATION stage, GAME_BEGINS is not
            triggered on player_leave
            """
            p1_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            p2_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            p1_ready_event = Event(
                type=Event.PLAYER_READY_STATE,
                data=PlayerMessage(player=self.player_record, payload=True),
            )
            p2_left_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.other_player_record),
            )
            players_before = self.session_record.players_now
            self.controller.player_event(p1_joined_event)
            self.controller.player_event(p2_joined_event)
            self.controller.player_event(p1_ready_event)
            self.controller._start_game()
            server_events = self.controller.player_event(p2_left_event)
            self.session_record.refresh_from_db()

            self.assertEqual(server_events[0].target, Event.TARGET_ALL)
            self.assertEqual(server_events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(len(server_events), 1)
            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_game_begins_is_not_fired_while_voting(self):
            """
            Test that if session is not in PREPARATION stage, GAME_BEGINS is not
            triggered on player_leave
            """
            p1_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            p2_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            p1_ready_event = Event(
                type=Event.PLAYER_READY_STATE,
                data=PlayerMessage(player=self.player_record, payload=True),
            )
            p2_left_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.other_player_record),
            )
            players_before = self.session_record.players_now
            self.controller.player_event(p1_joined_event)
            self.controller.player_event(p2_joined_event)
            self.controller.player_event(p1_ready_event)
            self.controller._start_game()
            self.controller._game_over()
            server_events = self.controller.player_event(p2_left_event)
            self.session_record.refresh_from_db()

            self.assertEqual(server_events[0].target, Event.TARGET_ALL)
            self.assertEqual(server_events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(len(server_events), 1)
            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_new_game_is_not_fired_while_prep(self):
            """
            Test that if session is not in VOTING stage, NEW_GAME is not
            triggered on player_leave
            """
            p1_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            p2_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            p2_left_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.other_player_record),
            )
            players_before = self.session_record.players_now
            self.controller.player_event(p1_joined_event)
            self.controller.player_event(p2_joined_event)
            self.controller._player_controller.set_player_vote(
                self.player_record,
                GameModes.SINGLE.label,
            )
            server_events = self.controller.player_event(p2_left_event)
            self.session_record.refresh_from_db()

            self.assertEqual(server_events[0].target, Event.TARGET_ALL)
            self.assertEqual(server_events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(len(server_events), 1)
            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_new_game_is_not_fired_while_game(self):
            """
            Test that if session is not in VOTING stage, NEW_GAME is not
            triggered on player_leave
            """
            p1_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record),
            )
            p2_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            p2_left_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.other_player_record),
            )
            players_before = self.session_record.players_now
            self.controller.player_event(p1_joined_event)
            self.controller.player_event(p2_joined_event)
            self.controller._player_controller.set_player_vote(
                self.player_record,
                GameModes.SINGLE.label,
            )
            self.controller._start_game()
            server_events = self.controller.player_event(p2_left_event)
            self.session_record.refresh_from_db()

            self.assertEqual(server_events[0].target, Event.TARGET_ALL)
            self.assertEqual(server_events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(len(server_events), 1)
            self.assertEqual(self.session_record.players_now, players_before + 1)

        def test_zero_players_after_leave_in_prep_does_not_start_game(self):
            """
            If all players leave while preparation, game does not start or finish.
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            leave_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.player_record)
            )
            self.controller.player_event(join_event)
            events = self.controller.player_event(leave_event)
            self.session_record.refresh_from_db()

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(events[0].target, Event.TARGET_ALL)
            self.assertEqual(self.session_record.players_now, 0)
            self.assertEqual(self.session_record.is_finished, False)
            self.assertIsNone(self.session_record.started_at)
            self.assertIsNone(self.session_record.finished_at)

        def test_zero_players_after_leave_in_game_stops_the_game(self):
            """
            If all players leave while game is active, game finishes immediately.
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            leave_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.player_record)
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            events = self.controller.player_event(leave_event)
            self.session_record.refresh_from_db()

            self.assertEqual(len(events), 2)
            self.assertEqual(events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(events[0].target, Event.TARGET_ALL)
            self.assertEqual(events[1].type, Event.SERVER_GAME_OVER)
            self.assertEqual(events[1].target, Event.TARGET_ALL)
            self.assertEqual(self.session_record.players_now, 0)
            self.assertEqual(self.session_record.is_finished, True)
            self.assertIsNotNone(self.session_record.started_at)
            self.assertIsNotNone(self.session_record.finished_at)

        def test_zero_players_after_leave_in_voting_does_not_create_new_game(self):
            """
            If all players leave while voting is active, no new game is created.
            """
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )
            leave_event = Event(
                type=Event.PLAYER_LEFT,
                data=PlayerMessage(player=self.player_record)
            )
            self.controller.player_event(join_event)
            self.controller._start_game()
            self.controller._game_over()
            events = self.controller.player_event(leave_event)
            self.session_record.refresh_from_db()

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].type, Event.SERVER_PLAYERS_UPDATE)
            self.assertEqual(events[0].target, Event.TARGET_ALL)
            self.assertEqual(self.session_record.players_now, 0)
            self.assertEqual(self.session_record.is_finished, True)
            self.assertIsNotNone(self.session_record.started_at)
            self.assertIsNotNone(self.session_record.finished_at)

        def test_host_id_is_none_if_not_set(self):
            """
            If host was not set on session, it defaults to None
            """
            self.assertIsNone(self.controller.host_id)

        def test_set_host_requires_player_present_in_session(self):
            """
            Test that host player setter expects player record as argument and
            checks it for presence in session
            """
            with self.assertRaises(AttributeError):
                self.controller.host_id = 1

            error_message = f'player {self.player_record} is not in session'
            with self.assertRaisesMessage(ValueError, error_message):
                self.controller.set_host(self.player_record)

            join_event = Event(type=Event.PLAYER_JOINED,
                               data=PlayerMessage(player=self.player_record))
            self.controller.player_event(join_event)
            self.controller.set_host(self.player_record)

            self.assertEqual(self.controller.host_id, self.player_record.pk)

        def test_host_leave_triggers_set_new_host(self):
            join_event = Event(type=Event.PLAYER_JOINED,
                               data=PlayerMessage(player=self.player_record))
            leave_event = Event(type=Event.PLAYER_LEFT,
                                data=PlayerMessage(player=self.player_record))
            self.controller.player_event(join_event)
            self.controller.set_host(self.player_record)

            events = self.controller.player_event(leave_event)

            self.assertEqual(events[0].type, Event.SERVER_NEW_HOST)
            self.assertEqual(events[0].target, Event.TARGET_ALL)
            self.assertEqual(events[0].data, None)

        def test_controller_picks_new_host_if_available(self):
            p1_join_event = Event(type=Event.PLAYER_JOINED,
                                  data=PlayerMessage(player=self.player_record))
            p2_join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.other_player_record),
            )
            p1_leave_event = Event(type=Event.PLAYER_LEFT,
                                   data=PlayerMessage(player=self.player_record))
            self.controller.player_event(p1_join_event)
            self.controller.player_event(p2_join_event)
            self.controller.set_host(self.player_record)

            events = self.controller.player_event(p1_leave_event)

            self.assertEqual(events[0].type, Event.SERVER_NEW_HOST)
            self.assertEqual(events[0].target, Event.TARGET_ALL)
            self.assertEqual(events[0].data, self.other_player_record.id)

        def test_player_join_no_password_fails_for_private(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record)
            )

            self.session_record.is_private = True
            self.session_record.set_password('test_password')
            self.session_record.save()
            self.controller = self.controller_cls(self.session_record.session_id)

            with self.assertRaises(PlayerJoinRefusedError):
                self.controller.player_event(join_event)

        def test_player_join_with_wrong_password_fails(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record,
                                   payload={'password': 'wrong_password'}),
            )

            self.session_record.is_private = True
            self.session_record.set_password('test_password')
            self.session_record.save()
            self.controller = self.controller_cls(self.session_record.session_id)

            with self.assertRaises(PlayerJoinRefusedError):
                self.controller.player_event(join_event)

        def test_player_join_with_correct_password(self):
            join_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(player=self.player_record,
                                   payload={'password': 'test_password'}),
            )

            self.session_record.is_private = True
            self.session_record.set_password('test_password')
            self.session_record.save()
            self.controller = self.controller_cls(self.session_record.session_id)

            self.controller.player_event(join_event)


class SingleGameControllerTestCase(BaseTests.GameControllerTestCase):
    game_mode = GameModes.SINGLE

    # TODO: test other settings do not apply
    # TODO: test for multiple players
    # TODO: check if game over condition is implemented and also
    #       check exactly what changes and what doesn't on good/bad word

    def test_game_options(self):
        self.assertEqual(self.controller._options.game_duration, 60)
        self.assertEqual(self.controller._options.win_condition,
                         GameOptions.WIN_CONDITION_BEST_SCORE)
        self.assertEqual(self.controller._options.team_mode, False)
        self.assertEqual(self.controller._options.speed_up_percent, 0)
        self.assertEqual(self.controller._options.points_difference, 0)
        self.assertEqual(self.controller._options.time_per_word, 0.0)
        self.assertEqual(self.controller._options.strict_mode, False)

    def test_competitors_schema(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        self.controller.player_event(join_event)

        competitors = self.controller._competitors_field
        players = competitors['players']

        player = players[0]

        self.assertIsInstance(player, dict)
        self.assertIn('id', player)
        self.assertIn('score', player)
        self.assertIn('speed', player)
        self.assertIn('isReady', player)
        self.assertIn('timeLeft', player)
        self.assertIn('displayedName', player)

    def test_game_over_condition(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        self.controller.player_event(join_event)

        self.controller._options.game_duration = 0.5
        local_player = self.controller._get_player(self.player_record)

        self.controller._start_game()
        self.assertFalse(self.controller._is_game_over())
        time.sleep(self.controller._options.game_duration)
        self.assertTrue(self.controller._is_game_over())
        self.controller._game_over()
        self.assertTrue(local_player.is_winner)

    def cannot_switch_team_here(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        opposite_team = 'red'
        switch_team_event = Event(
            type=Event.PLAYER_SWITCH_TEAM,
            data=PlayerMessage(
                player=self.player_record,
                payload=opposite_team,
            ),
        )
        local_player = self.controller._get_player(self.player_record)

        with self.assertRaises(InvalidOperationError):
            players_update_event, = self.controller.player_event(switch_team_event)
        self.assertEqual(local_player.team_name, None)


class IronWallGameControllerTestCase(SingleGameControllerTestCase):
    game_mode = GameModes.IRONWALL

    def test_game_options(self):
        self.assertEqual(self.controller._options.game_duration, 60)
        self.assertEqual(self.controller._options.win_condition,
                         GameOptions.WIN_CONDITION_BEST_SCORE)
        self.assertEqual(self.controller._options.team_mode, False)
        self.assertEqual(self.controller._options.speed_up_percent, 0)
        self.assertEqual(self.controller._options.points_difference, 0)
        self.assertEqual(self.controller._options.time_per_word, 0.0)
        self.assertEqual(self.controller._options.strict_mode, True)


class EndlessGameControllerTestCase(BaseTests.GameControllerTestCase):
    game_mode = GameModes.ENDLESS

    def test_game_options(self):
        self.assertEqual(self.controller._options.game_duration, 30)
        self.assertEqual(self.controller._options.win_condition,
                         GameOptions.WIN_CONDITION_SURVIVED)
        self.assertEqual(self.controller._options.team_mode, False)
        self.assertEqual(self.controller._options.speed_up_percent, 40.0)
        self.assertEqual(self.controller._options.points_difference, 0)
        self.assertEqual(self.controller._options.time_per_word, 0.5)
        self.assertEqual(self.controller._options.strict_mode, False)

    def test_correct_word_adds_time_left_to_player(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        trigger_tick_event = Event(
            type=Event.TRIGGER_TICK,
            data=PlayerMessage(
                player=self.player_record,
            ),
        )
        word_event = Event(
            type=Event.PLAYER_WORD,
            data=PlayerMessage(
                player=self.player_record,
                payload=initial_state_event.data['words'][0],
            ),
        )

        self.controller._start_game()
        time.sleep(0.5)
        self.controller.set_host(self.player_record)
        players_update_event_1, = self.controller.player_event(
            trigger_tick_event,
        )

        players_before_submission = players_update_event_1.data['players']
        _, players_update_event_2 = self.controller.player_event(word_event)
        players_after_submission = players_update_event_2.data['players']

        self.assertEqual(players_update_event_2.type,
                         Event.SERVER_PLAYERS_UPDATE)
        self.assertLess(players_before_submission[0]['timeLeft'],
                        players_after_submission[0]['timeLeft'])

    def test_time_left_cannot_exceed_game_duration(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        word_event = Event(
            type=Event.PLAYER_WORD,
            data=PlayerMessage(
                player=self.player_record,
                payload=initial_state_event.data['words'][0],
            ),
        )

        self.controller._start_game()
        _, players_update_event_2 = self.controller.player_event(word_event)
        players_after_submission = players_update_event_2.data['players']

        self.assertEqual(players_update_event_2.type,
                         Event.SERVER_PLAYERS_UPDATE)
        self.assertEqual(self.controller._options.game_duration,
                         players_after_submission[0]['timeLeft'])

    def test_time_left_decreases_exponentially(self):
        """
        BIBUS:
            1. When half the game_duration passes, time_left decreases faster
        ---
        If speed_up_percent:
        1. Controller has the ._increase_time_speed_at
        2. ._time_speed is considered at every tick
        3. When time surpasses ._increase_time_speed_at, it gets recalculated
           in couple with ._time_speed
        Else:
        1. ._time_speed = 1
        """
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        trigger_tick_event = Event(
            type=Event.TRIGGER_TICK,
            data=PlayerMessage(
                player=self.player_record,
            ),
        )
        self.controller._options.game_duration = 2
        self.controller.player_event(join_event)
        self.controller.set_host(self.player_record)
        local_player = self.controller._get_player(self.player_record)

        # Before start
        # TODO: check time_left decrease for a player
        self.assertEqual(self.controller._time_speed, 1)
        self.assertIsNone(self.controller._increase_time_speed_at)
        self.assertIsNone(local_player.time_left)

        # Right after start
        self.controller._start_game()
        self.assertEqual(self.controller._time_speed, 1)
        self.assertEqual(self.controller._increase_time_speed_at,
                         self.controller._session.started_at + timezone.timedelta(seconds=self.controller._options.game_duration / 2))
        self.assertEqual(local_player.time_left, self.controller._options.game_duration)

        # First increase
        sleep_seconds = (self.controller._increase_time_speed_at - timezone.now()).total_seconds()
        time.sleep(sleep_seconds)
        prev_increase = self.controller._increase_time_speed_at
        self.controller.player_event(trigger_tick_event)
        self.assertEqual(self.controller._time_speed,
                         (1 + self.controller._options.speed_up_percent / 100))
        self.assertEqual(self.controller._increase_time_speed_at,
                         prev_increase + timezone.timedelta(seconds=self.controller._options.game_duration / 2 / self.controller._time_speed))
        # time_left decreased with multiplier == 1
        # FIXME: use GreaterEqual and LessEqual for time boundaries instead of this
        self.assertAlmostEqual(
            local_player.time_left,
            self.controller._options.game_duration - (prev_increase - self.controller._session.started_at).total_seconds(),
            places=2,
        )

        # Second increase
        time.sleep((self.controller._increase_time_speed_at - timezone.now()).total_seconds())
        prev_increase = self.controller._increase_time_speed_at
        prev_time_speed = self.controller._time_speed
        self.controller.player_event(trigger_tick_event)
        self.assertEqual(self.controller._time_speed,
                         prev_time_speed * (1 + self.controller._options.speed_up_percent / 100))
        self.assertEqual(self.controller._increase_time_speed_at,
                         prev_increase + timezone.timedelta(seconds=self.controller._options.game_duration / 2 / self.controller._time_speed))
        # time_left decreased with multiplier == 1.4
        self.assertAlmostEqual(
            local_player.time_left,
            self.controller._options.game_duration - (
                        prev_increase - self.controller._session.started_at).total_seconds(),
            places=2,
        )

    def test_is_out_is_initially_false(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        self.controller._start_game()

        self.assertFalse(initial_state_event.data['player']['isOut'])

    def test_is_out_is_true_when_time_left_reaches_zero(self):
        self.controller._options.game_duration = 0.5
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        trigger_tick_event = Event(
            type=Event.TRIGGER_TICK,
            data=PlayerMessage(
                player=self.player_record,
            ),
        )
        initial_state_event, _ = self.controller.player_event(join_event)

        self.controller._start_game()
        time.sleep(self.controller._options.game_duration)

        self.controller.set_host(self.player_record)
        players_update_event_1, _ = self.controller.player_event(
            trigger_tick_event,
        )
        self.assertTrue(players_update_event_1.data['players'][0]['isOut'])

    def test_cannot_submit_words_when_out(self):
        self.controller._options.game_duration = 0.5
        p1_joined_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        p2_joined_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.other_player_record),
        )
        p1_initial_state_event, _ = self.controller.player_event(
            p1_joined_event,
        )
        p2_initial_state_event, _ = self.controller.player_event(
            p2_joined_event,
        )
        p2_word_event = Event(
            type=Event.PLAYER_WORD,
            data=PlayerMessage(
                player=self.player_record,
                payload=p2_initial_state_event.data['words'][0],
            ),
        )
        trigger_tick_event = Event(
            type=Event.TRIGGER_TICK,
            data=PlayerMessage(
                player=self.player_record,
            ),
        )

        local_p1 = self.controller._get_player(self.player_record)
        local_p2 = self.controller._get_player(self.other_player_record)

        self.controller._start_game()
        local_p1.time_left = 9000
        time.sleep(self.controller._options.game_duration)

        self.controller.set_host(self.player_record)
        self.controller.player_event(
            trigger_tick_event,
        )

        p2_score_before = local_p2.score
        self.controller.player_event(p2_word_event)
        p2_score_after = local_p2.score

        self.assertTrue(local_p2.is_out)
        self.assertEqual(local_p2.time_left, 0)
        self.assertEqual(p2_score_before, p2_score_after)

    def test_game_ends_when_player_is_out_for_single(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        trigger_tick_event = Event(
            type=Event.TRIGGER_TICK,
            data=PlayerMessage(
                player=self.player_record,
            ),
        )

        local_p1 = self.controller._get_player(self.player_record)

        self.controller._start_game()
        local_p1.time_left = 0.5
        time.sleep(local_p1.time_left)

        self.controller.set_host(self.player_record)
        _, game_over_event = self.controller.player_event(
            trigger_tick_event,
        )

        self.assertEqual(game_over_event.type, Event.SERVER_GAME_OVER)
        self.assertEqual(game_over_event.target, Event.TARGET_ALL)
        self.assertTrue(local_p1.is_winner)

    def test_game_ends_when_one_player_remains_standing_for_multiple(self):
        p1_joined_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        p2_joined_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.other_player_record),
        )
        p1_initial_state_event, _ = self.controller.player_event(
            p1_joined_event,
        )
        p2_initial_state_event, _ = self.controller.player_event(
            p2_joined_event,
        )
        trigger_tick_event = Event(
            type=Event.TRIGGER_TICK,
            data=PlayerMessage(
                player=self.player_record,
            ),
        )

        local_p1 = self.controller._get_player(self.player_record)
        local_p2 = self.controller._get_player(self.other_player_record)

        self.controller._start_game()
        local_p1.time_left = 9000
        local_p2.time_left = 0.5
        time.sleep(local_p2.time_left)

        self.controller.set_host(self.player_record)
        _, game_over_event = self.controller.player_event(
            trigger_tick_event,
        )

        self.assertEqual(game_over_event.type, Event.SERVER_GAME_OVER)
        self.assertEqual(game_over_event.target, Event.TARGET_ALL)
        self.assertTrue(local_p1.is_winner)
        self.assertFalse(local_p2.is_winner)

    def cannot_switch_team_here(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        opposite_team = 'red'
        switch_team_event = Event(
            type=Event.PLAYER_SWITCH_TEAM,
            data=PlayerMessage(
                player=self.player_record,
                payload=opposite_team,
            ),
        )
        local_player = self.controller._get_player(self.player_record)

        with self.assertRaises(InvalidOperationError):
            players_update_event, = self.controller.player_event(switch_team_event)
        self.assertEqual(local_player.team_name, None)

    # TODO: test schemas


class TugOfWarGameControllerTestCase(SingleGameControllerTestCase):
    game_mode = GameModes.TUGOFWAR

    def test_game_options(self):
        self.assertEqual(self.controller._options.game_duration, 0)
        self.assertEqual(self.controller._options.win_condition,
                         GameOptions.WIN_CONDITION_BEST_SCORE)
        self.assertEqual(self.controller._options.team_mode, True)
        self.assertEqual(self.controller._options.speed_up_percent, 0)
        self.assertEqual(self.controller._options.points_difference, 50)
        self.assertEqual(self.controller._options.time_per_word, 0.0)
        self.assertEqual(self.controller._options.strict_mode, False)

    def test_competitors_schema(self):
        # TODO: make competitors field a common presence in common tests
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        self.controller.player_event(join_event)

        competitors = self.controller._competitors_field
        team_red = competitors['teams']['red']
        team_blue = competitors['teams']['blue']

        player = (team_red['players'] or team_blue['players'])[0]

        self.assertIsInstance(team_red, dict)
        self.assertIsInstance(team_blue, dict)
        self.assertEqual(team_red.keys(), team_blue.keys())

        self.assertEqual(team_red['score'], 0)
        self.assertEqual(team_red['score'], team_blue['score'])
        # TODO: test team schema extensively

        self.assertIsInstance(player, dict)
        self.assertIn('id', player)
        self.assertIn('score', player)
        self.assertIn('speed', player)
        self.assertIn('teamName', player)
        self.assertIn('displayedName', player)

    def test_switch_team_event(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        team_name = initial_state_event.data['player']['teamName']
        opposite_team = 'red' if team_name == 'blue' else 'blue'
        switch_team_event = Event(
            type=Event.PLAYER_SWITCH_TEAM,
            data=PlayerMessage(
                player=self.player_record,
                payload=opposite_team,
            ),
        )

        players_update_event, = self.controller.player_event(switch_team_event)
        new_team = players_update_event.data['teams'][opposite_team]

        self.assertEqual(players_update_event.type,
                         Event.SERVER_PLAYERS_UPDATE)
        self.assertEqual(players_update_event.target,
                         Event.TARGET_ALL)
        self.assertEqual(len(new_team['players']), 1)
        self.assertEqual(new_team['players'][0]['teamName'], opposite_team)

    def cannot_switch_team_after_prep(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        team_name = initial_state_event.data['player']['teamName']
        opposite_team = 'red' if team_name == 'blue' else 'blue'
        switch_team_event = Event(
            type=Event.PLAYER_SWITCH_TEAM,
            data=PlayerMessage(
                player=self.player_record,
                payload=opposite_team,
            ),
        )
        local_player = self.controller._get_player(self.player_record)

        self.controller._start_game()
        with self.assertRaises(InvalidOperationError):
            players_update_event, = self.controller.player_event(switch_team_event)
        self.assertEqual(local_player.team_name, team_name)

        self.controller._game_over()
        with self.assertRaises(InvalidOperationError):
            players_update_event, = self.controller.player_event(switch_team_event)
        self.assertEqual(local_player.team_name, team_name)

    def test_correct_word_increases_team_score(self):
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        initial_state_event, _ = self.controller.player_event(join_event)
        next_word = initial_state_event.data['words'][0]
        word_event = Event(
            type=Event.PLAYER_WORD,
            data=PlayerMessage(player=self.player_record, payload=next_word),
        )

        competitors = self.controller._competitors_field

        player = initial_state_event.data['player']
        team = competitors['teams'][player['teamName']]

        self.assertEqual(team['score'], 0)
        self.controller._start_game()
        _, players_update_event = self.controller.player_event(word_event)

        team = players_update_event.data['teams'][player['teamName']]
        player = team['players'][0]

        self.assertEqual(team['score'], len(next_word))
        self.assertEqual(team['score'], player['score'])

    # TODO: test switch_team event

    def test_game_over_condition(self):
        p1_joined_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        p2_joined_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.other_player_record),
        )
        # TODO: test other conditions do not interfere
        self.controller.player_event(p1_joined_event)
        self.controller.player_event(p2_joined_event)
        self.controller._start_game()
        self.assertFalse(self.controller._is_game_over())

        team_1, team_2 = self.controller._competitors
        team_1.players[0].score = self.controller._options.points_difference

        self.assertGreater(team_1.score, 0)
        self.assertTrue(self.controller._is_game_over())

        self.controller._game_over()
        self.assertTrue(team_1.is_winner)
        self.assertTrue(team_1.players[0].is_winner)


class ControllerStorageTestCase(TestCase):
    storage_class = ControllerStorage
    controller_class = GameController

    def setUp(self):
        self.session_record = GameSession.objects.create()

    def test_get_new_controller(self):
        """If not instantiated, spawn controller"""
        storage_instance = self.storage_class()
        controller = storage_instance.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        self.session_record.refresh_from_db()

        self.assertIsInstance(controller, GameController)
        self.assertEqual(controller._session, self.session_record)

    def test_get_session_reuses_controller(self):
        """If controller was instantiated already, return it instead"""
        storage_instance = self.storage_class()
        controller1 = storage_instance.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        controller2 = storage_instance.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        self.session_record.refresh_from_db()

        self.assertIs(controller1, controller2)
        self.assertEqual(controller1._session, self.session_record)

    def test_instances_use_common_storage(self):
        """Instance A and Instance B should have the common storage variable"""
        storage_instance1 = self.storage_class()
        storage_instance2 = self.storage_class()
        controller1 = storage_instance1.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        controller2 = storage_instance2.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        self.session_record.refresh_from_db()

        self.assertIs(controller1, controller2)
        self.assertEqual(controller1._session, self.session_record)

    def test_get_new_controller_raises_exception_for_started_session(self):
        """Storage class should not supress controller exceptions"""
        storage_instance = self.storage_class()
        self.session_record.start_game()
        with self.assertRaises(GameOverError):
            storage_instance.get_game_controller(
                controller_cls=self.controller_class,
                session_id=self.session_record.session_id,
            )

    def test_get_new_controller_raises_exception_for_finished_session(self):
        """Storage class should not supress controller exceptions"""
        storage_instance = self.storage_class()
        self.session_record.start_game()
        self.session_record.game_over()
        with self.assertRaises(GameOverError):
            storage_instance.get_game_controller(
                controller_cls=self.controller_class,
                session_id=self.session_record.session_id,
            )

    def test_get_new_controller_raises_exception_for_nonexistent_session(self):
        """Storage class should not supress controller exceptions"""
        storage_instance = self.storage_class()
        self.session_record.delete()
        with self.assertRaises(GameSession.DoesNotExist):
            storage_instance.get_game_controller(
                controller_cls=self.controller_class,
                session_id=self.session_record.session_id,
            )

    def test_delete_controller_on_zero_users(self):
        """When <=0 users, pop controller from list"""
        storage_instance = self.storage_class()
        controller1 = storage_instance.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        storage_instance.remove_game_controller(
            session_id=self.session_record.session_id,
        )

        controller2 = storage_instance.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        self.assertIsNot(controller1, controller2)  # The new one was spawned

    def test_keep_controller_for_other_users_after_removing(self):
        """If user counter is > 1 on remove, keep the controller instance"""
        storage_instance = self.storage_class()
        controller1 = storage_instance.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        controller2 = storage_instance.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        storage_instance.remove_game_controller(
            session_id=self.session_record.session_id,
        )

        controller3 = storage_instance.get_game_controller(
            controller_cls=self.controller_class,
            session_id=self.session_record.session_id,
        )
        self.assertIs(controller2, controller3) # The old one was reused

    def test_remove_nonexistent_controller_does_not_fail(self):
        """If controller doesn't exist, return"""
        storage_instance = self.storage_class()
        storage_instance.remove_game_controller(
            session_id=self.session_record.session_id,
        )
