"""Comment URLs (namespace ``comments``), inside the i18n patterns."""

from __future__ import annotations

from django.urls import path

from apps.comments import views

app_name = "comments"

urlpatterns = [
    path("comments/<int:content_type_id>/<uuid:object_id>/add/", views.add, name="add"),
    path("comments/<uuid:pk>/delete/", views.delete, name="delete"),
]
