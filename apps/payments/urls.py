from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    PaymentCategoryViewSet,
    TransactionViewSet,
    AccountingPeriodViewSet,
    BillPaymentViewSet,
)

router = DefaultRouter()
router.register(r'categories',        PaymentCategoryViewSet, basename='payment-categories')
router.register(r'transactions',      TransactionViewSet,     basename='transactions')
router.register(r'accounting-periods',AccountingPeriodViewSet,basename='accounting-periods')
router.register(r'bill-payments',     BillPaymentViewSet,     basename='bill-payments')

urlpatterns = [
    path('', include(router.urls)),
]
