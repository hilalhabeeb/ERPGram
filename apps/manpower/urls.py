"""Manpower URLs (namespace ``manpower``), served inside the i18n patterns."""

from __future__ import annotations

from django.urls import path

from apps.manpower import views

app_name = "manpower"

urlpatterns = [
    # workers
    path("workers/", views.worker_list, name="worker_list"),
    path("workers/new/", views.worker_form, name="worker_create"),
    path("workers/<uuid:pk>/", views.worker_detail, name="worker_detail"),
    path("workers/<uuid:pk>/edit/", views.worker_form, name="worker_update"),
    path("workers/<uuid:pk>/archive/", views.worker_archive, name="worker_archive"),
    # sponsors
    path("sponsors/", views.sponsor_list, name="sponsor_list"),
    path("sponsors/new/", views.sponsor_create, name="sponsor_create"),
    path("sponsors/<uuid:pk>/archive/", views.sponsor_archive, name="sponsor_archive"),
    # setup
    path("manpower-setup/", views.setup, name="setup"),
    path("manpower-setup/<slug:section>/", views.setup, name="setup_section"),
]
