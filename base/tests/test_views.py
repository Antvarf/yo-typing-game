from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from base.models import Player, GameSession, GameModes

User = get_user_model()


class PlayerTestCase(APITestCase):
    """Test cases for CRUD on Player instances"""
    def setUp(self):
        credentials = {
            'username': 'test_player_1',
            'password': 'DanielRadcliffeIsScary',
        }
        user = User.objects.create_user(**credentials)
        another_user = User.objects.create_user(
            username='test_player_3', password='hehe',
        )
        self.player = user.player
        self.another_player = another_user.player
        self.anonymous_player = Player.objects.create(
            displayed_name='anonymous_test_player_2',
        )

    def test_player_list(self):
        """
        Players can be listed by anyone with the following fields:
            * id
            * displayed_name
        """
        url = reverse('yo_game:player-list')
        response = self.client.get(url)
        object_fields = set(['id', 'displayed_name'])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for p in response.data:
            self.assertEqual(p.keys(), object_fields)

    def test_player_details(self):
        """
        Player details can be viewed by anyone with the following fields:
            * id
            * displayed_name
            * games_played
            * avg_score
            * best_score
            * avg_speed
            * best_speed
        """
        url = reverse('yo_game:player-detail', args=[self.player.pk])
        response = self.client.get(url)
        player = response.data
        object_fields = set(
            ['id', 'displayed_name', 'games_played', 'avg_score',
             'best_score', 'best_speed', 'avg_speed', 'total_score']
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(player.keys(), object_fields)

    def test_player_update(self):
        self.client.force_authenticate(user=self.player.user)

        url = reverse('yo_game:player-detail', args=[self.player.id])
        response = self.client.put(url, {'displayed_name': 'dancedancewithme'})
        self.player.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.player.displayed_name, 'dancedancewithme')

    def test_update_another_player_fails(self):
        self.client.force_authenticate(user=self.player.user)

        url = reverse('yo_game:player-detail', args=[self.another_player.id])
        response = self.client.put(url, {'displayed_name': 'dancedancewithme'})
        self.another_player.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotEqual(
            self.another_player.displayed_name,
            'dancedancewithme',
        )

    def test_update_unauthenticated_fails(self):
        url = reverse('yo_game:player-detail', args=[self.player.id])
        response = self.client.put(url, {'displayed_name': 'dancedancewithme'})
        self.player.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotEqual(self.player.displayed_name, 'dancedancewithme')

    def test_player_update_anonymous_fails(self):
        self.client.force_authenticate(user=self.player.user)

        url = reverse('yo_game:player-detail', args=[self.anonymous_player.id])
        response = self.client.put(url, {'displayed_name': 'dancedancewithme'})
        self.anonymous_player.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotEqual(
            self.anonymous_player.displayed_name,
            'dancedancewithme',
        )

    def test_player_delete(self):
        """Operation is not allowed even for authenticated player"""
        self.client.force_authenticate(user=self.player.user)
        players = (self.player, self.anonymous_player, self.another_player)
        for player in players:
            url = reverse('yo_game:player-detail', args=[player.id])
            response = self.client.delete(url)
            self.assertEqual(response.status_code,
                             status.HTTP_405_METHOD_NOT_ALLOWED)
            Player.objects.get(id=player.id)

    def test_player_create_fails(self):
        """Player creation is handled by other API parts and is not allowed"""
        url = reverse('yo_game:player-list')
        data = {
            'displayed_name': 'new_test_player',
            'user': None,
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        with self.assertRaises(Player.DoesNotExist):
            Player.objects.get(**data)

        # Fails for authenticated user as well
        data['user'] = self.player.user
        self.client.force_authenticate(user=self.player.user)
        response = self.client.post(url, data)

        self.assertEqual(response.status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        with self.assertRaises(Player.DoesNotExist):
            Player.objects.get(**data)

    def test_player_my_profile(self):
        self.client.force_authenticate(user=self.player.user)
        url = reverse('yo_game:player-my-profile')
        object_fields = set(['id', 'displayed_name'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.keys(), object_fields)

    def test_player_my_profile_fails_unauthenticated(self):
        url = reverse('yo_game:player-my-profile')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_player_stats(self):
        url = reverse('yo_game:player-stats')
        object_fields = set(
            ['id', 'displayed_name', 'games_played', 'avg_score',
             'best_score', 'best_speed', 'avg_speed', 'total_score']
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for player in response.data:
            self.assertEqual(player.keys(), object_fields)


class SessionTestCase(APITestCase):
    def setUp(self):
        credentials = {
            'username': 'test_player_1',
            'password': 'DanielRadcliffeIsScary',
        }
        user = User.objects.create_user(**credentials)
        self.player = user.player
        self.session = GameSession.objects.create(
            mode=GameModes.SINGLE,
            creator=self.player,
        )
        self.object_fields = set(['id', 'session_id', 'mode', 'name',
                                   'is_private', 'players_max', 'players_now'])


    def test_create_session(self):
        self.client.force_authenticate(user=self.player.user)
        url = reverse('yo_game:gamesession-list')
        data = {
            'mode': 'single',
            'name': 'test_session_1',
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.keys(), self.object_fields)

    def test_authenticated_create_session(self):
        url = reverse('yo_game:gamesession-list')
        data = {
            'mode': 'single',
            'name': 'test_session_1',
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data.keys(), self.object_fields)

    def test_list_sessions(self):
        url = reverse('yo_game:gamesession-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for obj in response.data:
            self.assertEqual(obj.keys(), self.object_fields)
            self.assertEqual(obj['is_private'], False)

    def test_private_and_finished_sessions_are_not_listed(self):
        private_session = GameSession.objects.create(
            mode=GameModes.SINGLE,
            is_private=True,
        )
        finished_session = GameSession.objects.create(
            mode=GameModes.SINGLE,
            is_finished=True,
        )
        url = reverse('yo_game:gamesession-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for obj in response.data:
            self.assertEqual(obj.keys(), self.object_fields)
            self.assertEqual(obj['is_private'], False)
            self.assertNotEqual(obj['id'], private_session.id)
            self.assertNotEqual(obj['id'], finished_session.id)

    def test_retreive(self):
        url = reverse('yo_game:gamesession-detail', args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.keys(), self.object_fields)

    def test_delete_not_allowed(self):
        url = reverse('yo_game:gamesession-detail', args=[self.session.id])
        response = self.client.delete(url)

        self.session.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_edit_session_settings(self):
        url = reverse('yo_game:gamesession-detail', args=[self.session.id])
        responses = [
            self.client.put(url),
            self.client.patch(url),
        ]

        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_session_filters(self):
        pass

