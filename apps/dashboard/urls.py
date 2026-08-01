from django.urls import path

from .views import (
    DashboardClinicalView,
    DashboardFinancialView,
    DashboardInventoryView,
    DashboardOperationsView,
    DashboardOverviewView,
    DashboardSummaryView,
    RecentEncountersView,
)

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("v2/overview/", DashboardOverviewView.as_view(), name="dashboard-v2-overview"),
    path("v2/operations/", DashboardOperationsView.as_view(), name="dashboard-v2-operations"),
    path("v2/financial/", DashboardFinancialView.as_view(), name="dashboard-v2-financial"),
    path("v2/clinical/", DashboardClinicalView.as_view(), name="dashboard-v2-clinical"),
    path("v2/inventory/", DashboardInventoryView.as_view(), name="dashboard-v2-inventory"),
    path("recent-encounters/", RecentEncountersView.as_view(), name="dashboard-recent-encounters"),
]
