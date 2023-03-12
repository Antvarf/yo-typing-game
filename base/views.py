from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.mixins import (
    UpdateModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    CreateModelMixin,
)
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.viewsets import GenericViewSet

from . import serializers
from .models import Player, GameSession
from .permissions import IsPlayerOwnerOrReadOnly


class PlayerViewSet(GenericViewSet, ListModelMixin,
                    UpdateModelMixin, RetrieveModelMixin):
    serializer_class = serializers.PlayerSerializer
    queryset = Player.objects.all()
    permission_classes = [IsPlayerOwnerOrReadOnly]

    def get_queryset(self):
        if hasattr(self, 'action'):
            if self.action == 'retrieve':
                return self.queryset.with_stats()
        return self.queryset

    @action(detail=False,
            methods=['GET'],
            url_path='me',
            url_name='my-profile',
            permission_classes=[IsAuthenticated])
    def player_my_profile(self, request):
        serializer = self.get_serializer(request.user.player)
        return Response(data=serializer.data)


class SessionViewSet(GenericViewSet, ListModelMixin,
                     CreateModelMixin, RetrieveModelMixin):
    """ViewSet for operations on GameSession model"""
    serializer_class = serializers.GameSessionSerializer
    queryset = GameSession.objects.all()
    permission_classes = [AllowAny]

    def get_queryset(self):
        if hasattr(self, 'action'):
            if self.action == 'list':
                return self.queryset.filter(
                    is_finished=False,
                    is_private=False
                )
        return self.queryset