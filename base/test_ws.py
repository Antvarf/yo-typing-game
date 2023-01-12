"""
TODO:
  when finished:
    + Session object is not deleted but marked as finished now.
    - Each non-anon player record is updated with new result
    - SessionPlayerResult records pointing to session obj are created
    - if session is finished, player shouldn't be able to connect
    ? TugOfWar special case (time doesn't run out WE FUCK UP TILL WE LOSE YEAAH)
    ^ We could also just cword/bword flood and go without check_game_over
"""
import asyncio
from pprint import pprint

import pytest
from django.urls import (
    reverse,
    path,
    )
from django.contrib.auth.models import (
    User,
    AnonymousUser,
    )
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework.test import APIRequestFactory
from channels.routing import (
    ProtocolTypeRouter,
    ChannelNameRouter,
    URLRouter,
    )

#from E.routing import application
from E.auth import JWTAuthMiddleware
from base.models import Player, GameSession
from base.views import SwaggeredTokenObtainPairView
from base.serializers import GameSessionSerializer
from base import consumers


DEFAULT_PASSWORD = "ilikebirds"
SESSIONS = []
TEST_CASES = [
    {
        "players": {"John": {"authenticated":False}},
        "mode": "endless",
        "prep": {
            "events": [
                {"player": "John", "actions": ["join", "set_ready"]},
                ],
            },
        "game": {
            "events": [
                {
                    "player": "John",
                    "actions": [
                        "cword",
                        "sleep_1",
                        "bword",
                        "check_game_over",
                        ]
                },
                ],
            },
        "renew": {
            "events": [
                {"player": "John", "actions": ["vote_single", "leave"]},
                ],
            },
    },
    {
        "players": {"John": {"authenticated":True}},
        "mode": "single",
        "prep": {
            "events": [
                {"player": "John", "actions": ["join", "set_ready"]},
                ],
            },
        "game": {
            "events": [
                {"player": "John", "actions": ["cword", "sleep_1", "bword"]},
                ],
            },
        "renew": {
            "events": [
                {"player": "John", "actions": ["leave"]},
                ],
            },
    },
    {
        "players": {"John": {"authenticated":False}},
        "mode": "ironwall",
        "prep": {
            "events": [
                {"player": "John", "actions": ["join", "set_ready"]},
                ],
            },
        "game": {
            "events": [
                {
                    "player": "John",
                    "actions": [
                        "cword",
                        "sleep_1",
                        "bword",
                        "check_game_over",
                        ]
                },
                ],
            },
        "renew": {
            "events": [
                {"player": "John", "actions": ["vote_single", "leave"]},
                ],
            },
    },
]


def assertMessageIsWords(msg):
    assert type(msg) is dict
    event = msg.get("event", None)
    assert event == "words"
    data = msg.get("data", None)
    assert data is not None and type(data) is list and \
            all(type(i) is str for i in data)

#def assertMessageIsPlayerJoined(

