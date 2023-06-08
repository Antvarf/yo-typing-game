import urllib.parse

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from django.test import TestCase
from channels.testing import WebsocketCommunicator
from django.urls import path

from base.consumers import SingleGameConsumer, BaseGameConsumer
from base.game_logic import Event
from base.models import GameSession, Player


class BaseGameConsumerTestCase(TestCase):
    """
    This class contains tests for logic common for all consumers:
      * User identification
      * Session controller creation
      * Common message interactions and structure
    """
    pass
    # communicator = WebsocketCommunicator(SingleGameConsumer.as_asgi(), path='')

    # User identification logic
    # def test_username_query_param(self):
    #     raise Exception
    #
    # def test_username_changes_if_already_occupied(self):
    #     raise Exception

    # def test_jwt_auth(self):
    #     raise Exception
    #
    # def test_error_on_invalid_jwt(self):
    #     raise Exception
    #
    # def test_username_ignored_if_jwt_is_present(self):
    #     raise Exception


class SingleGameConsumerTestCase(TestCase):
    """
    This class contains tests specific to single game mode
    (+ all common tests, for now)

    FIXME: find a better class to inherit from because tests get stuck :^)
    """
    consumer_cls = SingleGameConsumer

    def setUp(self):
        self.session_record = GameSession.objects.create()
        self.other_session_record = GameSession.objects.create()
        self.application = URLRouter([
            path('ws/play/single/<str:session_id>/',
                 self.consumer_cls.as_asgi()),
        ])

    def get_communicator(self, session_id: str = None, **kwargs):
        params = urllib.parse.urlencode(kwargs)
        if session_id is None:
            session_id = self.session_record.session_id
        path = f'ws/play/single/{session_id}/?{params}'

        communicator = WebsocketCommunicator(
            self.application,
            path,
        )
        return communicator

    async def test_username_query_param(self):
        """
        If username is in query parameters, create Player with this name
        """
        username = 'test_user_1'
        communicator = self.get_communicator(username=username)
        is_connected, subprotocol = await communicator.connect()
        player = await database_sync_to_async(Player.objects.get)(
            displayed_name=username,
        )
        await communicator.disconnect()

        self.assertTrue(is_connected)
        self.assertEqual(player.displayed_name, username)

    async def test_no_username_or_jwt_returns_error(self):
        """
        If player with username same as the one provided is present in database
        but is not in the session, given username remains unchanged.
        """
        communicator = self.get_communicator()

        is_connected, subprotocol = await communicator.connect()
        response = await communicator.receive_json_from()

        self.assertTrue(is_connected)
        self.assertEqual(response['type'], Event.SERVER_ERROR)
        self.assertEqual(
            response['data'],
            'either `username` or `jwt` query params should be provided',
        )
        # TODO: test we got disconnected
        # communicator.receive_output()

    async def test_channel_layer_setup(self):
        """
        Tests that:
            - Individual messages are received only by consumer client
            - Broadcast messages are received by every other client in session
            - Broadcast messages are not received by clients outside of session

        + That for events with TARGET_PLAYER payload is sent individually
        + That for events with TARGET_ALL payload is broadcasted to everyone
        ---
        FIXME: should we mock the send_events() func and isolate its tests?
        """
        username1 = 'test_user_1'
        username2 = 'test_user_2'
        communicator1 = self.get_communicator(username=username1)
        communicator2 = self.get_communicator(username=username2)
        foreign_communicator = self.get_communicator(
            session_id=self.other_session_record.session_id,
            username=username1
        )

        await communicator1.connect()
        for i in range(2):
            await communicator1.receive_json_from()
        await communicator2.connect()
        update_message = await communicator1.receive_json_from()

        self.assertEqual(update_message['type'], Event.SERVER_PLAYERS_UPDATE)
        self.assertTrue(await communicator1.receive_nothing())

        await foreign_communicator.connect()
        self.assertTrue(await communicator1.receive_nothing())

        await communicator1.disconnect()
        await communicator2.disconnect()
        await foreign_communicator.disconnect()
