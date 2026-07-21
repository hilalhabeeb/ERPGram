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
    path("workers/<uuid:pk>/cv/", views.worker_cv, name="worker_cv"),
    # placements (the agreement + invoice)
    path("placements/", views.placement_list, name="placement_list"),
    path("placements/new/", views.placement_create, name="placement_create"),
    path("placements/<uuid:pk>/", views.placement_detail, name="placement_detail"),
    path("placements/<uuid:pk>/print/", views.placement_print, name="placement_print"),
    path("placements/<uuid:pk>/status/", views.placement_status, name="placement_status"),
    path(
        "placements/<uuid:pk>/save/<slug:section>/",
        views.placement_update,
        name="placement_update",
    ),
    path(
        "placements/<uuid:pk>/charges/add/",
        views.placement_charge_add,
        name="placement_charge_add",
    ),
    path(
        "placements/<uuid:pk>/charges/<uuid:charge_pk>/delete/",
        views.placement_charge_delete,
        name="placement_charge_delete",
    ),
    # sponsors
    path("sponsors/", views.sponsor_list, name="sponsor_list"),
    path("sponsors/new/", views.sponsor_create, name="sponsor_create"),
    path("sponsors/<uuid:pk>/archive/", views.sponsor_archive, name="sponsor_archive"),
    # setup
    path("manpower-setup/", views.setup, name="setup"),
    path("manpower-setup/<slug:section>/", views.setup, name="setup_section"),
]
