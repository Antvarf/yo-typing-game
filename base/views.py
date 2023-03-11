from django.contrib.auth.models import AnonymousUser
from rest_framework.decorators import api_view, action
from rest_framework.mixins import UpdateModelMixin, ListModelMixin, RetrieveModelMixin
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
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
