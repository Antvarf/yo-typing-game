from django.urls import path
from rest_framework_simplejwt.views import TokenVerifyView

from . import views


app_name = 'jwt_accounts'
urlpatterns = [
    path('', views.SwaggeredTokenObtainPairView.as_view(),
         name='obtain_jwt_pair'),
    path('refresh/', views.SwaggeredTokenRefreshView.as_view(),
         name='refresh_jwt_pair'),
    path('verify/', TokenVerifyView.as_view(),
         name='verify_jwt_pair'),
    path('signup/', views.CreateUserView.as_view(),
         name='create_user'),
]
