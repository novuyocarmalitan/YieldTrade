from django.contrib.auth import authenticate
from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import matching, orders
from .models import BuyRequest, Crop, Listing, Order
from .permissions import IsBuyer, IsFarmer, IsOwner
from .serializers import (
    BuyRequestSerializer, CropSerializer, ListingSerializer, OrderCreateSerializer, OrderSerializer,
    RegisterSerializer, UserSerializer,
)


# ------------------------------------------------------------------ auth

class _AuthView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RegisterView(_AuthView):
    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(_AuthView):
    def post(self, request):
        user = authenticate(username=request.data.get("username", ""), password=request.data.get("password", ""))
        if user is None or not hasattr(user, "profile"):
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ------------------------------------------------------------------ catalogue

class CropViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Crop.objects.all()
    serializer_class = CropSerializer
    pagination_class = None


def _truthy(value) -> bool:
    return str(value).lower() in ("1", "true", "yes")


class ListingViewSet(viewsets.ModelViewSet):
    serializer_class = ListingSerializer

    def get_queryset(self):
        qs = Listing.objects.select_related("crop", "farmer")
        p = self.request.query_params
        if p.get("crop"):
            qs = qs.filter(crop_id=p["crop"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("district"):
            qs = qs.filter(district__iexact=p["district"])
        if _truthy(p.get("mine")):
            qs = qs.filter(farmer=self.request.user)
        return qs

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsFarmer()]
        if self.action in ("update", "partial_update", "destroy", "matches"):
            return [IsAuthenticated(), IsFarmer(), IsOwner()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(farmer=self.request.user)

    def perform_destroy(self, instance):
        if instance.orders.exists():
            # Orders protect the record: close it instead of deleting history.
            instance.status = Listing.CLOSED
            instance.save(update_fields=["status"])
        else:
            instance.delete()

    @action(detail=True, methods=["get"])
    def matches(self, request, pk=None):
        """Open buy requests this produce could fill, best match first."""
        listing = self.get_object()
        reqs = BuyRequest.objects.filter(crop=listing.crop, status=BuyRequest.OPEN).select_related("crop", "buyer")
        ranked = matching.rank_requests(listing, reqs)
        return Response({
            "listing": ListingSerializer(listing).data,
            "matches": [{"request": BuyRequestSerializer(r).data, **s.to_dict()} for r, s in ranked],
        })


class BuyRequestViewSet(viewsets.ModelViewSet):
    serializer_class = BuyRequestSerializer

    def get_queryset(self):
        qs = BuyRequest.objects.select_related("crop", "buyer")
        p = self.request.query_params
        if p.get("crop"):
            qs = qs.filter(crop_id=p["crop"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if _truthy(p.get("mine")):
            qs = qs.filter(buyer=self.request.user)
        return qs

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsBuyer()]
        if self.action in ("update", "partial_update", "destroy", "matches"):
            return [IsAuthenticated(), IsBuyer(), IsOwner()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(buyer=self.request.user)

    def perform_destroy(self, instance):
        if instance.orders.exists():
            instance.status = BuyRequest.CANCELLED
            instance.save(update_fields=["status"])
        else:
            instance.delete()

    @action(detail=True, methods=["get"])
    def matches(self, request, pk=None):
        """Open listings ranked by 40% price and 60% volume, plus a plan to cover the whole request."""
        buy = self.get_object()
        listings = Listing.objects.filter(crop=buy.crop, status=Listing.OPEN).select_related("crop", "farmer")
        ranked = matching.rank_listings(buy, listings)
        return Response({
            "request": BuyRequestSerializer(buy).data,
            "weights": {"price": matching.PRICE_WEIGHT, "volume": matching.VOLUME_WEIGHT},
            "matches": [{"listing": ListingSerializer(l).data, **s.to_dict()} for l, s in ranked],
            "plan": matching.fulfilment_plan(buy, ranked, by="score"),
            "cheapest_plan": matching.fulfilment_plan(buy, ranked, by="cost"),
        })


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        u = self.request.user
        qs = Order.objects.filter(Q(buyer=u) | Q(listing__farmer=u)).select_related("listing__crop", "listing__farmer", "buyer")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def get_permissions(self):
        return [IsAuthenticated(), IsBuyer()] if self.action == "create" else [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        ser = OrderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        order = orders.place_order(request.user, d["listing"], d["quantity_kg"], d.get("request"))
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    def _move(self, request, pk, verb):
        return Response(OrderSerializer(orders.transition(int(pk), request.user, verb)).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return self._move(request, pk, "accept")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._move(request, pk, "reject")

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._move(request, pk, "cancel")

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._move(request, pk, "complete")
