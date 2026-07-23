"""Comment rules. Views orchestrate; these decide what may be commented on."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.http import Http404, HttpRequest
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404

from apps.comments.models import Comment

# The document types that carry a comment thread. A user could otherwise post
# the (content_type, object_id) of any model in the project — this allowlist is
# what stops a comment being hung off, say, a Role or a LoginAttempt. Add a pair
# here (and the template tag on its page) to make a new document commentable.
COMMENTABLE: set[tuple[str, str]] = {
    ("billing", "invoice"),
    ("manpower", "placement"),
    ("manpower", "worker"),
    ("manpower", "sponsor"),
}


def resolve_target(request: HttpRequest, content_type_id, object_id):
    """Return ``(content_type, object)`` for a commentable, tenant-owned document.

    404 (not 403) if the type is not commentable or the object is not this
    tenant's — the tenant-scoped manager only yields rows the caller owns, so a
    foreign or made-up id simply is not found, and we never confirm it exists.
    """
    content_type = get_object_or_404(ContentType, pk=content_type_id)
    if (content_type.app_label, content_type.model) not in COMMENTABLE:
        raise Http404("not a commentable document")
    model = content_type.model_class()
    if model is None:
        raise Http404("unknown document type")
    # ``objects`` is tenant-filtered, so this is the ownership check.
    obj = get_object_or_404(model.objects, pk=object_id)
    return content_type, obj


def comments_for(tenant, content_type, object_id) -> QuerySet[Comment]:
    return (
        Comment.objects.filter(tenant=tenant, content_type=content_type, object_id=object_id)
        .select_related("created_by")
        .order_by("created_at")
    )


def add_comment(*, tenant, user, content_type, object_id, body: str) -> Comment:
    return Comment.objects.create(
        tenant=tenant,
        content_type=content_type,
        object_id=object_id,
        body=body,
        created_by=user,
        updated_by=user,
    )


def thread_context(request: HttpRequest, obj) -> dict:
    """Everything the thread partial needs, shared by the tag and the add/delete
    views so an HTMX swap re-renders exactly what the inclusion tag first drew."""
    content_type = ContentType.objects.get_for_model(obj)
    return {
        "request": request,
        # The tag renders in an isolated context, so csrf_token must be handed in
        # explicitly for {% csrf_token %} to work inside the partial.
        "csrf_token": get_token(request),
        "content_type_id": content_type.id,
        "object_id": obj.pk,
        "comments": comments_for(request.tenant, content_type, obj.pk),
        "current_user": request.user,
    }
