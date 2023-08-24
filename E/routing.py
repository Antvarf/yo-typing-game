from django.urls import path

from channels.routing import (
    ProtocolTypeRouter,
    ChannelNameRouter,
    URLRouter,
    )
from .auth import JWTAuthMiddleware

from base.websocket import consumers


application = ProtocolTypeRouter({
    "websocket": JWTAuthMiddleware(
        URLRouter([
            path(
                "ws/play/<str:session_id>/",
                consumers.GameConsumer.as_asgi(),
                ),
            ])
        ),
    "channel": ChannelNameRouter({
        "game-tick": consumers.GameTickConsumer.as_asgi(),
        }),
})
