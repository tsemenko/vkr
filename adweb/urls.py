from django.contrib import admin
from django.urls import include, path

from accounts import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/logout/", views.logout_view, name="logout"),
    path("accounts/change-password/", views.change_initial_password, name="change_initial_password"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", views.index, name="index"),
    path("create/", views.create_account, name="create_account"),
    path("logs/", views.logs_view, name="logs"),
    path("logs/errors/", views.error_logs_view, name="error_logs"),
    path("logs/system/", views.system_logs_view, name="system_logs"),
    path("system/", views.system_management_view, name="system_management"),
    path("ad-analytics/", views.ad_analytics_view, name="ad_analytics"),
    path("ad-analytics/fragment/", views.ad_analytics_fragment_view, name="ad_analytics_fragment"),
    path("ad-analytics/refresh/", views.ad_analytics_refresh_view, name="ad_analytics_refresh"),
    path("ad-analytics/unlock/", views.unlock_user_view, name="ad_analytics_unlock"),
]
