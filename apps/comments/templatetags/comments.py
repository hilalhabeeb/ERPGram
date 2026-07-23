"""``{% comment_thread obj %}`` — drop a comment thread onto any document page."""

from __future__ import annotations

from django import template

from apps.comments import services

register = template.Library()


@register.inclusion_tag("comments/_thread.html", takes_context=True)
def comment_thread(context, obj):
    """Render the comment thread for ``obj`` (a commentable document)."""
    return services.thread_context(context["request"], obj)
