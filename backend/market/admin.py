from django.contrib import admin

from .models import BuyRequest, Crop, Listing, Order, Profile

for model in (Profile, Crop, Listing, BuyRequest, Order):
    admin.site.register(model)
