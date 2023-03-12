from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.mixins import UpdateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from . import serializers
from .models import Player
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
