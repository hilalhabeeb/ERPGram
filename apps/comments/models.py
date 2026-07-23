"""A comment thread that attaches to any document.

One generic model, keyed by (content_type, object_id), the way Frappe hangs its
Comment doctype off (reference_doctype, reference_name). Add a thread to a new
document type by dropping ``{% comment_thread obj %}`` on its page — no schema
change, no per-document table.

Tenant-scoped like every business table, so RLS isolates one agency's notes from
another's even though the model is shared.
"""

from __future__ import annotations

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantScopedModel


class Comment(TenantScopedModel):
    content_type = models.ForeignKey(
        ContentType,
        verbose_name=_("document type"),
        on_delete=models.CASCADE,
        related_name="+",
    )
    # UUID because every commentable document uses a UUID primary key.
    object_id = models.UUIDField(_("document id"))
    target = GenericForeignKey("content_type", "object_id")

    body = models.TextField(_("comment"))

    class Meta:
        verbose_name = _("comment")
        verbose_name_plural = _("comments")
        ordering = ["created_at"]
        base_manager_name = "all_tenants"
        indexes = [
            models.Index(fields=["tenant", "content_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return self.body[:50]
