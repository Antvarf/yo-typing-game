from rest_framework import serializers

from .models import (
    SessionPlayerResult,
    Player,
    GameSession,
    GameModes,
)


class CoolChoiceField(serializers.ChoiceField):
    """
    ChoiceField that replaces raw db values with readable labels and vice-versa
    (e.g 'single' is a valid choice for request data and 's' is not)
    """
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


class GameSessionSerializer(serializers.ModelSerializer):
    mode = CoolChoiceField(choices=GameModes.choices)
    password = serializers.CharField(write_only=True, required=False)
    session_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = GameSession
        fields = ('id', 'mode', 'session_id', 'name', 'is_private',
                  'players_max', 'players_now', 'password')
