from django.contrib.auth.models import AnonymousUser
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    )

from . import serializers, models


MODES = ("classic", "endless", "ironwall", "tugofwar")
LEADERBOARD_FIELDS = ["best_{}_score".format(i) for i in MODES]
LEADERBOARD_FIELDS.extend("avg_{}_score".format(i) for i in MODES)
LEADERBOARD_FIELDS.extend(["username", "score", "best_speed", "avg_speed","id"])
SESSION_DETAILS_FIELDS = [
    "mode", "creator", "players_max", "players_now", "private", "name",
    "players", "finished", "created_at", "started_at", "finished_at"
    ]



@swagger_auto_schema(
    method="get",
    responses={
        200: serializers.PlayerSerializer(
                fields=LEADERBOARD_FIELDS,
                many=True,
                ),
        },
    )
@api_view(["GET"])
def leaders(request):
    orderby = request.query_params.get("orderby", None)
    if orderby not in LEADERBOARD_FIELDS:
        orderby = "score"

    return Response(
        serializers.PlayerSerializer(
            models.Player.objects.order_by("-{}".format(orderby)),
            many=True,
            fields=LEADERBOARD_FIELDS,
            ).data,
        status=status.HTTP_200_OK,
        )


@swagger_auto_schema(
    method="GET",
    responses={
        200: serializers.GameSessionSerializer(
                fields=("mode", "creator", "players_max",
                        "players_now", "private", "name",
                        "players", "finished", "created_at",
                        "started_at", "finished_at"),
                ),
        404: "No session with given session_id found",
        },
    )
@api_view(["GET"])
def get_session(request, session_id=None):
    if request.method == "GET":
        if session_id is not None:
            try:
                session = models.GameSession.objects.get(session_id=session_id)
                print(session)
            except models.GameSession.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)

            return Response(
                serializers.GameSessionSerializer(
                    session,
                    fields=("mode", "creator", "players_max",
                            "players_now", "private", "name",
                            "players", "finished", "created_at",
                            "started_at", "finished_at"),
                    ).data,
                status=status.HTTP_200_OK,
                )

        return Response(status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="GET",
    responses={
        200: serializers.GameSessionSerializer(
                fields=("mode", "creator", "players_max",
                        "players_new", "private", "name",
                        "session_id",),
                many=True,
                ),
        },
    )
@swagger_auto_schema(
    method="POST",
    responses={
        201: serializers.GameSessionSerializer(fields=("session_id",)),
        400: "Invalid request, check response body for more info",
        },
    request_body=serializers.GameSessionSerializer(
        fields=("mode", "players_max", "password"),
        ),
    )
@api_view(["GET", "POST"])
def sessions(request):
    if request.method == "GET":
        finished = int(request.query_params.get("finished", False))
        return Response(
            serializers.GameSessionSerializer(
                models.GameSession.objects.filter(finished=finished),
                fields=("mode", "creator", "players_max",
                        "players_now", "private", "name",
                        "session_id",),
                many=True,
                ).data,
            status=status.HTTP_200_OK,
            )

    if request.method == "POST": # will probably add PUT later
        user = request.user if request.user.is_authenticated else AnonymousUser
        session = serializers.GameSessionSerializer(
            data=request.data,
            fields=("mode", "players_max", "name", "password"),
            context={"user": user},
            )
        if session.is_valid():
            session_obj = session.save()
            return Response(
                serializers.GameSessionSerializer(
                    session_obj,
                    fields=("session_id",),
                    ).data,
                status=status.HTTP_201_CREATED,
                )
        return Response(
            session.errors,
            status=status.HTTP_400_BAD_REQUEST,
            )
    return Response(status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="GET",
    responses={
        200: "Returns list of players sorted by given orderby query param",
        },
    request_body=serializers.PlayerSerializer(
        fields=LEADERBOARD_FIELDS,
        many=True,
        )
    )
@swagger_auto_schema(
    method="POST",
    responses={
        201: "Player created",
        400: "Invalid request, check response body for more info",
        },
    request_body=serializers.PlayerSerializer(fields=("username", "password")),
    )
@api_view(["GET", "POST"])
def players(request):
    if request.method == "GET":
        orderby = request.query_params.get("orderby", None)
        if orderby not in LEADERBOARD_FIELDS:
            orderby = "score"

        return Response(
            serializers.PlayerSerializer(
                models.Player.objects.order_by("-{}".format(orderby)),
                fields=LEADERBOARD_FIELDS,
                many=True,
                ).data,
            status=status.HTTP_200_OK,
            )

    if request.method == "POST":
        player = serializers.PlayerSerializer(
            data=request.data,
            fields=("username", "password"),
            )
        if player.is_valid():
            player.save()
            return Response(status=status.HTTP_201_CREATED)

    return Response(status=status.HTTP_400_BAD_REQUEST)


@swagger_auto_schema(
    method="GET",
    responses={
        200: "Player exists",
        404: "Player with given id doesn't exist",
        400: "Invalid request, check response body for more info",
        },
    request_body=serializers.PlayerSerializer(
        fields=LEADERBOARD_FIELDS+["date_joined", "sessions"],
        ),
    )
@api_view(["GET",])
def get_player(request, player_id=None):
    if request.method == "GET":
        try:
            player = models.Player.objects.get(id=player_id)
        except models.Player.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND,)

        return Response(
            serializers.PlayerSerializer(
                player,
                fields=LEADERBOARD_FIELDS+["date_joined", "sessions"],
                ).data,
            status=status.HTTP_200_OK,
            )

    return Response(status=status.HTTP_400_BAD_REQUEST)


class SwaggeredTokenObtainPairView(TokenObtainPairView):
    serializer_class = serializers.CustomTokenObtainPairSerializer

    @swagger_auto_schema(
        responses={
            200: serializers.TokenPairSerializer,
            400: "No user with given credentials",
            },
        )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class SwaggeredTokenRefreshView(TokenRefreshView):
    serializer_class = serializers.CustomTokenRefreshSerializer

    @swagger_auto_schema(
        responses={
            200: serializers.TokenPairSerializer,
            400: "What did you POST?",
            401: "Invalid, blacklisted or expired token",
            },
        )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)