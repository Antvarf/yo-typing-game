from __future__ import annotations

from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from channels.consumer import SyncConsumer
from channels.generic.websocket import JsonWebsocketConsumer

from .game_logic import Event, PlayerMessage, GameController, ControllerStorage, \
    PlayerJoinRefusedError, ControllerError
from .models import (
    Player,
    GameSession,
    )
from .helpers import (
    get_regular_words,
    get_yo_words,
    )


SESSIONS = dict()
WORDS = get_regular_words()
YO_WORDS = get_yo_words()


class PlayerInputError(Exception):
    pass


class GameConsumer(JsonWebsocketConsumer):
    RESERVED_EVENT_TYPES = (
        None,
        Event.PLAYER_JOINED,
        Event.PLAYER_LEFT,
        Event.TRIGGER_TICK,
    )
    controller_cls = GameController
    game_mode = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.controller = None
        self.player = None
        self.session_id = None
        self._storage = ControllerStorage()
        self.usernames = set()

    def connect(self):
        try:
            self.accept()
            self.join_session()
        except (ControllerError,
                PlayerInputError, GameSession.DoesNotExist) as e:
            self.send_error(str(e))
            self.close(3418)

    def receive_json(self, content, **kwargs):
        try:
            self._perform_input_checks(content)
        except PlayerInputError as e:
            self.send_error(str(e))
        else:
            self._controller_notify(content)

    def disconnect(self, exit_code):
        self.leave_session()

    def join_session(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.controller = self._init_controller()
        self.player = self._init_player()
        self._add_self_to_session()
        self._add_self_to_hosts()

    def leave_session(self):
        self._remove_self_from_session()

    def get_query_username(self) -> str | None:
        params = parse_qs(self.scope["query_string"].decode())
        return params.get('username', (None,))[0]

    def get_query_password(self) -> str | None:
        params = parse_qs(self.scope["query_string"].decode())
        return params.get('password', (None,))[0]

    def send_error(self, message: str):
        error_event = Event(
            type=Event.SERVER_ERROR,
            target=Event.TARGET_PLAYER,
            data=message,
        )
        self.notify([error_event])

    def notify(self, events: list[Event]):
        for event in events:
            if event.target is event.TARGET_ALL:
                async_to_sync(self.channel_layer.group_send)(
                    self.session_id,
                    {
                        'type': 'session.server.event',
                        'data': event.to_dict(),
                    },
                )
            elif event.target is event.TARGET_PLAYER:
                self.send_json(event.to_dict())

    def session_server_event(self, event):
        if event['type'] == Event.SERVER_NEW_HOST:
            if event['data'] == self.player.pk:
                self._add_self_to_hosts()
        else:
            self.send_json(event['data'])

    def session_tick(self, event):
        tick_event = Event(type=Event.TRIGGER_TICK,
                           data=PlayerMessage(player=self.player))
        events = self.controller.player_event(tick_event)
        self.notify(events)

    def _perform_input_checks(self, content):
        if type(content) is not dict:
            raise PlayerInputError('invalid message received')

        msg_type = content.get('type', None)
        if msg_type in self.RESERVED_EVENT_TYPES:
            raise PlayerInputError('message type is invalid or not present')

        msg_data = content.get('data', None)
        if msg_data is None:
            raise PlayerInputError('message data is required')

    def _add_self_to_session(self):
        events = self._controller_join()
        if self.controller.host_id is None:
            self._add_self_to_hosts()
        async_to_sync(self.channel_layer.group_add)(
            self.session_id,
            self.channel_name,
        )
        self.notify(events)

    def _remove_self_from_session(self):
        if self.controller.host_id == self.player.pk:
            self._remove_self_from_hosts()
        events = self._controller_leave()
        self.notify(events)
        async_to_sync(self.channel_layer.group_discard)(
            self.session_id,
            self.channel_name,
        )

    def _add_self_to_hosts(self):
        self.controller.set_host(self.player)
        async_to_sync(self.channel_layer.group_add)(
            settings.HOSTS_LAYER_NAME,
            self.channel_name,
        )

    def _remove_self_from_hosts(self):
        # controller selects the new host on its own
        async_to_sync(self.channel_layer.group_discard)(
            settings.HOSTS_LAYER_NAME,
            self.channel_name,
        )

    def _init_player(self) -> Player:
        user = self.scope['user']
        if user is AnonymousUser:
            username = self.get_query_username()
            if username is None:
                raise PlayerJoinRefusedError(
                    'either `username` or `jwt` are required as query params'
                )
            player = Player.objects.create(displayed_name=username)
        else:
            player = user.player
        return player

    def _init_controller(self):
        controller = self._storage.get_game_controller(
            controller_cls=self.controller_cls,
            session_id=self.session_id,
        )
        return controller

    def _controller_join(self) -> list[Event]:
        player_joined_event = Event(
            type=Event.PLAYER_JOINED,
            data=PlayerMessage(
                player=self.player,
                payload={'password': self.get_query_password()},
            )
        )
        events = self.controller.player_event(player_joined_event)
        return events

    def _controller_leave(self) -> list[Event]:
        player_left_event = Event(
            type=Event.PLAYER_LEFT,
            data=PlayerMessage(
                player=self.player,
            )
        )
        events = self.controller.player_event(player_left_event)
        return events

    def _controller_notify(self, content: dict):
        event = Event(
            type=content['type'],
            data=PlayerMessage(
                player=self.player,
                payload=content['data'],
            ),
        )
        try:
            events = self.controller.player_event(event)
            self.notify(events)
        except ControllerError as e:
            self.send_error(str(e))


class GameTickConsumer(SyncConsumer):
    def game_tick(self, message):
        async_to_sync(self.channel_layer.group_send)(
            settings.HOSTS_LAYER_NAME,
            {
                "type": "session.tick",
            },
        )
