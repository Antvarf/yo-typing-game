import secrets

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Player, GameSession
from .views import (
    LEADERBOARD_FIELDS,
    SESSION_DETAILS_FIELDS,
    )


class PlayersTest(APITestCase):
    creds = {"username": "Jesus", "password": "pleaseLetMeHaveTimeWithMyFriend"}

    def setUp(self):
        Player.objects.create_user(**self.creds)

    def test_create_player(self):
        """
        Ensures we are able to create new players so that:
            * Player names stay unique
            * The only considered input is "username" and "password"
            * Both "username" and "password" fields are required 
            * No possible input can alter a player that already exists
            * Player score and speed are initialized to 0
        """
        def check_new_player(player):
            self.assertEqual(player.score, 0)
            self.assertEqual(player.best_classic_score, 0)
            self.assertEqual(player.best_endless_score, 0)
            self.assertEqual(player.best_ironwall_score, 0)
            self.assertEqual(player.best_tugofwar_score, 0)
            self.assertEqual(player.avg_classic_score, 0)
            self.assertEqual(player.avg_endless_score, 0)
            self.assertEqual(player.avg_ironwall_score, 0)
            self.assertEqual(player.avg_tugofwar_score, 0)
            self.assertEqual(player.games_played, 0)
            self.assertEqual(player.classic_played, 0)
            self.assertEqual(player.endless_played, 0)
            self.assertEqual(player.ironwall_played, 0)
            self.assertEqual(player.tugofwar_played, 0)
            self.assertEqual(player.avg_speed, 0)
            self.assertEqual(player.best_speed, 0)
            self.assertEqual(player.sessions.all().exists(), False)

        url = reverse("players")

        #DEVISE A NEW FUZZING STRATEGY. WE HAVE LEADERS_FIELDS BTW
        good_cases = [
            {"username": "373rn4l1n50mn14", "password": "d45h4f7w"},
            {"username": "A", "password": "A", "score": 1000},
            {"username": "B", "password": "B", "speed": 10.0},
            {"username": "C", "password": "C", "score": 0, "speed": 10.0},
            {"username": "D", "password": "D", "score": -100, "speed": -10.0},
            {"username": "E", "password": "E", "score": True, "speed": True},
            ]

        bad_cases = [
            {"username": "", "password": "hoo"},
            {"username": "based", "password": ""},
            {"username": "", "password": ""},
            {"username": "yes"},
            {"username": ""},
            {"password": "no"},
            {"password": ""},
            {"username": "373rn4l1n50mn14", "password": "hijackedUrAcc"},
            {"username": "terrible", "score": 0, "speed": 0},
            {"password": "terrible", "score": 0, "speed": 0},
            ]

        for data in good_cases:
            player_count = Player.objects.count()
            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(Player.objects.count(), player_count + 1)

            player = Player.objects.get(username=data["username"])
            self.assertEqual(player.username, data["username"])
            check_new_player(player)

            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(Player.objects.count(), player_count + 1)
            player = Player.objects.get(username=data["username"])
            self.assertEqual(player.username, data["username"])
            check_new_player(player)

        players = Player.objects.values()
        player_count = len(players)

        for data in bad_cases:
            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            new_players = Player.objects.values()
            self.assertEqual(len(new_players), player_count)
            for old, new in zip(players, new_players):
                self.assertDictEqual(old, new)

    def test_get_leaders(self):
        """
        Ensures we can obtain list of players such that:
            * Player objects are sorted by field from LEADERS_FIELS (descending)
            * Default sorting is by total score, descending
            * Only allowed fields are exposed
            * Every player is present (planning to introduce pagination later)
            * Polling this endpoint causes no side effects (HOW?)
        TODO:
            * refactor this test so that isolate users were tested for sesh recs
        """

        for i in LEADERBOARD_FIELDS:
            leaders = Player.objects.order_by("-{}".format(i)).values(*LEADERBOARD_FIELDS)
            response = self.client.get(reverse("players")+"?orderby={}".format(i), format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertListEqual(response.data, list(leaders))

        leaders = Player.objects.order_by("-score").values(*LEADERBOARD_FIELDS)
        # Check bad field values
        for i in ["guacamole", ""]:
            response = self.client.get(reverse("players")+"?orderby={}".format(i), format="json")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertListEqual(response.data, list(leaders))
        # Check abscent orderby param
        response = self.client.get(reverse("players"), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertListEqual(response.data, list(leaders))

    def test_get_player(self):
        """
        Ensures we can request player details so that:
            * LEADERBOARD_FIELDS+date_joined+sessions were joined
            * if player with given id doesn't exist, return 404
            * the only allowed method is GET
        TODO:
            * player with id 0xdeadbeef doesn't exist
            * side effects fuzzing? 
            * http methods fuzzing?
            ? sessions field is of list type with correct item fields
        """
        # CREATE PLAYERS
        for player in Player.objects.all():
            response = self.client.get(
                reverse("players")+str(player.id)+"/",
                format="json",
                )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertSetEqual(
                set(LEADERBOARD_FIELDS+["date_joined","sessions"]),
                set(response.data.keys()),
                )

        response = self.client.get(
            reverse("players")+str(0xdeadbeef)+"/",
            format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post(
            reverse("players")+str(player.id)+"/",
            format="json",
            )
        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            )


class ObtainTokensTest(APITestCase):
    creds = {"username": "Jesus", "password": "pleaseLetMeHaveTimeWithMyFriend"}

    def setUp(self):
        Player.objects.create_user(**self.creds)

    def test_obtain_pair(self):
        """
        Ensures we can obtain access/refresh JWT pair with the right credentials
        """
        response = self.client.post(reverse("auth"), self.creds, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)


class RefreshTokensTest(APITestCase):
    creds = {"username": "Jesus", "password": "pleaseLetMeHaveTimeWithMyFriend"}

    def setUp(self):
        Player.objects.create_user(**self.creds)
        # do we really just presume this post is gonna work?
        response = self.client.post(reverse("auth"), self.creds, format="json")
        self.tokens = response.data
        self.tokens.pop("access")

    def test_refresh_pair(self):
        """
        Ensures we can use refresh token in a way that:
            * We are allowed to utilise this token to obtain new pair
            * We can't use old access/refresh pair after getting a new one
            * We can't use outdated refresh token (HOW?)
        """
        url = reverse("auth_refresh")
        response = self.client.post(url, self.tokens, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        
        response = self.client.post(url, self.tokens, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SessionsTest(APITestCase):

    def setUp(self):
        self.test_session_id = "dancewiththedeadconcert"
        self.test_session_mode = "i"
        self.test_session_mode_repr = "ironwall"
        self.test_session_players = 9000
        self.test_session_name = "crawling"

        self.other_session_id = "daydreamsuchabeautifulday"
        self.other_session_mode = "t"
        self.other_session_mode_repr = "tugofwar"
        self.other_session_players = 1337
        self.other_session_name = "autumn"

        self.creds = {
            "username": "Jesus",
            "password": "pleaseLetMeHaveTimeWithMyFriend"
            }
        self.test_user = Player.objects.create_user(**self.creds)

        self.session = GameSession.objects.create(
            creator=self.test_user,
            session_id=self.test_session_id,
            mode=self.test_session_mode,
            players_max=self.test_session_players,
            name=self.test_session_name,
            )

        self.other_creds = {
            "username": "somerandomguy", 
            "password": "ha",
            }
        self.other_user = Player.objects.create_user(**self.other_creds)
        self.other_session = GameSession.objects.create(
            creator=self.other_user,
            session_id=self.other_session_id,
            mode=self.other_session_mode,
            players_max=self.other_session_players,
            name=self.other_session_name,
            )

    def test_create_session(self):
        """
        Ensures we can create a session in a way that:
            * If request is unauthorized, session is created by AnonymousUser
            * The only considered input is "mode" and "players"
            * If input is considered bad, code 400 is returned

            * Only "mode" field is required
            * "mode" input field value is one of the possible string choices
            * All possible choices are valid

            * If "players" field is provided, it should be integer and >= 0
            * If "players" field is not provided, it's initialized to 0
            * If "players" field is provided with invalid value, input is bad

            * No possible input can alter a session that already exists
        """

        url = reverse("sessions")

        good_cases = [
            {"mode": "single", "players_max": 9, "name": "asia"},
            {"mode": "single", "name": "asia"},
            {
                "mode": "single",
                "creator": {
                    "username": self.other_creds["username"] # shouldn't be him
                    },
                "name": "asia",
            },
            {"mode": "single", "session_id": "cantsethatvalue", "name": "asia"},
            {
                "mode": "single",
                "session_id": self.test_session_id,
                "name": "asia"
            },
            {
                "mode": self.test_session_mode_repr,
                "session_id": self.test_session_id,
                "creator": {
                    "username": self.other_user.username,
                    },
                "name": "asia",
            },
            {
                "mode": self.other_session_mode_repr,
                "session_id": "cantsetthat",
                "creator": {
                    "username": self.other_user.username,
                    },
                "name": "asia",
            },
            ]

        bad_cases = [
            {"mode": "badmode", "players_max": 9},
            {"mode": "single", "players_max": -1},
            {"mode": ""},
            ]

        sessions = GameSession.objects.values()
        old_len = len(sessions)

        for data in good_cases:
            print(" * checking {}".format(data))
            session_count = GameSession.objects.count()
            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertSetEqual({"session_id",}, set(response.data.keys()))
            self.assertEqual(GameSession.objects.count(), session_count+1)

            session = GameSession.objects.get(**response.data)
            self.assertEqual(session.creator, None)
            if ("players_max" in data) and (data["players_max"] > 0):
                self.assertEqual(session.players_max, data["players_max"])
            else:
                self.assertEqual(session.players_max, 0)

            if "session_id" in data:
                self.assertNotEqual(session.session_id, data["session_id"])

        sessions = GameSession.objects.values()
        old_len = len(sessions)

        for data in bad_cases:
            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            new_sessions = GameSession.objects.values()
            new_len = len(new_sessions)
            self.assertEqual(old_len, new_len)

            for old, new in zip(sessions, new_sessions):
                self.assertDictEqual(old, new)

        self.client.force_authenticate(user=self.test_user)

        for data in good_cases:
            print(" * checking {}".format(data))
            session_count = GameSession.objects.count()
            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertSetEqual({"session_id",}, set(response.data.keys()))
            self.assertEqual(GameSession.objects.count(), session_count+1)

            session = GameSession.objects.get(**response.data)
            self.assertEqual(session.creator, self.test_user)
            if ("players_max" in data) and (data["players_max"] > 0):
                self.assertEqual(session.players_max, data["players_max"])
            else:
                self.assertEqual(session.players_max, 0)

            if "session_id" in data:
                self.assertNotEqual(session.session_id, data["session_id"])

        sessions = GameSession.objects.values()
        old_len = len(sessions)

        for data in bad_cases:
            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            new_sessions = GameSession.objects.values()
            new_len = len(new_sessions)
            self.assertEqual(old_len, new_len)

            for old, new in zip(sessions, new_sessions):
                self.assertDictEqual(old, new)

    def test_get_session(self):
        """
        Ensures we can request session details so that:
            * only allowed fields are exposed (SESSION_DETAILS_FIELDS)
            * if a session with given id doesn't exist, return 404
            * the only allowed method is GET
        TODO:
            * session with id 0xdeadbeef doesn't exist
            * side effects fuzzing? 
            * http methods fuzzing?
            ? players field is of list type with correct item fields
        REFACTOR:
            ? give up on magic values for session ids
        """
        for session in GameSession.objects.all():
            print("* checking {}".format(session))
            response = self.client.get(
                reverse("sessions")+str(session.session_id)+"/",
                format="json",
                )
            print(response)
            print("* request url: {}".format(
                reverse("sessions")+str(session.session_id)+"/",
                ))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertSetEqual(
                set(SESSION_DETAILS_FIELDS),
                set(response.data.keys()),
                )

        response = self.client.get(
            reverse("sessions")+str(0xdeadbeef)+"/",
            format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.post(
            reverse("sessions")+str(session.session_id)+"/",
            format="json",
            )
        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            )
