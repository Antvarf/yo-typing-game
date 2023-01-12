import pytest
from django.db import close_old_connections
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from channels.db import database_sync_to_async
from asgiref.sync import async_to_sync

from base.models import Player

class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    def __call__(self, scope):
        # This call is recommended by current version of django channels docs
        close_old_connections()

        authenticator = JWTAuthentication()

        token = scope["path"].rstrip("/").split("/")[-1]
        try:
            raw_token = authenticator.get_raw_token(b"JWT "+token.encode())
            validated_token = authenticator.get_validated_token(raw_token)
            user = authenticator.get_user(validated_token)
        except:
            user = AnonymousUser

        return self.inner(dict(scope, user=user))
