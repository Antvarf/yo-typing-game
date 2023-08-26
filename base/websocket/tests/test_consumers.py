import time
import urllib.parse

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.consumer import AsyncConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from channels.testing import WebsocketCommunicator

from E.routing import application
from base.websocket.consumers import GameConsumer
from base.websocket.game_logic.events import Event
from base.websocket.game_logic.helpers import get_tokens_for_user
from base.models import GameSession

User = get_user_model()


# FIXME: hehe another dirty hack for lack of a better solution in community
AsyncConsumer.channel_layer_alias = settings.TEST_LAYER_NAME


class GameConsumerTestCase(TestCase):
    """
    This class contains tests specific to single game mode
    (+ all common tests, for now)

    This class contains tests for logic common for all consumers:
      * User identification
      * Session controller creation
      * Common message interactions and structure

    FIXME: find a better class to inherit from because tests get stuck :^)
    """
    consumer_cls = GameConsumer

    def setUp(self):
        self.session_record = GameSession.objects.create()
        self.other_session_record = GameSession.objects.create()
        self.application = application

    async def get_communicator(self, session_id: str = None, **kwargs):
        params = urllib.parse.urlencode(kwargs)
        if session_id is None:
            session_id = self.session_record.session_id
        path = f'ws/play/{session_id}/?{params}'

        communicator = WebsocketCommunicator(
            self.application,
            path,
        )
        return communicator

    # FIXME: this is hell on earth of a test to debug
    # async def test_username_query_param(self):
    #     """
    #     If username is in query parameters, create Player with this name
    #     """
    #     username = 'test_user_1'
    #     communicator = await self.get_communicator(username=username)
    #     is_connected, subprotocol = await communicator.connect()
    #     player = await database_sync_to_async(Player.objects.get)(
    #         displayed_name=username,
    #     )
    #     await communicator.disconnect()
    #
    #     self.assertTrue(is_connected)
    #     self.assertEqual(player.displayed_name, username)

    async def test_no_username_or_jwt_returns_error(self):
        """
        If player with username same as the one provided is present in database
        but is not in the session, given username remains unchanged.
        """
        communicator = await self.get_communicator()

        is_connected, subprotocol = await communicator.connect()
        response = await communicator.receive_json_from()

        self.assertTrue(is_connected)
        self.assertEqual(response['type'], Event.SERVER_ERROR)
        self.assertEqual(
            response['data'],
            'either `username` or `jwt` are required as query params',
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
        communicator1 = await self.get_communicator(username=username1)
        communicator2 = await self.get_communicator(username=username2)
        foreign_communicator = await self.get_communicator(
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

    async def test_receive_json(self):
        """
        All events except filtered are passed as Event to .player_event()
        --
        TODO: i will mock test it someday
        """
        username1 = 'test_user_1'
        communicator1 = await self.get_communicator(username=username1)

        await communicator1.connect()
        for i in range(2):
            await communicator1.receive_json_from()
        await communicator1.send_json_to({
            'type': Event.PLAYER_READY_STATE,
            'data': True,
        })
        update_message = await communicator1.receive_json_from()

        self.assertEqual(update_message['type'], Event.SERVER_PLAYERS_UPDATE)

        await communicator1.disconnect()

    async def test_receive_reserved_message_type(self):
        """Messages with reserved type should be filtered out"""
        username1 = 'test_user_1'
        communicator1 = await self.get_communicator(username=username1)

        await communicator1.connect()
        for i in range(2):
            await communicator1.receive_json_from()
        await communicator1.send_json_to({
            'type': Event.PLAYER_JOINED,
            'data': None,
        })
        update_message = await communicator1.receive_json_from()

        self.assertEqual(update_message['type'], Event.SERVER_ERROR)
        self.assertEqual(update_message['data'],
                         'message type is invalid or not present')
        self.assertTrue(await communicator1.receive_nothing())

        await communicator1.disconnect()

    async def test_tick(self):
        """Only host player sends ticks"""
        username1 = 'test_user_1'
        username2 = 'test_user_2'
        communicator1 = await self.get_communicator(username=username1)
        communicator2 = await self.get_communicator(username=username2)
        channel_layer = get_channel_layer(settings.TEST_LAYER_NAME)

        await communicator1.connect()
        await communicator2.connect()
        for i in range(3):
            await communicator1.receive_json_from()

        await channel_layer.group_send(settings.HOSTS_GROUP_NAME, {
                'type': 'session.tick',
            }, )
        self.assertTrue(await communicator1.receive_nothing())

        await communicator1.send_json_to({
            'type': Event.PLAYER_READY_STATE,
            'data': True,
        })
        await communicator2.send_json_to({
            'type': Event.PLAYER_READY_STATE,
            'data': True,
        })

        for i in range(3):
            await communicator1.receive_json_from()

        self.assertTrue(await communicator1.receive_nothing())

        time.sleep(3)

        await channel_layer.group_send(settings.HOSTS_GROUP_NAME, {
                'type': 'session.tick',
            }, )
        await communicator1.receive_json_from()
        update_message = await communicator1.receive_json_from()

        self.assertEqual(update_message['type'], Event.SERVER_PLAYERS_UPDATE)
        self.assertTrue(await communicator1.receive_nothing())

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_join_password_required(self):
        """If password not given when asked for.. well...."""
        username1 = 'test_user_1'
        communicator1 = await self.get_communicator(username=username1)

        self.session_record.is_private = True
        self.session_record.set_password('test_password')
        await database_sync_to_async(self.session_record.save)()

        await communicator1.connect()
        error_message = await communicator1.receive_json_from()

        self.assertEqual(error_message['type'], Event.SERVER_ERROR)

        await communicator1.disconnect()

    async def test_join_with_wrong_password(self):
        """If password doesn't match it's sad"""
        username1 = 'test_user_1'
        communicator1 = await self.get_communicator(username=username1,
                                                    password='wrong_password')

        self.session_record.is_private = True
        self.session_record.set_password('test_password')
        await database_sync_to_async(self.session_record.save)()

        await communicator1.connect()
        error_message = await communicator1.receive_json_from()

        self.assertEqual(error_message['type'], Event.SERVER_ERROR)

        await communicator1.disconnect()

    async def test_join_with_password_good(self):
        """If password fits we rolllllll"""
        username1 = 'test_user_1'
        communicator1 = await self.get_communicator(username=username1,
                                                    password='test_password')

        self.session_record.is_private = True
        self.session_record.set_password('test_password')
        await database_sync_to_async(self.session_record.save)()

        await communicator1.connect()
        message = await communicator1.receive_json_from()

        self.assertEqual(message['type'], Event.SERVER_INITIAL_STATE)  # yay

        await communicator1.disconnect()

    async def test_authenticated_join(self):
        user = await database_sync_to_async(User.objects.create_user)(
            username='test_user_1',
            password='something good',
        )
        jwt_pair = await database_sync_to_async(get_tokens_for_user)(user)

        communicator1 = await self.get_communicator(jwt=jwt_pair['access'])

        await communicator1.connect()
        message = await communicator1.receive_json_from()

        self.assertEqual(message['type'], Event.SERVER_INITIAL_STATE)  # yay
        self.assertEqual(
            message['data']['player']['displayedName'],
            user.username,
        )

        await communicator1.disconnect()

    async def test_authenticated_join_overrides_username(self):
        user = await database_sync_to_async(User.objects.create_user)(
            username='test_user_1',
            password='something good',
        )
        jwt_pair = await database_sync_to_async(get_tokens_for_user)(user)

        communicator1 = await self.get_communicator(jwt=jwt_pair['access'],
                                                    username='test_user_2')

        await communicator1.connect()
        message = await communicator1.receive_json_from()

        self.assertEqual(message['type'], Event.SERVER_INITIAL_STATE)  # yay
        self.assertEqual(
            message['data']['player']['displayedName'],
            user.username,
        )

        await communicator1.disconnect()

    async def test_invalid_jwt_does_not_override_username(self):
        invalid_token = 'oh boy this is not in jwt format at all'

        communicator1 = await self.get_communicator(jwt=invalid_token,
                                                    username='test_user_2')

        await communicator1.connect()
        message = await communicator1.receive_json_from()

        self.assertEqual(message['type'], Event.SERVER_INITIAL_STATE)  # yay
        self.assertEqual(
            message['data']['player']['displayedName'],
            'test_user_2'
        )

        await communicator1.disconnect()
