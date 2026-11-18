from rest_framework.permissions import BasePermission

from .models import Profile


def _role(user):
    profile = getattr(user, "profile", None)
    return profile.role if profile else None


class IsFarmer(BasePermission):
    message = "Only farmers can do that."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and _role(request.user) == Profile.FARMER)


class IsBuyer(BasePermission):
    message = "Only buyers can do that."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and _role(request.user) == Profile.BUYER)


class IsOwner(BasePermission):
    """Object-level: the record belongs to the requesting user (farmer or buyer field)."""

    message = "You can only change your own records."

    def has_object_permission(self, request, view, obj):
        return getattr(obj, "farmer_id", None) == request.user.id or getattr(obj, "buyer_id", None) == request.user.id
