from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TherapyViewSet, PanchakarmaOrderViewSet, PanchakarmaSessionViewSet

router = DefaultRouter()
router.register(r'therapies', TherapyViewSet)
router.register(r'orders', PanchakarmaOrderViewSet)
router.register(r'sessions', PanchakarmaSessionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
