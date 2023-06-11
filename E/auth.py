from urllib.parse import parse_qs

from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    def __call__(self, scope):
        authenticator = JWTAuthentication()
        user = AnonymousUser

        params = parse_qs(scope["query_string"].decode())
        token = params.get('jwt', (None,))[0]
        if token:
            try:
                raw_token = authenticator.get_raw_token(b"JWT "+token.encode())
                validated_token = authenticator.get_validated_token(raw_token)
                user = authenticator.get_user(validated_token)
            except AuthenticationFailed:
                pass

        return self.inner(dict(scope, user=user))
