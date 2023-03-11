from drf_yasg.utils import swagger_auto_schema
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