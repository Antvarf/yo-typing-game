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
    """
    consumer_cls = SingleGameConsumer

    def setUp(self):
        print('Heyo')
        self.session_record = GameSession.objects.create()
        self.get_player = database_sync_to_async(Player.objects.get)
        self.application = self._wrapApplication(self.consumer_cls.as_asgi())

    @staticmethod
    @database_sync_to_async
    def count_players(*args, **kwargs):
        return Player.objects.filter(*args, **kwargs).count()

    @staticmethod
    def _wrapApplication(app):
        wrapped = URLRouter([
            path('ws/play/single/<str:session_id>/', app),
        ])
        return wrapped

    def get_communicator(self, path: str):
        communicator = WebsocketCommunicator(
            self.application,
            path,
        )
        return communicator

    async def test_username_query_param(self):
        """
        If username is in query parameters, create Player with this name
        """
        print('test_username_query_param')
        username = 'test_user_1'
        uuid = self.session_record.session_id
        print(uuid)
        path = f'ws/play/single/{uuid}/?username={username}'
        print(path)
        communicator = self.get_communicator(path)
        is_connected, subprotocol = await communicator.connect(timeout=1)
        player = await self.get_player(displayed_name=username)
        await communicator.disconnect(timeout=1)

        self.assertTrue(is_connected)
        self.assertEqual(player.displayed_name, username)
        print('OK')

    async def test_username_changes_if_already_occupied_in_session(self):
        """
        If player with username same as the one provided is already present
        in the session, given username gets mangled.
        """
        print('test_username_changes_if_already_occupied_in_session')
        username = 'test_user_1'
        uuid = self.session_record.session_id
        print(uuid)
        path = f'ws/play/single/{uuid}/?username={username}'
        print(path)
        communicator = self.get_communicator(path)
        await communicator.connect(timeout=1)

        print('CONNECTING')
        is_connected, subprotocol = await communicator.connect(timeout=1)
        print('OK')
        print('RECEIVING')
        response = await communicator.receive_json_from(timeout=1)
        print('OK')
        player_obj = response['data']['player']
        new_username = player_obj['displayed_name']
        print('GETTING PLAYER')
        player = await self.get_player(id=player_obj['id'])
        print('OK')
        print('DISCONNECTING')
        await communicator.disconnect(timeout=1)
        print('OK')

        self.assertTrue(is_connected)
        self.assertNotEqual(username, new_username)
        self.assertEqual(player.displayed_name, new_username)
        print('OK')

    async def test_username_remains_unchanged_if_duplicate_is_only_in_database(self):
        """
        If player with username same as the one provided is present in database
        but is not in the session, given username remains unchanged.
        """
        print('test_username_remains_unchanged_if_duplicate_is_only_in_database')
        username = 'test_user_1'
        uuid = self.session_record.session_id
        path = f'ws/play/single/{uuid}/?username={username}'
        communicator = self.get_communicator(path)

        is_connected, subprotocol = await communicator.connect(timeout=1)
        response = await communicator.receive_json_from(timeout=1)
        player_obj = response['data']['player']
        new_username = player_obj['displayed_name']
        player = await self.get_player(id=player_obj['id'])
        username_count = await self.count_players(displayed_name=username)
        await communicator.disconnect(timeout=1)

        self.assertTrue(is_connected)
        self.assertEqual(username, new_username)
        self.assertEqual(player.displayed_name, new_username)
        self.assertEqual(username_count, 2)
        print('OK')

    async def test_no_username_or_jwt_returns_error(self):
        """
        If player with username same as the one provided is present in database
        but is not in the session, given username remains unchanged.
        """
        print('test_no_username_or_jwt_returns_error')
        uuid = self.session_record.session_id
        path = f'ws/play/single/{uuid}/'
        print(path)
        communicator = self.get_communicator(path)

        is_connected, subprotocol = await communicator.connect(timeout=1)
        response = await communicator.receive_json_from(timeout=3)

        self.assertTrue(is_connected)
        self.assertEqual(response['type'], Event.SERVER_ERROR)
        self.assertEqual(
            response['data'],
            'either `username` or `jwt` query params should be provided',
        )
        await communicator.disconnect(timeout=1)
        print('OK')
        # communicator.receive_output()
