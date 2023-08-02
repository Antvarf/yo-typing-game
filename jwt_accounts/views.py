from rest_framework import permissions
from rest_framework.generics import CreateAPIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import serializers


class CreateUserView(CreateAPIView):
    permission_classes = [
        permissions.AllowAny,
    ]
    serializer_class = serializers.UserSerializer


class SwaggeredTokenObtainPairView(TokenObtainPairView):
    serializer_class = serializers.CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class SwaggeredTokenRefreshView(TokenRefreshView):
    serializer_class = serializers.CustomTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)