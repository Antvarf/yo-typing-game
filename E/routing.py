from django.urls import path

from channels.routing import (
    ProtocolTypeRouter,
    ChannelNameRouter,
    URLRouter,
    )
from .auth import JWTAuthMiddleware

from base import consumers


application = ProtocolTypeRouter({
    "websocket": JWTAuthMiddleware(
        URLRouter([
            path(
                "ws/play/<str:session_id>/",
                consumers.GameConsumer,
                ),
            ])
        ),
    "channel": ChannelNameRouter({
        "game-tick": consumers.GameTickConsumer,
        }),
})
