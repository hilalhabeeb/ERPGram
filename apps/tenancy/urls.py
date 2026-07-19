"""Organisation-structure URLs (namespace ``tenancy``), inside the i18n patterns."""

from __future__ import annotations

from django.urls import path

from apps.tenancy import views

app_name = "tenancy"

urlpatterns = [
    path("companies/", views.company_list, name="company_list"),
    path("companies/new/", views.company_create, name="company_create"),
    path("companies/<uuid:pk>/", views.company_detail, name="company_detail"),
    path("companies/<uuid:pk>/edit/", views.company_update, name="company_update"),
    path("companies/<uuid:pk>/archive/", views.company_archive, name="company_archive"),
    # branches
    path("companies/<uuid:pk>/branches/new/", views.branch_create, name="branch_create"),
    path(
        "companies/<uuid:pk>/branches/<uuid:branch_pk>/",
        views.branch_detail,
        name="branch_detail",
    ),
    path(
        "companies/<uuid:pk>/branches/<uuid:branch_pk>/edit/",
        views.branch_update,
        name="branch_update",
    ),
    path(
        "companies/<uuid:pk>/branches/<uuid:branch_pk>/archive/",
        views.branch_archive,
        name="branch_archive",
    ),
    # departments
    path(
        "companies/<uuid:pk>/branches/<uuid:branch_pk>/departments/new/",
        views.department_create,
        name="department_create",
    ),
    path(
        "companies/<uuid:pk>/branches/<uuid:branch_pk>/departments/<uuid:department_pk>/edit/",
        views.department_update,
        name="department_update",
    ),
    path(
        "companies/<uuid:pk>/branches/<uuid:branch_pk>/departments/<uuid:department_pk>/archive/",
        views.department_archive,
        name="department_archive",
    ),
]
