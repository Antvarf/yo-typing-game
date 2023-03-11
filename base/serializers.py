# from secrets import (
#     token_hex,
#     token_urlsafe,
#     )
#
# from django.contrib.auth.models import AnonymousUser
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
    )

from .models import (
    SessionPlayerResult,
    Player,
    # GameSession,
    # GameModes,
    )


# class CoolChoiceField(serializers.ChoiceField):
#
#     def to_representation(self, data):
#         if data not in self.choices.keys():
#             self.fail('invalid_choice', input=data)
#         else:
#             return self.choices[data]
#
#     def to_internal_value(self, data):
#         for dbrec, disprec in self.choices.items():
#             if disprec == data:
#                 return dbrec
#         self.fail('invalid_choice', input=data)
#
#
# class DynamicFieldsModelSerializer(serializers.ModelSerializer):
#     def __init__(self, *args, **kwargs):
#         fields = kwargs.pop('fields', None)
#         super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)
#         if fields is not None:
#            allowed = set(fields)
#            existing = set(self.fields)
#            for i in existing - allowed:
#                self.fields.pop(i)


class SessionPlayerResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionPlayerResult
        fields = '__all__'


class PlayerSerializer(serializers.ModelSerializer):
    best_score = serializers.IntegerField(read_only=True)
    best_speed = serializers.FloatField(read_only=True)
    avg_score = serializers.FloatField(read_only=True)
    avg_speed = serializers.FloatField(read_only=True)
    games_played = serializers.IntegerField(read_only=True)
    # sessions = SessionPlayerResultSerializer(many=True,
    #                                          read_only=True, required=False)

    class Meta:
        model = Player
        exclude = ('user',)

# class GameSessionSerializer(DynamicFieldsModelSerializer):
#     creator = PlayerSerializer(
#         fields=("username",),
#         )
#     mode = CoolChoiceField(choices=GameModes.choices)
#     players_max = serializers.IntegerField(min_value=0, required=False)
#     players_now = serializers.IntegerField(
#         min_value=0,
#         required=False,
#         read_only=True
#         )
#     players = SessionPlayerResultSerializer(many=True)
#     name = serializers.CharField(max_length=50)
#     password = serializers.CharField(max_length=50, required=False)
#
#     def create(self, validated_data):
#         user = self.context["user"]
#         if user is AnonymousUser:
#             creator=None
#         else:
#             creator=Player.objects.get(username=self.context['user'].username)
#
#         password = validated_data.pop("password", None)
#         if password is not None:
#             validated_data["password"] = make_password(password)
#             validated_data["private"] = True
#
#         while True:
#             session_id = token_hex(SESSION_ID_LENGTH // 2)
#             if not GameSession.objects.filter(session_id=session_id):
#                 break
#
#         name = validated_data["name"]
#         while GameSession.objects.filter(name=name):
#             name = validated_data["name"]+"_"+token_urlsafe(3)
#         validated_data["name"] = name
#
#         return GameSession.objects.create(
#             session_id=session_id,
#             creator=creator,
#             **validated_data,
#             )
#
#     class Meta:
#         model = GameSession
#         fields = "__all__"
#         ref_name = None