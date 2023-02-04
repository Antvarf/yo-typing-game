from secrets import (
    token_hex,
    token_urlsafe,
    )

from django.contrib.auth.models import AnonymousUser
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
    )

from .models import (
    Player,
    GameSession,
    SessionPlayerResult,
    GameModes,
    )


class CoolChoiceField(serializers.ChoiceField):

    def to_representation(self, data):
        if data not in self.choices.keys():
            self.fail('invalid_choice', input=data)
        else:
            return self.choices[data]

    def to_internal_value(self, data):
        for dbrec, disprec in self.choices.items():
            if disprec == data:
                return dbrec
        self.fail('invalid_choice', input=data)


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        fields = kwargs.pop('fields', None)
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)
        if fields is not None:
           allowed = set(fields)
           existing = set(self.fields)
           for i in existing - allowed:
               self.fields.pop(i)


class SessionPlayerResultSerializer(DynamicFieldsModelSerializer):

    class Meta:
        model = SessionPlayerResult
        fields = "__all__"
        ref = None


class PlayerSerializer(DynamicFieldsModelSerializer):
    sessions = SessionPlayerResultSerializer(many=True)

    def create(self, validated_data):
        return Player.objects.create_user(**validated_data)

    def update(self, instance, validated_data):
        session = self.context.get("session")
        player = validated_data.get("player")
        if session["mode"] == "single":
            player.best_classic_score = max(
                score, player.best_classic_score,
                )
            player.classic_played += 1
            player.avg_classic_score *= \
                (player.classic_played - 1) / player.classic_played
            player.avg_classic_score += score / player.classic_played
            player.score += score

        elif session["mode"] == "endless":
            player.best_endless_score = max(
                score, player.best_endless_score,
                )
            player.endless_played += 1
            player.avg_endless_score *= \
                (player.endless_played - 1) / player.endless_played
            player.avg_endless_score += score / player.endless_played
            player.score += score

        elif session["mode"] == "ironwall":
            player.best_ironwall_score = max(
                score, player.best_ironwall_score,
                )
            player.ironwall_played += 1
            player.avg_ironwall_score *= \
                (player.ironwall_played - 1) / player.ironwall_played
            player.avg_ironwall_score += score / player.ironwall_played
            player.score += score

        elif session["mode"] == "tugofwar":
            player.best_tugofwar_score = max(
                score, player.best_tugofwar_score,
                )
            player.tugofwar_played += 1
            player.avg_tugofwar_score *= \
                (player.tugofwar_played - 1) / player.tugofwar_played
            player.avg_tugofwar_score += score / player.tugofwar_played
            player.score += score

        if speed is not None:
            player.best_speed = max(speed, player.best_speed)
            player.games_played += 1
            player.avg_speed *= \
                (player.games_played - 1)/ player.games_played

            player.avg_speed += speed / player.games_played

        player.save()
        return player

    class Meta:
        model = Player
        fields = "__all__"
        ref_name = None



class GameSessionSerializer(DynamicFieldsModelSerializer):
    creator = PlayerSerializer(
        fields=("username",),
        )
    mode = CoolChoiceField(choices=GameModes.choices)
    players_max = serializers.IntegerField(min_value=0, required=False)
    players_now = serializers.IntegerField(
        min_value=0,
        required=False,
        read_only=True
        )
    players = SessionPlayerResultSerializer(many=True)
    name = serializers.CharField(max_length=50)
    password = serializers.CharField(max_length=50, required=False)

    def create(self, validated_data):
        user = self.context["user"]
        if user is AnonymousUser:
            creator=None
        else:
            creator=Player.objects.get(username=self.context['user'].username)

        password = validated_data.pop("password", None)
        if password is not None:
            validated_data["password"] = make_password(password)
            validated_data["private"] = True

        while True:
            session_id = token_hex(SESSION_ID_LENGTH // 2)
            if not GameSession.objects.filter(session_id=session_id):
                break

        name = validated_data["name"]
        while GameSession.objects.filter(name=name):
            name = validated_data["name"]+"_"+token_urlsafe(3)
        validated_data["name"] = name

        return GameSession.objects.create(
            session_id=session_id,
            creator=creator,
            **validated_data,
            )

    class Meta:
        model = GameSession
        fields = "__all__"
        ref_name = None


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        return token


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        return token
