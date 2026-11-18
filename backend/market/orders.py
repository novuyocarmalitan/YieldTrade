"""Order lifecycle. Stock is reserved when an order is placed and released if it falls through.

    pending --accept--> accepted --complete--> completed
       |  \\--reject (farmer)--> rejected      (stock released)
       \\----cancel (buyer)----> cancelled     (stock released)

Every change runs in one transaction with the listing row locked, so two buyers cannot reserve
the same kilograms.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .models import BuyRequest, Listing, Order


def place_order(buyer, listing_id: int, quantity: Decimal, request_id: int | None = None) -> Order:
    with transaction.atomic():
        try:
            listing = Listing.objects.select_for_update().select_related("crop").get(pk=listing_id)
        except Listing.DoesNotExist:
            raise NotFound("Listing not found.")
        if not listing.is_open:
            raise ValidationError({"listing": "This listing is no longer open."})
        if listing.farmer_id == buyer.id:
            raise ValidationError({"listing": "You cannot buy your own produce."})
        if quantity > listing.quantity_kg:
            raise ValidationError({"quantity_kg": f"Only {listing.quantity_kg} kg is available."})

        buy_request = None
        if request_id is not None:
            buy_request = BuyRequest.objects.select_for_update().filter(pk=request_id, buyer=buyer).first()
            if buy_request is None:
                raise ValidationError({"request": "That buy request is not yours."})
            if buy_request.crop_id != listing.crop_id:
                raise ValidationError({"request": "The request is for a different crop."})
            if buy_request.status == BuyRequest.CANCELLED:
                raise ValidationError({"request": "That buy request was cancelled."})

        listing.quantity_kg -= quantity
        if listing.quantity_kg <= 0:
            listing.status = Listing.CLOSED
        listing.save(update_fields=["quantity_kg", "status"])

        order = Order.objects.create(
            listing=listing, buyer=buyer, request=buy_request, quantity_kg=quantity, price_per_kg=listing.price_per_kg
        )
        if buy_request:
            buy_request.refresh_status()
        return order


def _release(order: Order) -> None:
    listing = Listing.objects.select_for_update().get(pk=order.listing_id)
    was_sold_out = listing.quantity_kg <= 0
    listing.quantity_kg += order.quantity_kg
    if was_sold_out and listing.status == Listing.CLOSED:
        listing.status = Listing.OPEN  # only a sell-out reopens; a listing the farmer closed by hand stays closed
    listing.save(update_fields=["quantity_kg", "status"])


def transition(order_id: int, actor, action: str) -> Order:
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().select_related("listing").get(pk=order_id)
        except Order.DoesNotExist:
            raise NotFound("Order not found.")
        is_farmer = order.listing.farmer_id == actor.id
        is_buyer = order.buyer_id == actor.id
        if not (is_farmer or is_buyer):
            raise NotFound("Order not found.")  # do not reveal other people's orders

        rules = {
            "accept": (is_farmer, Order.PENDING, Order.ACCEPTED, False),
            "reject": (is_farmer, Order.PENDING, Order.REJECTED, True),
            "cancel": (is_buyer, Order.PENDING, Order.CANCELLED, True),
            "complete": (is_farmer, Order.ACCEPTED, Order.COMPLETED, False),
        }
        if action not in rules:
            raise ValidationError({"action": "Unknown action."})
        allowed, from_status, to_status, releases = rules[action]
        if not allowed:
            who = "the farmer" if action in ("accept", "reject", "complete") else "the buyer"
            raise PermissionDenied(f"Only {who} can {action} this order.")
        if order.status != from_status:
            raise ValidationError({"status": f"A {order.status} order cannot be {action}ed."})

        if releases:
            _release(order)
        order.status = to_status
        order.save(update_fields=["status", "updated_at"])
        if order.request_id:
            order.request.refresh_status()
        return order
