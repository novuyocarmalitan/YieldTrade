from django.core.management.base import BaseCommand

from market.models import Crop

CROPS = ["Maize", "Sorghum", "Pearl Millet", "Groundnuts", "Cowpeas", "Sugar Beans", "Soybeans", "Sunflower", "Tomatoes", "Onions"]


class Command(BaseCommand):
    help = "Load the crop catalogue. Safe to run on every deploy (it only adds what is missing)."

    def handle(self, *args, **opts):
        added = sum(Crop.objects.get_or_create(name=n)[1] for n in CROPS)
        self.stdout.write(self.style.SUCCESS(f"Crop catalogue ready ({added} added, {Crop.objects.count()} total)."))
