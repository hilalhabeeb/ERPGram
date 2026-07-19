"""App-shell URLs (namespace ``ui``), served inside the i18n URL patterns."""

from __future__ import annotations

from django.urls import path

from apps.ui import views

app_name = "ui"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("settings/profile/", views.settings_profile, name="settings_profile"),
    path("settings/organization/", views.settings_organization, name="settings_organization"),
    path("settings/users/", views.settings_users, name="settings_users"),
]