class SessionPlayer:
    def __init__(self, playerobj, session, url, username=None):
        self.username = playerobj.username or username
        self.playerobj = playerobj
        self.session = session
        self.counts = {
            "player_count": 0,
            "ready_count": 0,
            "voted_count": 0,
            }
        self.url = url
        self.communicator = None
        self.modes = {
            "single": False,
            "ironwall": False,
            "endless": False,
            "tugofwar": False,
            }
        self.last_time_left = 0
        if session["mode"] == "single":
            self.Consumer = consumers.SingleGameConsumer
        elif session["mode"] == "endless":
            self.Consumer = consumers.EndlessGameConsumer
        elif session["mode"] == "tugofwar":
            self.Consumer = consumers.TugOfWarGameConsumer
        elif session["mode"] == "ironwall":
            self.Consumer = consumers.IronWallGameConsumer

    def handle_server_message(self, msg):
        event, data = msg.get("event", None), msg.get("data", None)
        if event == "username_switch":
            if data["old_username"] == self.username:
                self.username = data["new_username"]
            ###########################################
        elif event == "player_ready":
            self.session["ready_count"] = \
                [i["ready"] for i in data["players"]].count(True)
            self.session["player_count"] = len(data["players"])

            if self.session["player_count"] == self.session["ready_count"]:
                self.waiting_for_start = True

        elif event == "get_ready":
            assert self.waiting_for_start and self.session["player_count"] > 1
            self.get_ready_received = True
            #### check timings ####

        elif event == "game_begins":
            assert self.waiting_for_start
            assert self.session["player_count"] == 1 or self.get_ready_received

        elif event == "new_word":
            if self.session["mode"] == "endless":
                data = data["word"]
            assert type(data) is str
            self.words.append(data)

        elif event == "tick":
            assert self.session["state"] == "game"
            self.check_game_over(data)

    async def recv_until_event(self, evt):
        while True:
            msg = await self.communicator.receive_json_from()
            event, data = msg.get("event", None), msg.get("data", None)
            print("Waiting for {}".format(evt))
            print("Received {}".format(msg))
            self.handle_server_message(msg)
            if event == evt:
                return event, data

    async def join(self):
        communicator = WebsocketCommunicator(
            self.session["app"],
            self.url,
            )
        connected, subprotocol = await communicator.connect()
        if self.session["state"] == "game":
            assert not connected
        assert connected

        msg = await communicator.receive_json_from()
        assertMessageIsWords(msg)
        self.words = msg["data"]
 
        msg = await communicator.receive_json_from()
        msg = await communicator.receive_json_from()
        assert type(msg) is dict
        event, data = msg.get("event", None), msg.get("data", None)
        assert event == "player_joined"
        if self.playerobj is AnonymousUser:
            assert data["username"].startswith(self.username)
            if self.username != data["username"]:
                print("My username: {}\nGiven: {}".format(self.username,data["username"]))
                self.username = data["username"]
                assert len(self.username.split("_")) > 1
        else:
            assert self.username == data["username"]

        player = [i for i in data["players"] if i["username"]==self.username][0]
        assert player["speed"] == 0 and \
                player["score"] == 0 and \
                player["ready"] is False and \
                player["voted"] is False and \
                ((self.playerobj is AnonymousUser and \
                 player["anonymous"] is True) or (player["anonymous"] is False))

        return communicator

    async def leave(self):
        print("{} is leaving YAY".format(self.username))
        await self.communicator.disconnect()

    async def ready(self, is_ready):
        await self.communicator.send_json_to({
            "event": "ready",
            "data": is_ready,
            })

        event, data = await self.recv_until_event("player_ready")
        
        assert data["username"] == self.username
        player = self.extract_tick_player(data)
        assert player["ready"] == is_ready

    async def vote(self):
        await self.communicator.send_json_to({
            "event": "vote",
            "data": self.mode,
            })
        event, data = await self.recv_until_event("modes")  # recv all and look
                                                            # for particular msg
    async def word(self, wrd):
        await self.communicator.send_json_to({
            "event": "word",
            "data": wrd,
            })
        event, data = await self.recv_until_event("new_word")
        if event is None or data is None:
            return None
        if self.session["mode"] == "endless":
            data = data["word"]
        print(self.session["mode"])
        assert type(data) is str
        return data

    async def act(self, action):
        if action == "join":
            if self.communicator is None:
                self.communicator = await self.join()
            else:
                raise Exception("What the frick do you think you are doing")

        elif action == "leave":
            if self.communicator is None:
                raise Exception("What the frick do you think you are doing")
            else:
                await self.leave()
                self.communicator = None

        elif action == "set_ready":
            await self.ready(True)

        elif action == "unset_ready":
            await self.ready(False)

        elif action == "set_renew":
            await self.renew(True)

        elif action == "unset_renew":
            await self.renew(False)

        elif action.startswith("vote"):
    #       for mode in self.modes:
    #           self.modes[mode] = mode in action
            self.mode = action.split("_")[1]
            await self.vote()

        elif action == "cword":
            new_word = await self.word(self.words[0])
            if self.session["state"] == "prep":
                assert new_word is None
            else:
                assert new_word is not None
                self.words.append(new_word)
                self.words.pop(0)

        elif action == "bword":
            new_word = await self.word("somethingsurelywrong")
            if self.session["state"] == "prep":
                assert new_word is None
            else:
                assert new_word is not None
                self.words.append(new_word)
                self.words.pop(0)

        elif action.startswith("sleep"):
            duration = float(action.split("_")[1])
            await asyncio.sleep(duration)

        elif action == "check_game_over":
            assert self.session["state"] == "game"
            event, data = await self.recv_until_event("game_over")
            self.check_winners(
                data,
                )

        elif action == "check_new_session":
            assert self.session["state"] == "renew"
            event, data = await self.recv_until_event("new_session")
            session_obj = await get_session(data["new_session_id"])
            #SESSIONS.append(data["new_session_id"])

    def check_game_over(self, tick):
        if self.session["mode"] in ("single", "ironwall"):
            assert tick["time_left"] >= 0
            if self.last_time_left:
                assert tick["time_left"] < self.last_time_left
            self.last_time_left = tick["time_left"]

        elif self.session["mode"] == "tugofwar":
            assert tick["teams"][self.Consumer.TEAM_RED]["tickets"] and \
                tick["teams"][self.Consumer.TEAM_BLUE]["tickets"]

        elif self.session["mode"] == "endless":
            for player in tick["players"]:
                assert player["time_left"] > 0 or player["out"]

    def check_winners(self, data):
        if self.session["mode"] in ("single", "ironwall"):
            max_score = max(i["score"] for i in data["players"])
            winners = [i for i in data["players"] if i["score"] == max_score]
            assert winners == data["winners"]

        if self.session["mode"] == "endless":
            if len(data["players"]) == 1:
                assert data["winners"] == data["players"]
            else:
                assert data["winners"] == \
                        [i for i in data["players"] if not i["out"]]

    def extract_tick_player(self, tick):
        return [i for i in tick["players"] if i["username"]==self.username][0]

