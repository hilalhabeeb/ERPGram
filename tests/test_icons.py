"""Guard: every icon referenced anywhere must actually be vendored.

A missing icon used to render an invisible placeholder, which is how a blank
square shipped to the dashboard. This test makes that a build failure instead.
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.ui.templatetags.ui import available_icons

ROOT = Path(__file__).resolve().parent.parent

# {% icon "name" ... %} in templates
_TEMPLATE_ICON_RE = re.compile(r"""\{%\s*icon\s+["']([a-z0-9-]+)["']""")
# icon="name" / empty_icon="name" passed through {% include ... with %}
_INCLUDE_ICON_RE = re.compile(r"""\b(?:empty_)?icon=["']([a-z0-9-]+)["']""")
# Python passes icon names by keyword (icon="name") precisely so they are greppable.
_PY_ICON_RE = re.compile(r"""\bicon=["']([a-z0-9-]+)["']""")


def _referenced_icons() -> dict[str, set[str]]:
    """Map icon name -> set of files referencing it."""
    found: dict[str, set[str]] = {}

    def record(name: str, path: Path) -> None:
        found.setdefault(name, set()).add(str(path.relative_to(ROOT)))

    for path in ROOT.glob("**/templates/**/*.html"):
        text = path.read_text(encoding="utf-8")
        for pattern in (_TEMPLATE_ICON_RE, _INCLUDE_ICON_RE):
            for match in pattern.finditer(text):
                record(match.group(1), path)

    for path in (ROOT / "apps").glob("**/*.py"):
        if "migrations" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in _PY_ICON_RE.finditer(text):
            record(match.group(1), path)

    return found


def test_every_referenced_icon_is_vendored():
    referenced = _referenced_icons()
    assert referenced, "icon scanner found nothing — the patterns are probably wrong"

    vendored = available_icons()
    missing = {name: sorted(files) for name, files in referenced.items() if name not in vendored}

    assert not missing, "icons referenced but not vendored in apps/ui/icons/: " + "; ".join(
        f"{name} (used in {', '.join(files)})" for name, files in sorted(missing.items())
    )
