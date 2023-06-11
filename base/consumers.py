from __future__ import annotations

import time
import random
import asyncio
import secrets
from datetime import datetime
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.hashers import check_password
from channels.consumer import SyncConsumer
from channels.generic.websocket import AsyncJsonWebsocketConsumer, JsonWebsocketConsumer

from .game_logic import Event, PlayerMessage, SingleGameController, ControllerStorage, GameOverError, \
    PlayerJoinRefusedError, ControllerError
from .models import (
    Player,
    GameSession,
    )
from .helpers import (
    get_regular_words,
    get_yo_words,
    )
from .serializers import (
    PlayerSerializer,
    GameSessionSerializer,
    SessionPlayerResultSerializer,
    )


SESSIONS = dict()
WORDS = get_regular_words()
YO_WORDS = get_yo_words()


class PlayerInputError(Exception):
    pass


class BaseGameConsumer(JsonWebsocketConsumer):
    RESERVED_EVENT_TYPES = (
        None,
        Event.PLAYER_JOINED,
        Event.PLAYER_LEFT,
        Event.TRIGGER_TICK,
    )
    controller_cls = SingleGameController

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
            self.close(418)

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

    def get_query_username(self):
        params = parse_qs(self.scope["query_string"].decode())
        return params.get('username', (None,))[0]

    def get_query_password(self):
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


class SingleGameConsumer(BaseGameConsumer):
    MODE = "single"
    pass


class EndlessGameConsumer(BaseGameConsumer):
    MODE = "endless"
    GAME_DURATION = 30

    async def process_word(self, word):
        correct_word = self.words.pop(0)
        if word == correct_word: # Lowercase conversion ???
            self.player["score"] += len(word) * 2
            self.total_wordlength += len(word)
            self.player["speed"] = self.total_wordlength / \
                    (time.time() - self.session["game_starts"])
            self.player["time_left"] += len(word)
            if self.player["time_left"] >= self.GAME_DURATION:
                self.player["time_left"] = self.GAME_DURATION
            self.player["correct_words"] += 1
        else:
            self.player["score"] -= round(len(word)/2)
            self.player["incorrect_words"] += 1

        if not self.session["words"]:
            self.session["words"] = self.generate_words()

        await self.channel_layer.group_send(
            self.session_id,
            {
                "type": "session.new.word",
                "word": self.session["words"].pop(),
            },
            )

        await self.channel_layer.group_send(
            self.session_id,
            {
                "type": "session.players.update",
                "action": "tick",
            },
            )

    async def session_all_players_ready(self, event):
        if self.session["player_count"] > 1:
            await self.send_json({
                "event": "get_ready",
                "data": event["game_starts"] - time.time(),
                })
            await asyncio.sleep(event["game_starts"] - time.time())
        self.player["time_left"] = self.GAME_DURATION
        self.last_tick = time.time()
        await self.send_json({
            "event": "game_begins",
            "data": self.player["time_left"]
            })

    async def session_players_update(self, event):
        msg = {
            "event": event["action"],
            "data": {
                "players": list(self.session["players"].values()),
                },
            }

        if event["action"] == "tick":
            await self.decrease_time_left()
            msg["data"]["time_left"] = self.player["time_left"]
            msg["data"]["score"] = self.player["score"]
            msg["data"]["speed"] = self.player["speed"]
            msg["data"]["time_speed"] = self.session["time_speed"]
        else:
            msg["data"]["username"] = event["username"]

        await self.send_json(msg)

    async def session_new_word(self, event):
        await self.decrease_time_left()
        self.words.append(event["word"])
        await self.send_json({
            "event": "new_word",
            "data": {
                "word": event["word"],
                "time_left": self.player["time_left"],
                },
            })

    def init_player(self):
        player = {
            "username": self.username,
            "speed": 0.0,
            "score": 0,
            "ready": False,
            "voted": False,
            "time_left": 0.0,
            "out": False,
            "anonymous": True if self.scope.get("user", AnonymousUser) \
                         is AnonymousUser else False,
            "correct_words": 0,
            "incorrect_words": 0,
            "mistake_ratio": 0.0,
            }
        return player

    async def decrease_time_left(self):
        self.session["time_speed"] = \
                (time.time() - self.session["game_starts"]) / 20 + 1
        self.player["time_left"] -= \
                (time.time() - self.last_tick)*self.session["time_speed"]
        self.last_tick = time.time()
        if self.player["time_left"] <= 0:
            self.player["time_left"] = 0
            if not self.player["out"]:
                self.player["out"] = True
                self.session["out_count"] += 1
                await self.channel_layer.group_send(
                    self.session_id,
                    {
                        "type": "session.players.update",
                        "action": "player_out",
                        "username": self.username,
                    },
                    )

    def game_over(self):
        return self.session["out_count"] and \
               ((self.session["out_count"] == self.session["player_count"]) or \
                (self.session["out_count"] == self.session["player_count"]-1))

    def winners(self):
        if self.session["player_count"] != 1:
            return [i for i in self.session["players"].values() if not i["out"]]
        return list(self.session["players"].values())


