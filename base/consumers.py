from __future__ import annotations

import time
import random
import asyncio
import secrets
from datetime import datetime
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.hashers import check_password
from channels.consumer import SyncConsumer
from channels.generic.websocket import AsyncJsonWebsocketConsumer, JsonWebsocketConsumer

from .game_logic import Event, PlayerMessage, SingleGameController, ControllerStorage, GameOverError
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


class BaseGameConsumer(JsonWebsocketConsumer):
    controller_cls = SingleGameController

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.controller = None
        self.player = None
        self.session_id = None
        self._storage = ControllerStorage()
        self.usernames = set()

    def connect(self):
        events = []
        errors = []
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.controller = self._init_controller()
        if self.controller is None:
            error_message = self._get_error_event(
                'This session can\'t be joined',
            )
            errors.append(error_message)
        self.player = self._init_player()
        if self.player is None:
            error_message = self._get_error_event(
                'either `username` or `jwt` '
                'query params should be provided'
            )
            errors.append(error_message)
        else:
            player_joined_event = Event(
                type=Event.PLAYER_JOINED,
                data=PlayerMessage(
                    player=self.player,
                )
            )
            events.extend(self.controller.player_event(player_joined_event))
        self.accept()
        if errors:
            self.send_events(errors)
            self.close(418)
        else:
            async_to_sync(self.channel_layer.group_add)(
                self.session_id,
                self.channel_name,
            )
            self.send_events(events)

    def _init_player(self) -> Player | None:
        username, jwt = self.get_query_username(), self.get_query_jwt()
        if username:
            player = Player.objects.create(displayed_name=username)
            return player

    def _init_controller(self):
        try:
            controller = self._storage.get_game_controller(
                controller_cls=self.controller_cls,
                session_id=self.session_id,
            )
        except (GameOverError, GameSession.DoesNotExist):
            pass
        else:
            return controller

    def _get_error_event(self, message: str) -> Event:
        error_message = Event(
            type=Event.SERVER_ERROR,
            target=Event.TARGET_PLAYER,
            data=message,
        )
        return error_message

    def get_query_username(self):
        params = parse_qs(self.scope["query_string"].decode())
        return params.get('username', (None,))[0]

    def get_query_jwt(self):
        return

    def send_events(self, events: list[Event]):
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
        self.send_json(event['data'])

    def disconnect(self, exit_code):
        player_left_event = Event(
            type=Event.PLAYER_LEFT,
            data=PlayerMessage(
                player=self.player,
            )
        )
        if self.player is not None:
            events = self.controller.player_event(player_left_event)
            self.send_events(events)
        if self.controller is not None:
            self._storage.remove_game_controller(self.session_id)

    def can_connect(self):
        if not hasattr(self, "session"):
            return True
        if self.game_started():
            return False
        #if self.session["players_max"] <= self.session["player_count"]:
        #    return False

    async def can_join(self):
        pass_correct = self.check_pass()
        await self.send_json({
            "event": "pass_correct",
            "data": pass_correct,
            })
        return pass_correct

    def check_pass(self):
        if not self.session["password"]:
            return True

        params = parse_qs(self.scope["query_string"].decode())
        try:
            result = check_password(
                params["password"][0],
                self.session["password"],
                )
            print("Check passed: {}".format(result))
            return result
        except:
            return False

        # if hasattr(self, "session"):
        #     self.session["players"].pop(self.username)
        #
        #     await self.channel_layer.group_send(
        #         self.session_id,
        #         {
        #             "type": "session.players.update",
        #             "action": "player_left",
        #             "username": self.username,
        #         },
        #         )
        #
        #     if self.player["ready"]:
        #         self.session["ready_count"] -= 1
        #     if self.player["voted"]:
        #         self.session["vote_count"] -= 1
        #     if "out" in self.player and self.player["out"]:
        #         self.session["out_count"] -= 1
        #
        #     await self.check_ready_states()
        #     await self.check_vote_states()
        #
        #     await self.channel_layer.group_discard(
        #         self.session_id,
        #         self.channel_name,
        #         )
        #     if self.is_host:
        #         await self.channel_layer.group_discard(
        #             "session_hosts",
        #             self.channel_name,
        #             )
        #
        #         if self.session["players"]:
        #             new_host = random.choice(list(self.session["players"]))
        #             await self.channel_layer.group_send(
        #                 self.session_id,
        #                 {
        #                     "type": "session.new.host",
        #                     "username": new_host,
        #                 },
        #                 )
        #             print("New host: {}".format(new_host))
        #     await self.update_player_count(increase=False)

    async def receive_json(self, content):
        msg_type = content.get("event", None)
        msg_data = content.get("data", None)

        if msg_type == "word" and self.game_started() and \
           not ("out" in self.player and self.player["out"]) and \
           not self.game_over():
            await self.process_word(msg_data)

        elif msg_type == "ready" and not self.game_started():
            if msg_data and not self.player["ready"]:
                self.player["ready"] = True
                self.session["ready_count"] += 1

            elif self.player["ready"] and not msg_data:
                self.player["ready"] = False
                self.session["ready_count"] -= 1

            await self.channel_layer.group_send(
                self.session_id,
                {
                    "type": "session.players.update",
                    "action": "player_ready",
                    "username": self.username,
                },
                )

            await self.check_ready_states()

        elif msg_type == "vote" and self.game_over():
            old_mode = self.player["voted"]
            if msg_data in self.session["votes"]:
                if old_mode:
                    self.session["votes"][old_mode] -= 1
                else:
                    self.session["vote_count"] += 1
                self.session["votes"][msg_data] += 1
                self.player["voted"] = msg_data

            await self.channel_layer.group_send(
                self.session_id,
                {
                    "type": "session.new.vote",
                    "username": self.username,
                },
                )

            await self.check_vote_states()

        elif msg_type == "switch_team" and not self.game_started():
            await self.switch_team(msg_data)

    async def handle_username_collisions(self, username):
        if username in self.session["players"]:
            if self.scope["user"] is AnonymousUser:
                self.username = self.get_unique_mangled(username)
            else:
                victim = self.session["players"][username]
                mangled_username = self.get_unique_mangled(username)
                if not victim["anonymous"]:
                    self.username = mangled_username
                    await self.disconnect(418)
                else:
                    victim["username"] = mangled_username
                    self.session["players"][mangled_username] = victim.copy()
                    self.session["players"].pop(username)
                    await self.channel_layer.group_send(
                        self.session_id,
                        {
                            "type": "session.username.switch",
                            "old_username": username,
                            "new_username": victim["username"],
                        },
                        )
        self.username = username

    async def session_username_switch(self, event):
        self.send_json({
            "event": "username_switch",
            "old_username": event["old_username"],
            "new_username": event["new_username"],
            "players": list(self.session["players"].values()),
            })

    async def switch_team(self, msg):
        pass

    async def check_ready_states(self):
        if self.session["player_count"] == self.session["ready_count"] and \
          not self.game_started():
            await self.start_game()

    async def check_vote_states(self):
        if self.session["vote_count"] == self.session["player_count"] and \
          self.game_over() and "vote_fired" not in self.session:
            self.session["vote_fired"] = True
            await self.start_renew()

    async def start_renew(self):
        best_count = max(count for count in self.session["votes"].values())
        mode = random.choice(
            [mode for mode, count in self.session["votes"].items() \
             if count == best_count]
            )
        new_session_id = await self.register_new_session(mode)
        await self.channel_layer.group_send(
            self.session_id,
            {
                "type": "session.new.session",
                "new_session_id": new_session_id,
                "new_mode": mode,
            },
            )

    @database_sync_to_async
    def update_player_count(self, increase):
        inc = 1 if increase else -1
        self.session["player_count"] += inc
        if self.session["db_record"]:
            sesh = GameSession.objects.get(session_id=self.session_id)
            sesh.players_now = self.session["player_count"]
            if sesh.players_now <= 0:
                sesh.finished = True
            sesh.save()
        if self.session["player_count"] <= 0:
            SESSIONS.pop(self.session_id)

    @database_sync_to_async
    def register_new_session(self, new_mode):
        name = self.session["name"]
        sesh = GameSessionSerializer(
            data={"name": name, "mode": new_mode, "players": 0},
            fields=("name", "mode", "players"),
            context={
                "user": self.scope["user"],
                },
            )
        if sesh.is_valid():
            return sesh.save().session_id



    async def init_session(self):
        """
        """
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        if self.session_id not in SESSIONS:
            SESSIONS[self.session_id] = "is_created"
            SESSIONS[self.session_id] = await self.create_session()
        else:
            while SESSIONS[self.session_id] == "is_created":
                await asyncio.sleep(0.3)
        self.session = SESSIONS[self.session_id]

        if self.scope.get("user", AnonymousUser) is AnonymousUser:
            self.username = self.get_query_username()
            print("Obtained {} as qs".format(self.scope["query_string"]))
            print("Parsed {} as username".format(self.username))
            if not self.username:
                await self.close()
                return "error"
        else:
            self.username = self.scope["user"].username
        await self.handle_username_collisions(self.username)

        self.words = self.session["words"][:]
        self.total_wordlength = 0

        self.add_session_player()
        # add to the database

        await self.channel_layer.group_add(
            self.session_id,
            self.channel_name,
            )

        await self.channel_layer.group_send(
            self.session_id,
            {
                "type": "session.players.update",
                "action": "player_joined",
                "username": self.username,
            },
            )

        await self.send_json({
            "event": "words",
            "data": self.words,
            })


    def add_session_player(self):
        self.player = self.init_player()
        self.session["players"][self.username] = self.player
        return self.player

    @database_sync_to_async
    def create_session(self):
        # session id check against db (do we even want it?)
        session = {
            "players": dict(),
            "teams": dict(),
            "player_count": 0,
            "ready_count": 0,
            "vote_count": 0,
            "out_count": 0,
            "words": self.generate_words(),
            "game_over": False,
            "votes": {
                SingleGameConsumer.MODE: 0,
                EndlessGameConsumer.MODE: 0,
                TugOfWarGameConsumer.MODE: 0,
                IronWallGameConsumer.MODE: 0,
                }
            }
        try:
            sesh = GameSession.objects.get(session_id=self.session_id) \
                    and not GameSession.objects.finished
        except:
            sesh = False

        session["db_record"] = bool(sesh)
        session["name"] = sesh.name if sesh else "JohnDoe"
        session["password"] = sesh.password if sesh else ""
        session["players_max"] = sesh.players_max if sesh else 0

        return session

    async def start_game(self):
        self.session["game_starts"] = time.time()
        if self.session["player_count"] > 1:
            self.session["game_starts"] += self.GAME_START_DELAY

        self.session["game_ends"] = self.session["game_starts"] + \
                self.GAME_DURATION

        self.session["words"] = self.generate_words()

        self.is_host = True
        print("Game begins! {} is host".format(self.player["username"]))
        await self.clean_db_session()
        await self.channel_layer.group_add(
            "session_hosts",
            self.channel_name,
            )

        await self.channel_layer.group_send(
            self.session_id,
            {
                "type": "session.all.players.ready",
                "game_starts": self.session["game_starts"],
            },
            )

    async def session_tick(self, event):
        self.recalc_tickets()
        if self.game_over():
            print(
                "* Game is over! Host: \n\t{}\nplayers:\n\t {}".format(
                    self.username,
                    self.session["players"]
                    )
                )
            if "game_over_notified" not in self.session:
                print("* And I am also firing game_over!")
                winners = self.winners()
                await self.channel_layer.group_send(
                    self.session_id,
                    {
                        "type": "session.game.over",
                        "winners": winners,
                        "players": list(self.session["players"].values()),
                    },
                    )
                if self.session["db_record"]:
                    await self.save_results(winners)
                self.session["game_over_notified"] = True
        else:
            await self.channel_layer.group_send(
                self.session_id,
                {
                    "type": "session.players.update",
                    "action": "tick",
                    "username": "SERVER",
                },
                )

    def recalc_tickets(self):
        pass

    @database_sync_to_async
    def clean_db_session(self):
        if self.session["db_record"]:
            sesh = GameSession.objects.get(session_id=self.session_id)
            sesh.finished = True
            sesh.save()
        self.session["db_record"] = False

    @database_sync_to_async
    def save_results(self):
        players = self.update_session_record(
            self.session["players"].values(),
            winners,
            )

    def update_session_record(self, players, winners):
        """
        Updates session as follows:
          * Marks session obj as finished [+]
          * Updates each non-anon player record with new result [+]
          * Creates sessionPlayerResult records pointing to session obj [+]
          ! SessionPlayerSerializer is responsible for updating player
          ! SessionPlayerResult record is created here
        ----
        TODO: reduce number of db calls!!!
        """
        # Update session
        sesh = GameSession.objects.get(session_id=self.session_id)
        sesh.finished = True
        sesh.started_at = datetime.fromtimestamp(self.session["game_begins"])
        sesh.finished_at = datetime.now()
        sesh.save()
        # ---------
        # Update players
        for player in players:
            if player["anonymous"]:
                player_rec = AnonymousUser
            else:
                player_rec = Player.objects.get(
                    username=player["username"],
                    )
                player["mode"] = self.MODE
                player_ser = PlayerSerializer(
                    player_rec,
                    context=player,
                    data={},
                    fields=tuple(),
                    )
                ihope = player_ser.is_valid()
                player_rec = player_ser.save()
                player.pop("mode")

            # create records
            player_result = {
                "username": player["username"],
                "score": player["score"],
                "speed": player["speed"],
                "mistake_ratio": player["mistake_ratio"],
                "player": player_rec,
                "winner": player in winners,
                "correct_words": player["correct_words"],
                "incorrect_words": player["incorrect_words"],
                "session": sesh,
                },
            if "team" in player:
                player_result["team"] = player["team"]

            result_obs = SessionPlayerResult.objects.create(**player_result)

    def game_started(self):
        session_id = self.scope["url_route"]["kwargs"]["session_id"]
        return session_id in SESSIONS and "game_starts" in SESSIONS[session_id]

    def game_over(self):
        return self.session["game_ends"] <= time.time()

    async def session_all_players_ready(self, event):
        if self.session["player_count"] > 1:
            await self.send_json({
                "event": "get_ready",
                "data": event["game_starts"] - time.time(),
                })
            await asyncio.sleep(event["game_starts"] - time.time())
        await self.send_json({
            "event": "game_begins",
            "data": self.session["game_ends"] - time.time(),
            })

    async def session_players_update(self, event):
        msg = {
            "event": event["action"],
            "data": {
                "players": list(self.session["players"].values()),
                },
            }

        if event["action"] == "tick":
            msg["data"]["time_left"] = self.session["game_ends"] - time.time()
            msg["data"]["score"] = self.player["score"]
            msg["data"]["speed"] = self.player["speed"]
        else:
            msg["data"]["username"] = event["username"]

        await self.send_json(msg)

    async def session_new_vote(self, event):
        await self.send_json({
            "event": "modes",
            "data": {
                "votes": self.session["votes"],
                "players": list(self.session["players"].values()),
                },
            })

    async def session_game_over(self, event):
        await self.send_json({
            "event": "game_over",
            "data": {
                "winners": event["winners"],
                "players": event["players"],
                },
            })

    async def session_new_host(self, event):
        if self.username == event["username"]:
            self.is_host = True
            await self.channel_layer.group_add(
                "session_hosts",
                self.channel_name,
                )
            print("I'm ({}) host now!".format(self.username))

    async def session_new_session(self, event):
        await self.send_json({
            "event": "new_session",
            "data": {
                "new_session_id": event["new_session_id"],
                "new_mode": event["new_mode"],
                },
            })
        await self.disconnect(418)
        await self.close()

    async def session_new_word(self, event):
        self.words.append(event["word"])
        await self.send_json({
            "event": "new_word",
            "data": event["word"],
            })

    async def process_word(self, word):
        correct_word = self.words.pop(0)
        if word == correct_word: # Lowercase conversion ???
            self.player["score"] += len(correct_word) * 2
            self.total_wordlength += len(correct_word)
            self.player["speed"] = self.total_wordlength / \
                    (time.time() - self.session["game_starts"])
            self.player["correct_words"] += 1
        else:
            self.player["score"] -= round(len(correct_word)/2)
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

    def winners(self):
        max_score = max(i["score"] for i in self.session["players"].values())
        return [i for i in self.session["players"].values() \
                if i["score"] == max_score]

    def generate_words(self):
        YO_WORDS_COUNT = 8
        WORDS_COUNT = YO_WORDS_COUNT * 8

        words = random.choices(WORDS, k=WORDS_COUNT) + \
                random.choices(YO_WORDS, k=YO_WORDS_COUNT)
        random.shuffle(words)
        return words

    async def get_anon_handle(self):
        NICKNAMES = {
            "PerryThePlatypus",
            "LinusTorvalds",
            "PositiveThinker",
            "Mr. Pink",
            "HonestPolitician",
            "AllWork&NoPlay",
            "CowardishFish",
            "BeautifulSandwich",
            }

        while self.username is None:
            await asyncio.sleep(0.1)


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
