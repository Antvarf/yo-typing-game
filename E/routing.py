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
        ),
    "channel": ChannelNameRouter({
        "game-tick": consumers.GameTickConsumer,
        }),
})
