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
        username = 'test_user_1'
        uuid = self.session_record.session_id
        path = f'ws/play/single/{uuid}/?username={username}'
        communicator = self.get_communicator(path)
        is_connected, subprotocol = await communicator.connect(timeout=1)
        player = await self.get_player(displayed_name=username)
        await communicator.disconnect(timeout=1)

        self.assertTrue(is_connected)
        self.assertEqual(player.displayed_name, username)

    async def test_no_username_or_jwt_returns_error(self):
        """
        If player with username same as the one provided is present in database
        but is not in the session, given username remains unchanged.
        """
        uuid = self.session_record.session_id
        path = f'ws/play/single/{uuid}/'
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
        # communicator.receive_output()

    # Things to test:
    #   * Consumer handles query params correctly
    #       + username
    #       - jwt
    #       - password
    #   * Consumer calls .player_event with player_join message on join
    #   * Consumer is added to channel layer for his session on successful join
    #   * If no session controller was instantiated for this session_id,
    #       - Consumer becomes host
    #       - Consumer instantiates session controller with that session_id
    #       - Race conditions between two consumers are excluded
    #   * Consumer calls .player_event with player_leave message on leave
    #   * Consumer is removed from channel layer after leave
    #   * Consumer calls .player_event with input wrapped in Event
    #       - Consumer sends individually events returned with TARGET_PLAYER
    #       - Consumer broadcasts events returned with TARGET_ALL
    #   * When host, consumer is responsible for delivering ticks to controller
    #       - Consumer is added to HOSTS channel layer
    #       - On each tick consumer calls .player_event with TRIGGER_TICK event
    #   * If host Consumer leaves, it is responsible for selecting new host
    #       AFTER LEAVE MESSAGE:
    #       - Players can be selected from controller.players
    #       - If no players available, deinstantiate session controller
    #   * When last player that leaves is not host, he deinstantiates session
    #       (theoretically impossible but for redundancy)
