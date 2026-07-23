"""Add and remove comments. Anyone in the tenant who can open a document can
comment on it; only the author can delete their own note."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.comments import services
from apps.comments.models import Comment


def _back(request: HttpRequest) -> HttpResponse:
    """Return to the document the comment lives on, safely."""
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(nxt)
    return redirect("ui:dashboard")


@require_POST
def add(request: HttpRequest, content_type_id: int, object_id) -> HttpResponse:
    content_type, obj = services.resolve_target(request, content_type_id, object_id)
    body = request.POST.get("body", "").strip()
    if body:
        services.add_comment(
            tenant=request.tenant,
            user=request.user,
            content_type=content_type,
            object_id=obj.pk,
            body=body,
        )
    if request.htmx:
        return render(request, "comments/_thread.html", services.thread_context(request, obj))
    return _back(request)


@require_POST
def delete(request: HttpRequest, pk) -> HttpResponse:
    comment = get_object_or_404(Comment.objects, pk=pk)
    if comment.created_by_id != request.user.id:
        raise PermissionDenied("only the author can delete a comment")
    target = comment.target  # resolve before the row is gone
    comment.delete()
    if request.htmx and target is not None:
        return render(request, "comments/_thread.html", services.thread_context(request, target))
    return _back(request)
