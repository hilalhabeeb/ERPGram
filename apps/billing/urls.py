"""Accounting URLs (namespace ``billing``), inside the i18n patterns."""

from __future__ import annotations

from django.urls import path

from apps.billing import views

app_name = "billing"

urlpatterns = [
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/new/", views.invoice_create, name="invoice_create"),
    path("invoices/receivables/", views.receivables, name="receivables"),
    path("invoices/<uuid:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<uuid:pk>/print/", views.invoice_print, name="invoice_print"),
    path("invoices/<uuid:pk>/issue/", views.invoice_issue, name="invoice_issue"),
    path("invoices/<uuid:pk>/cancel/", views.invoice_cancel, name="invoice_cancel"),
    path("invoices/<uuid:pk>/credit/", views.invoice_credit, name="invoice_credit"),
    path("invoices/<uuid:pk>/save/<slug:section>/", views.invoice_update, name="invoice_update"),
    path("invoices/<uuid:pk>/lines/save/", views.invoice_lines_save, name="invoice_lines_save"),
    path("invoices/<uuid:pk>/payments/add/", views.payment_add, name="payment_add"),
    path(
        "sponsors/<uuid:sponsor_pk>/statement/",
        views.sponsor_statement,
        name="sponsor_statement",
    ),
    path("billing-setup/", views.setup, name="setup"),
    path("billing-setup/<slug:section>/", views.setup, name="setup_section"),
]
