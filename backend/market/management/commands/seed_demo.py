from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from market.models import BuyRequest, Crop, Listing, Profile

CROPS = ["Maize", "Sorghum", "Pearl Millet", "Groundnuts", "Cowpeas", "Sugar Beans", "Soybeans", "Sunflower", "Tomatoes", "Onions"]
DEMO_PASSWORD = "demo-pass-1234"  # development only

FARMERS = [
    ("farmer_tendai", "Gwanda", [("Maize", 800, "0.34"), ("Sorghum", 300, "0.40"), ("Groundnuts", 150, "1.10")]),
    ("farmer_rudo", "Tsholotsho", [("Maize", 400, "0.30"), ("Cowpeas", 120, "0.95")]),
    ("farmer_sipho", "Umguza", [("Maize", 1500, "0.38"), ("Sugar Beans", 200, "1.30")]),
]
BUYERS = [
    ("buyer_mill", "Bulawayo", [("Maize", 1200, "0.36")]),
    ("buyer_grocer", "Bulawayo", [("Groundnuts", 100, "1.20"), ("Sugar Beans", 150, "1.25")]),
]


class Command(BaseCommand):
    help = "Load demo crops, users, listings and buy requests (development only)."

    def handle(self, *args, **opts):
        User = get_user_model()
        crops = {n: Crop.objects.get_or_create(name=n)[0] for n in CROPS}
        soon = date.today() + timedelta(days=14)

        def user(name, role, district):
            u, created = User.objects.get_or_create(username=name)
            if created:
                u.set_password(DEMO_PASSWORD)
                u.save()
            Profile.objects.get_or_create(user=u, defaults={"role": role, "district": district})
            return u

        for name, district, items in FARMERS:
            u = user(name, Profile.FARMER, district)
            if not u.listings.exists():
                for crop, qty, price in items:
                    Listing.objects.create(farmer=u, crop=crops[crop], quantity_kg=qty, price_per_kg=Decimal(price),
                                           district=district, available_from=date.today())
        for name, district, items in BUYERS:
            u = user(name, Profile.BUYER, district)
            if not u.requests.exists():
                for crop, qty, price in items:
                    BuyRequest.objects.create(buyer=u, crop=crops[crop], quantity_kg=qty, max_price_per_kg=Decimal(price),
                                              district=district, needed_by=soon)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(CROPS)} crops, {len(FARMERS)} farmers, {len(BUYERS)} buyers. "
            f"Demo logins use the password {DEMO_PASSWORD!r} (development only)."))
