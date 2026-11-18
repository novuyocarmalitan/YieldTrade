from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import BuyRequest, Crop, Listing, Order, Profile

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="profile.role", read_only=True)
    phone = serializers.CharField(source="profile.phone", read_only=True)
    district = serializers.CharField(source="profile.district", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "role", "phone", "district"]


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    role = serializers.ChoiceField(choices=[Profile.FARMER, Profile.BUYER])
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    district = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"], user=User(username=attrs["username"]))
        return attrs

    def create(self, data):
        user = User.objects.create_user(username=data["username"], password=data["password"])
        Profile.objects.create(user=user, role=data["role"], phone=data["phone"], district=data["district"])
        return user


class CropSerializer(serializers.ModelSerializer):
    class Meta:
        model = Crop
        fields = ["id", "name"]


class ListingSerializer(serializers.ModelSerializer):
    crop_name = serializers.CharField(source="crop.name", read_only=True)
    farmer_name = serializers.CharField(source="farmer.username", read_only=True)

    class Meta:
        model = Listing
        fields = ["id", "farmer", "farmer_name", "crop", "crop_name", "quantity_kg", "price_per_kg",
                  "district", "available_from", "status", "created_at"]
        read_only_fields = ["farmer", "created_at"]

    def validate_quantity_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be more than zero. Close the listing instead.")
        return value


class BuyRequestSerializer(serializers.ModelSerializer):
    crop_name = serializers.CharField(source="crop.name", read_only=True)
    buyer_name = serializers.CharField(source="buyer.username", read_only=True)
    ordered_kg = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = BuyRequest
        fields = ["id", "buyer", "buyer_name", "crop", "crop_name", "quantity_kg", "max_price_per_kg",
                  "district", "needed_by", "status", "ordered_kg", "created_at"]
        read_only_fields = ["buyer", "created_at", "status"]


class OrderSerializer(serializers.ModelSerializer):
    crop_name = serializers.CharField(source="listing.crop.name", read_only=True)
    farmer_name = serializers.CharField(source="listing.farmer.username", read_only=True)
    buyer_name = serializers.CharField(source="buyer.username", read_only=True)
    district = serializers.CharField(source="listing.district", read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "listing", "crop_name", "farmer_name", "buyer_name", "district", "request",
                  "quantity_kg", "price_per_kg", "total", "status", "created_at", "updated_at"]
        read_only_fields = fields


class OrderCreateSerializer(serializers.Serializer):
    listing = serializers.IntegerField()
    quantity_kg = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    request = serializers.IntegerField(required=False, allow_null=True)
