"""UI template tags: the ``{% icon %}`` tag and small template helpers."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)
register = template.Library()

_ICON_DIR = Path(__file__).resolve().parent.parent / "icons"
_SVG_OPEN_RE = re.compile(r"<svg\b", re.IGNORECASE)


@lru_cache(maxsize=256)
def _load_icon(name: str) -> str:
    path = _ICON_DIR / f"{name}.svg"
    if not path.exists():
        # Never fail a render over an icon, but never fail *silently* either: an
        # invisible placeholder once shipped a blank square to the dashboard.
        logger.warning("icon %r not found in %s", name, _ICON_DIR)
        if settings.DEBUG:
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                '<rect x="1" y="1" width="22" height="22" rx="4" fill="none" '
                'stroke="#DC2626" stroke-width="2" stroke-dasharray="3 2"/></svg>'
            )
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"></svg>'
    return path.read_text(encoding="utf-8").strip()


def available_icons() -> set[str]:
    """Names of every vendored icon — used by the template-audit test."""
    return {p.stem for p in _ICON_DIR.glob("*.svg")}


@register.simple_tag
def icon(name: str, css_class: str = "w-5 h-5", label: str | None = None) -> str:
    """Inline a vendored Lucide SVG with a Tailwind class and a11y attributes.

    Usage: ``{% icon "users" css_class="w-5 h-5" label="Team" %}``. Icons use
    ``currentColor`` so colour follows the surrounding text token.
    """
    svg = _load_icon(name)
    attrs = f'class="{css_class}" '
    if label:
        attrs += f'role="img" aria-label="{label}" '
    else:
        attrs += 'aria-hidden="true" focusable="false" '
    svg = _SVG_OPEN_RE.sub(f"<svg {attrs.strip()}", svg, count=1)
    return mark_safe(svg)  # noqa: S308 — trusted, vendored local files only


@register.filter
def get_item(mapping: dict, key: str):
    """Dict lookup by variable key inside templates."""
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return None


@register.simple_tag(takes_context=True)
def query_string(context, **updates) -> str:
    """Return the current query string with ``updates`` applied — for pager/sort links."""
    request = context["request"]
    params = request.GET.copy()
    for key, value in updates.items():
        params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""