class TugOfWarGameConsumer(BaseGameConsumer):
    MODE = "tugofwar"
    TEAM_RED = "red"
    TEAM_BLUE = "blue"

    def init_player(self):
        player = {
            "username": self.username,
            "speed": 0.0,
            "score": 0,
            "ready": False,
            "voted": False,
            "team": None,
            "anonymous": True if self.scope.get("user", AnonymousUser) \
                         is AnonymousUser else False,
            "correct_words": 0,
            "incorrect_words": 0,
            "mistake_ratio": 0.0,
            }
        return player

    def init_team(self, name):
        team = {
            "players" : dict(),
            "score": 0,
            "speed": 0.0,
            "avg_speed": 0.0,
            "name": name,
            "tickets": 50,
            }
        return team

    def init_teams(self):
        teams = {
            self.TEAM_RED: self.init_team(self.TEAM_RED),
            self.TEAM_BLUE: self.init_team(self.TEAM_BLUE),
            }
        return teams

    def add_session_player(self):
        self.player = self.init_player()
        self.session["players"][self.username] = self.player
        if not self.session["teams"]:
            self.session["teams"] = self.init_teams()

        if len(self.session["teams"][self.TEAM_RED]["players"]) > \
            len(self.session["teams"][self.TEAM_BLUE]["players"]):
                team_name = self.TEAM_BLUE
                opposite_team_name = self.TEAM_RED
        elif len(self.session["teams"][self.TEAM_RED]["players"]) < \
            len(self.session["teams"][self.TEAM_BLUE]["players"]):
                team_name = self.TEAM_RED
                opposite_team_name = self.TEAM_BLUE
        else:
                team_name = random.choice(list(self.session["teams"].keys()))
                opposite_team_name = \
                        (self.session["teams"].keys() - {team_name,}).pop()

        self.team = self.session["teams"][team_name]
        self.opposite_team = self.session["teams"][opposite_team_name]
        self.team["players"][self.username] = self.player
        self.player["team"] = team_name

        return self.player

    async def switch_team(self, msg):
        if msg != self.team["name"] and msg in self.session["teams"]:
            self.team["players"].pop(self.username)
            self.opposite_team = self.team
            self.team = self.session["teams"][msg]
            self.team["players"][self.username] = self.player
            self.player["team"] = msg
            await self.channel_layer.group_send(
                self.session_id,
                {
                    "type": "session.players.update",
                    "action": "team_switch",
                    "new_team": self.team["name"],
                    "username": self.username,
                },
                )

    async def process_word(self, word):
        correct_word = self.words.pop(0)
        if word == correct_word: # Lowercase conversion ???
            self.player["score"] += len(correct_word)
            self.total_wordlength += len(correct_word)
            self.player["speed"] = self.total_wordlength / \
                    (time.time() - self.session["game_starts"])
            self.team["score"] += len(correct_word) * 2
            self.team["speed"] = sum(
                i["speed"] for i in self.team["players"].values()
                )
            self.team["avg_speed"] = self.team["speed"] / \
                len(self.team["players"])
            self.team["tickets"] += len(correct_word)
            self.opposite_team["tickets"] -= len(correct_word)
            self.player["correct_words"] += 1
        else:
            self.player["score"] -= len(correct_word)
            self.team["tickets"] -= len(correct_word)
            self.opposite_team["tickets"] += len(correct_word)
            self.player["incorrect_words"] += 1

        if not self.session["words"]:
            self.session["words"] = self.generate_words()

        if self.team["tickets"] <= 0:
            self.session["game_over"] = True
            self.team["tickets"] = 0
            self.opposite_team["tickets"] = 100
            self.session["winner"] = self.opposite_team
        elif self.opposite_team["tickets"] <= 0:
            self.session["game_over"] = True
            self.opposite_team["tickets"] = 0
            self.team["tickets"] = 100
            self.session["winner"] = self.team

        await self.channel_layer.group_send(
            self.session_id,
            {
                "type": "session.new.word",
                "word": self.session["words"].pop(),
            },
            )

    async def session_players_update(self, event):
        msg = {
            "event": event["action"],
            "data": {
                "players": list(self.session["players"].values()),
                },
            }

        if event["action"] == "tick":
            msg["data"]["teams"] = self.session["teams"]
            msg["data"]["score"] = self.team["score"]
        else:
            msg["data"]["username"] = event["username"]

        if event["action"] == "team_switch":
            msg["data"]["new_team"] = event["new_team"]

        await self.send_json(msg)

    def recalc_tickets(self):
        pass
#       incr = (self.session["teams"][self.TEAM_RED]["score"] - \
#               self.session["teams"][self.TEAM_BLUE]["score"])*0.1
#       incr = (1 + abs(incr)) * abs(incr) / incr / 4 if incr else incr

#       self.session["teams"][self.TEAM_RED]["tickets"] += incr
#       self.session["teams"][self.TEAM_BLUE]["tickets"] -= incr

#       if self.session["teams"][self.TEAM_RED]["tickets"] <= 0:
#           self.session["game_over"] = True
#           self.session["teams"][self.TEAM_RED]["tickets"] = 0
#           self.session["teams"][self.TEAM_BLUE]["tickets"] = 100
#           self.session["winner"] = self.session["teams"][self.TEAM_BLUE]

#       elif self.session["teams"][self.TEAM_BLUE]["tickets"] <= 0:
#           self.session["game_over"] = True
#           self.session["teams"][self.TEAM_BLUE]["tickets"] = 0
#           self.session["teams"][self.TEAM_RED]["tickets"] = 100
#           self.session["winner"] = self.session["teams"][self.TEAM_RED]

    def game_over(self):
        return self.session["game_over"]

    def winners(self):
        return [i for i in self.session["winner"]["players"].values()]


class IronWallGameConsumer(BaseGameConsumer):
    MODE = "ironwall"
    pass


class GameTickConsumer(SyncConsumer):
    def game_tick(self, message):
        async_to_sync(self.channel_layer.group_send)(
            "session_hosts",
            {
                "type": "session.tick",
            },
            )
