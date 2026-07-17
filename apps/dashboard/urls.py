from django.urls import path

from .views import DashboardSummaryView, RecentEncountersView

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("recent-encounters/", RecentEncountersView.as_view(), name="dashboard-recent-encounters"),
]
