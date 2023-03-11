from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from base.models import Player


User = get_user_model()


class AuthAPITestCase(APITestCase):
    """Tests that:
        * user can be created given the username doesn't exist and password is non-empty
         `- bad username/password yield 400, 201 on success
        * if given the right credentials, auth-refresh JWT pair is obtained
         `- wrong credentials yield 401, 200 on success
        * refresh endpoint invalidates old refresh token (should be full pair?)
      --------------------
        ? new JWT pair obtained via auth doesn't invalidate another one alike
    """

    def setUp(self):
        self.credentials = {
            "username": "test_user_1",
            "password": "aPwSoStrong&SecureItMakes[Inf]HackersCry1e1000times",
        }
        self.user = User.objects.create_user(**self.credentials)
        self.create_user_url = reverse('jwt_accounts:create_user')
        self.auth_url = reverse('jwt_accounts:obtain_jwt_pair')
        self.refresh_url = reverse('jwt_accounts:refresh_jwt_pair')
        self.auth_check_url = reverse('jwt_accounts:verify_jwt_pair')

    def test_create_user_with_duplicate_username_fails(self):
        user_before_create = User.objects.get(
            username=self.credentials['username']
        )
        response = self.client.post(
            self.create_user_url,
            data=self.credentials,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            user_before_create,
            User.objects.get(username=self.credentials['username']),
        )

    def test_create_user(self):
        """
        * duplicate passwords are allowed
        * password is not saved in plaintext (user created w/ .create_user())
        """
        self.credentials['username'] = 'test_user_2'
        with self.assertRaises(User.DoesNotExist):
            user_before_create = User.objects.get(
                username=self.credentials['username']
            )
        response = self.client.post(
            self.create_user_url,
            data=self.credentials,
        )
        user_created = User.objects.get(username=self.credentials['username'])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(user_created.username, self.credentials['username'])
        self.assertNotEqual(
            user_created.password,
            self.credentials['password'],
        )

    def test_obtain_jwt_pair_by_credentials(self):
        """
        Ensures we can obtain access/refresh JWT pair with the right credentials
          * valid credentials yield 200 OK
          * bad credentials yield 401 Unauthorized
          * obtained token authenticates user correctly (TokenVerifyView?)
        """
        response = self.client.post(self.auth_url, self.credentials)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        access_token_data = {'token': response.data['access']}
        response = self.client.post(self.auth_check_url, access_token_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_obtain_jwt_pair_with_bad_credentials(self):
        self.credentials['password'] += 'hehe now this password is bad'
        response = self.client.post(self.auth_url, self.credentials)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)
        self.assertNotIn('refresh', response.data)

    def test_refresh_jwt_pair(self):
        """
        Ensures we can use refresh token in a way that:
            * We are allowed to utilise this token to obtain new pair
            * We can't use old access/refresh pair after getting a new one
        TODO:
            - We can't use outdated refresh token (HOW?)
        """
        response = self.client.post(self.auth_url, self.credentials)
        refresh_token_data = {'refresh': response.data['refresh']}
        access_token_data = {'token': response.data['access']}
        response = self.client.post(self.refresh_url, refresh_token_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        # Shouldn't work the 2nd time with the old refresh token
        response = self.client.post(self.refresh_url, refresh_token_data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response = self.client.post(self.auth_check_url, access_token_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # # Access tokens aren't invalidated by the blacklist part of simplejwt
        # # library, so for some time this code will just be there, waiting to
        # # be uncommented...
        # self.client.credentials(HTTP_AUTHORIZATION='JWT {}'.format(old_tokens['access']))
        # response = self.client.post(self.auth_check_url)
        # self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
