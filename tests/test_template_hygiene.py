"""Static checks on templates that reviewing by eye keeps missing.

The multi-line comment rule has now bitten twice — a `{# ... #}` spanning two
lines is not a comment in Django, it is text, and it renders to the page. Both
times it shipped and was only caught in a screenshot. This makes it a test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_DIRS = [ROOT / "templates", *(ROOT / "apps").glob("*/templates")]


def _templates() -> list[Path]:
    found: list[Path] = []
    for directory in TEMPLATE_DIRS:
        found.extend(directory.glob("**/*.html"))
    return found


def test_templates_were_found():
    """Guard against the scanner silently matching nothing."""
    assert len(_templates()) > 20


@pytest.mark.parametrize("template", _templates(), ids=lambda p: p.name)
def test_no_multiline_django_comments(template: Path):
    """`{# #}` must open and close on one line; otherwise use {% comment %}."""
    offenders = [
        (number, line.strip())
        for number, line in enumerate(template.read_text(encoding="utf-8").splitlines(), 1)
        if "{#" in line and "#}" not in line
    ]
    assert not offenders, (
        f"{template.relative_to(ROOT)} has a `{{#` comment that does not close on the "
        f"same line — Django renders it as text. Use {{% comment %}} instead: {offenders}"
    )


@pytest.mark.parametrize("template", _templates(), ids=lambda p: p.name)
def test_no_physical_direction_utilities(template: Path):
    """RTL is non-negotiable, so spacing must use logical properties.

    ml-/mr-/pl-/pr-/left-/right- do not flip in Arabic; ms-/me-/ps-/pe-/start-/
    end- do. Matching is on class attributes only, so prose is unaffected.
    """
    text = template.read_text(encoding="utf-8")
    physical = re.compile(r'class="[^"]*?(?<![\w-])(?:[mp][lr]|left|right)-[\w./\[\]]+', re.S)
    matches = physical.findall(text)
    assert not matches, (
        f"{template.relative_to(ROOT)} uses a physical direction utility; "
        f"use the logical equivalent (ms-/me-/ps-/pe-/start-/end-) so RTL mirrors."
    )
