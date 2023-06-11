from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


@database_sync_to_async
def get_user_from_query_string(query_string: bytes):
    authenticator = JWTAuthentication()
    user = AnonymousUser

    params = parse_qs(query_string.decode())
    token = params.get('jwt', (None,))[0]
    if token:
        try:
            raw_token = authenticator.get_raw_token(b"JWT " + token.encode())
            validated_token = authenticator.get_validated_token(raw_token)
            user = authenticator.get_user(validated_token)
        except AuthenticationFailed:
            pass

    return user


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope['user'] = await get_user_from_query_string(scope['query_string'])
        return await self.app(scope, receive, send)
