from django.urls import path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from . import views


schema_view = get_schema_view(
    openapi.Info(
        title="Ё api",
        default_version="v1",
        description="SOME VERY NICE AND POLITE DESCRIPTION",
        contact=openapi.Contact(email="warrior@typewars.ru"),
        ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    )

urlpatterns = [
    path("sessions/<str:session_id>/", views.get_session),
    path("sessions/", views.sessions, name="sessions"),
    path("players/<int:player_id>/", views.get_player),
    path("players/", views.players, name="players"),
    path("auth/", views.SwaggeredTokenObtainPairView.as_view(), name="auth"),
    path(
        "auth/refresh/",
        views.SwaggeredTokenRefreshView.as_view(),
        name="auth_refresh",
        ),
    path("swagger/", schema_view.with_ui('swagger')),
]