@database_sync_to_async
def get_player(username):
    try:
        playerobj = Player.objects.get(username=username)
    except:
    #    playerobj = Player.objects.create_user(
    #        username=username,
    #        password=DEFAULT_PASSWORD,
    #        )
        pass
    return playerobj


@database_sync_to_async
def get_session(session_id):
#   try:
    session_obj = GameSession.objects.get(session_id=session_id)
#   except:
    #    playerobj = Player.objects.create_user(
    #        username=username,
    #        password=DEFAULT_PASSWORD,
    #        )
    #   pass
    return session_obj 


@pytest.fixture(scope="function", autouse=True)
def create_players():
    Player.objects.all().delete()
    for case in TEST_CASES:
        for username, player in case["players"].items():
            try:
                player = Player.objects.get(username=username)
            except:
                 player = Player.objects.create_user(
                     username=username,
                     password=DEFAULT_PASSWORD,
                 )

        sesh = GameSessionSerializer(
            data={
                "name": "gayshit",
                "password": "cathedral",
                "mode": case["mode"],
                },
            fields=("name","password","players_max","mode"),
            context={"user": player},
            )
        if sesh.is_valid():
            SESSIONS.append(sesh.save().session_id)
            print("YAY TACOS ARE YUMMY")


@database_sync_to_async
def get_tokens(username):
    factory = APIRequestFactory()
    request = factory.post(
        reverse("auth"),
        {
            "username": username,
            "password": DEFAULT_PASSWORD,
        },
        format="json",
        )
    view = SwaggeredTokenObtainPairView.as_view()
    response = view(request)
    return response.data

async def prep(case, app):
    session_obj = await get_session(SESSIONS.pop(0))

    session = {
        "url": "/ws/play/"+case["mode"]+"/"+session_obj.session_id,
        "state":"prep",
        "app": app,
        "obj": session_obj,
        "mode": case["mode"],
        }
    players = dict()
    for username, player in case["players"].items():
        url = session["url"]
        if player["authenticated"]:
            playerobj = await get_player(username)
            tokens = await get_tokens(username) 
            url += "/{}/?".format(tokens["access"])
        else:
            playerobj = AnonymousUser
            url += "?username="+username+"&"
        url += "password=cathedral"

        players[username] = SessionPlayer(playerobj, session, url, username) ##

    for events in case["prep"]["events"]:
        player = players[events["player"]]
        for action in events["actions"]:
            await player.act(action)

    print("!"*30)
    pprint(session)
    print("!"*30)

    return case, session, players

async def game(case, session, players):
    session["state"] = "game"
    for events in case["game"]["events"]:
        player = players[events["player"]]
        for action in events["actions"]:
            await player.act(action)

    return case, session, players

