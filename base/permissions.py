from django.contrib.auth.models import AnonymousUser
from rest_framework import permissions


class IsPlayerOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to allow only the authenticated users to edit their
    respective player profiles.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user == obj.user != AnonymousUser
