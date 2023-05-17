from django.db import transaction
from django.test import TestCase

from base.game_logic import Event, PlayerMessage, InvalidGameStateException, ControllerExistsException, \
    SingleGameController
from base.models import GameSession, Player, GameModes


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
        * add basic tests for the following messages:
            - 'game_over'
            - 'new_game'
            - 'start_game'
        * make this test case inheritable so that it applies to every game mode
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

    def test_no_multiple_controllers_for_session(self):
        """Only a single controller instance can exist per session"""
        with self.assertRaises(ControllerExistsException):
            controller = self.controller_cls(
                session_id=self.session_record.session_id,
            )

    def test_session_does_not_exist(self):
        """Exception is raised if no session with given session_id exists"""
        with self.assertRaises(GameSession.DoesNotExist):
            with transaction.atomic():
                self.controller_cls(session_id=self.session_record.session_id)
                # TODO: pass session_id that does not exist

    def test_session_cannot_be_started_or_finished(self):
        """Controller can only be assigned to session at preparation stage"""
        self.session_record.start_game()
        with self.assertRaises(InvalidGameStateException):
            self.controller_cls(session_id=self.session_record.session_id)

        self.session_record.save_results(list())
        with self.assertRaises(InvalidGameStateException):
            self.controller_cls(session_id=self.session_record.session_id)

    def test_player_joined_event(self):
        """
        Player can join if the session is not yet started.
        player_joined is broadcasted on success,
        """
        event = Event(
            # we know: - session_id
            #          - username / auth_token -> derive Player object from that
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        players_before = self.session_record.players_now
        server_events = self.controller.player_event(event)
        self.session_record.refresh_from_db()

        initial_state_event = server_events[0]
        player_joined_event = server_events[1]
        player_object = initial_state_event.data['player']

        self.assertEqual(player_object['displayed_name'],
                         self.player_record.displayed_name)
        self.assertIs(type(player_object['local_id']), int)
        self.assertEqual(player_object['score'], 0)
        self.assertEqual(player_object['speed'], 0)

        self.assertEqual(initial_state_event.type, Event.INITIAL_STATE)
        self.assertEqual(initial_state_event.target, Event.TARGET_PLAYER)
        self.assertIs(type(initial_state_event.data['words']), list)
        self.assertTrue(all(
            type(w) == str
            for w in initial_state_event.data['words']
        ))
        # TODO: add check that for two players words are the same
        self.assertIn('players', initial_state_event.data)

        self.assertEqual(player_joined_event.target, Event.TARGET_ALL)
        self.assertEqual(player_joined_event.type, Event.SERVER_PLAYER_JOINED)
        self.assertIn('players', player_joined_event.data)

        self.assertEqual(self.session_record.players_now, players_before + 1)

    def test_player_cannot_join_started_session(self):
        """
        Player can't join if the session is started.
        close_connection is expected for this case.
        """
        event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        players_before = self.session_record.players_now
        self.controller._start_game()
        server_events = self.controller.player_event(event)
        self.session_record.refresh_from_db()

        # TODO: come up with error message format, insert error message for
        #       client first
        self.assertEqual(server_events[0].target, Event.TARGET_PLAYER)
        self.assertEqual(server_events[0].type, Event.SERVER_CLOSE_CONNECTION)
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
        server_events = self.controller.player_event(event)
        self.session_record.refresh_from_db()

        # TODO: refactor when error message format is defined
        self.assertEqual(server_events[0].target, Event.TARGET_PLAYER)
        self.assertEqual(server_events[0].type, Event.SERVER_CLOSE_CONNECTION)
        self.assertEqual(self.session_record.players_now, players_before)

    def test_player_joined_twice(self):
        """
        Player joining twice doesn't yield anything.
        """
        event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record),
        )
        players_before = self.session_record.players_now
        self.controller.player_event(event)
        server_events = self.controller.player_event(event)
        self.session_record.refresh_from_db()

        self.assertEqual(len(server_events), 0)
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

        player_object = self.controller._get_player(self.player_record)

        self.assertEqual(player_object['displayed_name'],
                         self.player_record.displayed_name)
        self.assertIs(type(player_object['local_id']), int)
        self.assertEqual(player_object['score'], 0)
        self.assertEqual(player_object['speed'], 0)

        self.assertEqual(server_events[0].target, Event.TARGET_ALL)
        self.assertEqual(server_events[0].type, Event.SERVER_PLAYER_LEFT)
        self.assertIn('players', server_events[0].data)
        self.assertEqual(self.session_record.players_now, players_before)

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
            type=Event.READY_STATE,
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
        self.assertEqual(server_events[0].type, Event.SERVER_PLAYER_LEFT)
        self.assertEqual(server_events[1].target, Event.TARGET_ALL)
        self.assertEqual(server_events[1].type, Event.SERVER_GAME_BEGINS)
        self.assertEqual(self.session_record.players_now, players_before + 1)
        self.assertIsNotNone(self.session_record.started_at)

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
            data=PlayerMessage(player=self.other_player_record)
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
        self.assertEqual(server_events[0].type, Event.SERVER_PLAYER_LEFT)
        self.assertEqual(server_events[1].target, Event.TARGET_ALL)
        self.assertEqual(server_events[1].type, Event.SERVER_NEW_SESSION)
        self.assertEqual(self.session_record.players_now, players_before + 1)
        self.assertIsNotNone(self.session_record.finished_at)

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
        """
        join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        ready_event = Event(
            type=Event.READY_STATE,
            data=PlayerMessage(player=self.player_record, payload=True)
        )
        self.controller.player_event(join_event)
        server_events = self.controller.player_event(ready_event)
        self.session_record.refresh_from_db()

        players_update_event, game_begins_event = server_events
        player_object = self.controller._get_player(self.player_record)

        self.assertEqual(player_object['displayed_name'],
                         self.player_record.displayed_name)
        self.assertIs(type(player_object['local_id']), int)
        self.assertEqual(player_object['score'], 0)
        self.assertEqual(player_object['speed'], 0)
        self.assertEqual(player_object['ready'], True)

        self.assertEqual(players_update_event.target, Event.TARGET_ALL)
        self.assertEqual(players_update_event.type, Event.SERVER_PLAYERS_UPDATE)
        self.assertIn('players', players_update_event.data)
        self.assertEqual(game_begins_event.target, Event.TARGET_ALL)
        self.assertEqual(game_begins_event.type, Event.SERVER_GAME_BEGINS)
        self.assertIsNotNone(self.session_record.started_at)

    def test_player_ready_twice_yields_nothing(self):
        p1_join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.player_record)
        )
        p2_join_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(player=self.other_player_record)
        )
        p1_ready_event = Event(
            type=Event.READY_STATE,
            data=PlayerMessage(player=self.player_record, payload=True)
        )
        players_before = self.session_record.players_now
        self.controller.player_event(p1_join_event)
        self.controller.player_event(p2_join_event)
        server_events1 = self.controller.player_event(p1_ready_event)
        server_events2 = self.controller.player_event(p1_ready_event)
        self.session_record.refresh_from_db()

        self.assertEqual(len(server_events1), 1)
        self.assertEqual(server_events1[0].target, Event.TARGET_ALL)
        self.assertEqual(server_events1[0].type, Event.SERVER_PLAYERS_UPDATE)

        self.assertEqual(len(server_events2), 0)
        self.assertEqual(self.session_record.players_now, players_before + 2)
        self.assertIsNone(self.session_record.started_at)

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
            type=Event.READY_STATE,
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
        # TODO
        pass

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
        self.controller.player_event(join_event)
        self.controller._start_game()
        server_events = self.controller.player_event(word_event)

        # TODO: test for stat changes
        self.assertEqual(server_events[0].type, Event.SERVER_NEW_WORD)
        self.assertEqual(server_events[0].target, Event.TARGET_ALL)
        self.assertIs(type(server_events[0].data), str)

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
        server_events = self.controller.player_event(vote_event)

        self.assertEqual(server_events[0].type, Event.SERVER_VOTES_UPDATE)
        self.assertEqual(server_events[0].target, Event.TARGET_ALL)
        self.assertIs(type(server_events[0].data), dict)
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
        server_events = self.controller.player_event(vote_event)

        self.assertEqual(server_events[0].type, Event.SERVER_MODES_AVAILABLE)
        self.assertEqual(server_events[0].target, Event.TARGET_PLAYER)
        self.assertIs(type(server_events[0].data), list)
        self.assertTrue(all(
            type(w) == str
            for w in server_events[0].data
        ))

    def test_player_cant_vote_twice_for_the_same_mode(self):
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
        server_events_2 = self.controller.player_event(vote_event)

        self.assertEqual(server_events_1, server_events_2) # vote counts are eq

    def test_game_over(self):
        pass