async def renew(case, session, players):
    for events in case["renew"]["events"]:
        player = players[events["player"]]
        for action in events["actions"]:
            await player.act(action)

    await database_sync_to_async(
        session["obj"].refresh_from_db
        )()
    assert not session["obj"].finished

    return case, session, players


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_classic_consumer():
    """
    Ensures player can join a game and play with the following being true:
     If session_id from url corresponds to valid (session.finished==0) db entry:
      * Game results are saved including AnonymousPlayer's scores/speeds
      * No more than session.players can join if session.players != 0
     Elif (session.finished==1):
      * player shouldn't be able to connect
     Elif (session.DoesNotExist):
      * It's a VERY SECRET session :)
     When player joins:
      * His score and speed are zero-initialized
      If player is authenticated:
        * He's playing under his username 
        * His results are gonna be recorded to db at the end of the game
        * He can't spawn multiple instances of himself in a session
      Else:
        * Player is given to choose his username with "anon_username" message
        * If username is present in the session, it gets mangled
        * If authenticated player with such name joins, anon's name gets mangled
          In this case, message "username_switch" is broadcasted
      Finally:
        * First message is "words", containing N session words
        * Second message is "player_joined" triggered by him (contains username)

     In session (preparation stage):
       * Game does not begin until all players are ready
       * No messages except for "ready" will be accepted
       * Once all players are ready -
       If there are several players:
        * There's a delay described by "get_ready" message
       Finally:
        * "game_begins" is sent 

     In session (game stage):
      * Player may send "word"s and will receive "new_word" in response to 
        that. Other messages may be received before "new_word". 
       * If the word sent is correct (matches the first one in word pool), 
         player gains "len(word)*2" points, speed is updated according to 
         "len(all_words_concatenated) / time_passed" formula.
       * Else, player loses "round(len(word)/2))" points
      * During the game, "tick"s are being sent periodically, keeping player
        up-to-date with session scores, speeds, time left to the end, etc.
      * No other player may join the game (unless game room is empty?)
      * Player may leave at any point of game session, game is not affected
      * Once N seconds have passed, "game_over" is broadcasted. Results of every
        authenticated player in session are saved. Player with best score wins.
        Connections persist
     
     In session (renew stage):
      * Players are free to leave, or request a new session via "renew" message
      * Once every player left is ready to renew, a new db session entry is
        created and "new_session" is broadcasted. Everybody disconnects
    """

    APPLICATION = JWTAuthMiddleware(
        URLRouter([
            path(
                "ws/play/dummy/<str:session_id>/<str:jwt>/",
                consumers.BaseGameConsumer
                ),
            path(
                "ws/play/single/<str:session_id>/<str:jwt>/",
                consumers.SingleGameConsumer
                ),
            path(
                "ws/play/endless/<str:session_id>/<str:jwt>/",
                consumers.EndlessGameConsumer
                ),
            path(
                "ws/play/tugofwar/<str:session_id>/<str:jwt>/",
                consumers.TugOfWarGameConsumer
                ),
            path(
                "ws/play/ironwall/<str:session_id>/<str:jwt>/",
                consumers.IronWallGameConsumer
                ),
            path(
                "ws/play/dummy/<str:session_id>",
                consumers.BaseGameConsumer
                ),
            path(
                "ws/play/single/<str:session_id>",
                consumers.SingleGameConsumer
                ),
            path(
                "ws/play/endless/<str:session_id>",
                consumers.EndlessGameConsumer
                ),
            path(
                "ws/play/tugofwar/<str:session_id>",
                consumers.TugOfWarGameConsumer
                ),
            path(
                "ws/play/ironwall/<str:session_id>",
                consumers.IronWallGameConsumer
                ),
            ])
        )
#   session = {
#       "url": "/ws/play/"+consumers.SingleGameConsumer.MODE+"/catsarentbirbs",
#       "state":"prep",
#       "mode": consumers.SingleGameConsumer.MODE,
#       "app": APPLICATION,
#       }
#   players = dict()
#   case = TEST_CASES[0]

#   for username, player in case["players"].items():
#       url = session["url"]
#       if player["authenticated"]:
#           playerobj = await get_player(username)
#           tokens = await get_tokens(username) 
#           url += "/{}/".format(tokens["access"])
#       else:
#           playerobj = AnonymousUser
#
#   communicator = WebsocketCommunicator(
#       APPLICATION,
#       session["url"],
#       )
#   connected, subprotocol = await communicator.connect()
#   if session["state"] == "game":
#       assert not connected
#   assert connected

#   if playerobj is AnonymousUser:
#       await communicator.send_json_to({
#           "event": "anon_username",
#           "data": username,
#           })
#
#   msg = await communicator.receive_json_from()
#   assertMessageIsWords(msg)
#
#   msg = await communicator.receive_json_from()
#   assert type(msg) is dict
#   event, data = msg.get("event", None), msg.get("data", None)
#   assert event == "player_joined"
#   if playerobj is AnonymousUser:
#       assert data["username"].startswith(username)
#       if username != data["username"]:
#           username = data["username"]
#           assert len(username.split("_")) > 1
#   else:
#       assert username == data["username"]
    for case in TEST_CASES:
        print("*** Starting case {} ***".format(case))
        await renew(
            *await game(
                *await prep(case, APPLICATION),
                )
            )
        print("*** Case passed!! ***".format(case))
