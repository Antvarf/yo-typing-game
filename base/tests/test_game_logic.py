import copy
import time

from django.db import transaction
from django.test import TestCase

from base.game_logic import (
    Event,
    PlayerMessage,
    InvalidGameStateError,
    ControllerExistsError,
    SingleGameController,
    PlayerJoinRefusedError,
    ControllerStorage,
    BaseGameController,
    GameOverError,
)
from base.models import (
    GameSession,
    Player,
    GameModes,
)


class WordListProviderTestCase(TestCase):
    pass


class BasePlayerControllerTestCase(TestCase):
    pass


class PlayerPlainControllerTestCase(TestCase):
    pass


class SingleGameControllerTestCase(TestCase):
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
        * make this test case inheritable so that it applies to every game mode
        * test invalid events handling
    """
    controller_cls = SingleGameController

    def setUp(self):
        self.session_record = GameSession.objects.create(
            mode=GameModes.SINGLE,
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
        self.assertIn('players', initial_state_event.data)

        self.assertEqual(player_joined_event.target, Event.TARGET_ALL)
        self.assertEqual(player_joined_event.type, Event.SERVER_PLAYERS_UPDATE)
        self.assertIn('players', player_joined_event.data)

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
        local_player = self.controller._get_player(self.player_record)
        self.assertIsNone(local_player)

        self.assertEqual(server_events[0].target, Event.TARGET_ALL)
        self.assertEqual(server_events[0].type, Event.SERVER_PLAYERS_UPDATE)
        self.assertIn('players', server_events[0].data)
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
        self.assertIn('players', players_update_event.data)

        self.assertEqual(game_begins_event.target, Event.TARGET_ALL)
        self.assertEqual(game_begins_event.type, Event.SERVER_GAME_BEGINS)

        if self.controller.START_GAME_DELAY <= 0:
            start_game_event = server_events[2]
            self.assertEqual(start_game_event.target, Event.TARGET_ALL)
            self.assertEqual(start_game_event.type, Event.SERVER_START_GAME)
            self.assertIsNotNone(self.session_record.started_at)
        # .started_at should be set only after SERVER_START_GAME fires

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
        word_event = Event(
            type=Event.PLAYER_WORD,
            data=PlayerMessage(player=self.player_record, payload='test_word')
        )
        _, players_update_event_1 = self.controller.player_event(join_event)
        players_before_submission = copy.deepcopy(players_update_event_1.data)

        self.controller._start_game()
        new_word_event, players_update_event_2 =\
            self.controller.player_event(word_event)
        players_after_submission = players_update_event_2.data

        self.assertEqual(new_word_event.type, Event.SERVER_NEW_WORD)
        self.assertEqual(new_word_event.target, Event.TARGET_ALL)
        self.assertIs(type(new_word_event.data), str)

        self.assertEqual(players_update_event_2.type,
                         Event.SERVER_PLAYERS_UPDATE)
        self.assertEqual(players_update_event_2.target, Event.TARGET_ALL)
        self.assertNotEqual(players_before_submission,
                            players_after_submission)

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
        self.assertTrue(issubclass(type(server_events[0].data), dict))
        self.assertTrue(all(
            mode in GameModes.labels and type(count) is int
            for mode, count
            in server_events[0].data.items()
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
                               payload=GameModes.labels[0]+'lolidontexist'),
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

        self.assertEqual(server_events_1, server_events_2) # vote counts are eq

    def test_no_session_creation_with_zero_votes(self):
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
        self.controller.START_GAME_DELAY = 1
        self.controller.player_event(join_event)
        players_update_event, game_begins_event =\
            self.controller.player_event(ready_event)

        self.controller.set_host(self.player_record)
        tick_response_events = self.controller.player_event(tick_event)

        self.assertEqual(players_update_event.type,
                         Event.SERVER_PLAYERS_UPDATE)
        self.assertEqual(game_begins_event.type,
                         Event.SERVER_GAME_BEGINS)
        self.assertEqual(game_begins_event.data,
                         self.controller.START_GAME_DELAY)
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
        self.controller.START_GAME_DELAY = 0.2
        self.controller.player_event(join_event)
        players_update_event, game_begins_event = \
            self.controller.player_event(ready_event)
        time.sleep(self.controller.START_GAME_DELAY)

        self.controller.set_host(self.player_record)
        tick_response_events = self.controller.player_event(tick_event)

        self.assertEqual(players_update_event.type,
                         Event.SERVER_PLAYERS_UPDATE)
        self.assertEqual(game_begins_event.type,
                         Event.SERVER_GAME_BEGINS)
        self.assertEqual(game_begins_event.data,
                         self.controller.START_GAME_DELAY)
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
        self.assertNotEqual(players_data_1, players_data_2)

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
        self.controller._player_controller.set_player_vote(
            self.player_record.pk,
            GameModes.SINGLE,
        )
        p2_left_event = Event(
            type=Event.PLAYER_LEFT,
            data=PlayerMessage(player=self.other_player_record),
        )
        players_before = self.session_record.players_now
        self.controller.player_event(p1_joined_event)
        self.controller.player_event(p2_joined_event)
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
        self.controller._player_controller.set_player_vote(
            self.player_record.pk,
            GameModes.SINGLE,
        )
        p2_left_event = Event(
            type=Event.PLAYER_LEFT,
            data=PlayerMessage(player=self.other_player_record),
        )
        players_before = self.session_record.players_now
        self.controller.player_event(p1_joined_event)
        self.controller.player_event(p2_joined_event)
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

    def test_username_gets_mangled_for_the_same_in_session(self):
        """
        If player with username same as the one provided is already present
        in the session, given username gets mangled.
        """
        old_username = self.player_record.displayed_name
        self.duplicate_name_player_record = Player.objects.create(
            displayed_name=self.player_record.displayed_name
        )
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        duplicate_name_join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.duplicate_name_player_record)
        )
        self.controller.player_event(join_event)
        initial_state_event, _ = self.controller.player_event(
            duplicate_name_join_event
        )
        self.duplicate_name_player_record.refresh_from_db()
        self.player_record.refresh_from_db()

        p1_object = self.controller._get_player(
            self.player_record
        )
        p2_object = self.controller._get_player(
            self.duplicate_name_player_record
        )

        new_username = initial_state_event.data['player']['displayed_name']

        self.assertEqual(initial_state_event.type, Event.SERVER_INITIAL_STATE)
        self.assertNotEqual(old_username, new_username)
        self.assertEqual(old_username, p1_object.displayed_name)
        self.assertEqual(new_username, p2_object.displayed_name)
        self.assertEqual(old_username,
                         self.player_record.displayed_name)
        self.assertEqual(new_username,
                         self.duplicate_name_player_record.displayed_name)

    # def test_displayed_name_gets_untagged_after_leave(self):
    #     raise Exception

    def test_displayed_name_gets_unoccupied_if_player_left(self):
        """
        If player with username same as the one provided is already present
        in the session, given username gets mangled.
        """
        old_username = self.player_record.displayed_name
        self.duplicate_name_player_record = Player.objects.create(
            displayed_name=self.player_record.displayed_name
        )

        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        leave_event = Event(
            type=Event.PLAYER_LEFT,
            data=PlayerMessage(player=self.player_record)
        )
        duplicate_name_join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.duplicate_name_player_record)
        )
        self.controller.player_event(join_event)
        self.controller.player_event(leave_event)
        initial_state_event, _ = self.controller.player_event(
            duplicate_name_join_event
        )
        self.duplicate_name_player_record.refresh_from_db()

        player_object = self.controller._get_player(
            self.duplicate_name_player_record
        )

        displayed_name = initial_state_event.data['player']['displayed_name']

        self.assertEqual(initial_state_event.type, Event.SERVER_INITIAL_STATE)
        self.assertEqual(old_username, displayed_name)
        self.assertEqual(old_username, player_object.displayed_name)

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


# TODO: add test for game over condition (should be per mode)


class ControllerStorageTestCase(TestCase):
    storage_class = ControllerStorage
    controller_class = SingleGameController

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

        self.assertTrue(issubclass(controller.__class__, BaseGameController))
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
