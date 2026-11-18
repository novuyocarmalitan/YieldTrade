from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("crops", views.CropViewSet, basename="crop")
router.register("listings", views.ListingViewSet, basename="listing")
router.register("requests", views.BuyRequestViewSet, basename="request")
router.register("orders", views.OrderViewSet, basename="order")

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/login/", views.LoginView.as_view()),
    path("auth/me/", views.MeView.as_view()),
    path("", include(router.urls)),
]
