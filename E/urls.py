from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('api/auth/', include('jwt_accounts.urls')),
    path('api/', include('base.urls')),
]
