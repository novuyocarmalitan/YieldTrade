from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

POSITIVE = [MinValueValidator(Decimal("0.01"))]


class Profile(models.Model):
    FARMER, BUYER = "farmer", "buyer"
    ROLES = [(FARMER, "Farmer"), (BUYER, "Buyer")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLES)
    phone = models.CharField(max_length=30, blank=True)
    district = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Crop(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Listing(models.Model):
    """Produce a farmer is selling. `quantity_kg` is what remains available (orders reserve from it)."""

    OPEN, CLOSED = "open", "closed"
    STATUSES = [(OPEN, "Open"), (CLOSED, "Closed")]

    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listings")
    crop = models.ForeignKey(Crop, on_delete=models.PROTECT, related_name="listings")
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2, validators=POSITIVE)
    district = models.CharField(max_length=100, blank=True)
    available_from = models.DateField()
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.quantity_kg}kg {self.crop} @ {self.price_per_kg}"

    @property
    def is_open(self):
        return self.status == self.OPEN and self.quantity_kg > 0


class BuyRequest(models.Model):
    """Demand a buyer has posted: how much, of what, and the most they will pay."""

    OPEN, FULFILLED, CANCELLED = "open", "fulfilled", "cancelled"
    STATUSES = [(OPEN, "Open"), (FULFILLED, "Fulfilled"), (CANCELLED, "Cancelled")]

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="requests")
    crop = models.ForeignKey(Crop, on_delete=models.PROTECT, related_name="requests")
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2, validators=POSITIVE)
    max_price_per_kg = models.DecimalField(max_digits=8, decimal_places=2, validators=POSITIVE)
    district = models.CharField(max_length=100, blank=True)
    needed_by = models.DateField()
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.quantity_kg}kg {self.crop} <= {self.max_price_per_kg}"

    def ordered_kg(self) -> Decimal:
        live = self.orders.exclude(status__in=[Order.REJECTED, Order.CANCELLED])
        return sum((o.quantity_kg for o in live), Decimal("0"))

    def refresh_status(self):
        """Fulfilled once live orders cover the request; reopened if orders fall away."""
        if self.status == self.CANCELLED:
            return
        new = self.FULFILLED if self.ordered_kg() >= self.quantity_kg else self.OPEN
        if new != self.status:
            self.status = new
            self.save(update_fields=["status"])


class Order(models.Model):
    PENDING, ACCEPTED, REJECTED, CANCELLED, COMPLETED = "pending", "accepted", "rejected", "cancelled", "completed"
    STATUSES = [(s, s.title()) for s in (PENDING, ACCEPTED, REJECTED, CANCELLED, COMPLETED)]

    listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name="orders")
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    request = models.ForeignKey(BuyRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2, validators=POSITIVE)
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2)  # snapshot: later listing edits cannot change it
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def total(self) -> Decimal:
        return (self.quantity_kg * self.price_per_kg).quantize(Decimal("0.01"))

    def __str__(self):
        return f"Order {self.pk}: {self.quantity_kg}kg ({self.status})"
