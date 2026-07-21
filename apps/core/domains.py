"""Business domains (industries).

A tenant picks its domain when it signs up, and the domain decides which parts
of the product exist for that tenant at all. This is a different axis from
permissions:

* **domain**     — does this feature exist for this customer?
* **permission** — may *this user* use a feature their tenant has?

Nav entries, permissions and modules all declare the domains they belong to, so
adding an industry means adding a ``Domain`` here plus an app that tags its own
entries — not editing the shell.

Only ``manpower`` is implemented today. ``general`` exists so a tenant that is
not in a supported industry still gets the shared core (organisation structure,
users, roles) rather than an empty product.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

GENERAL = "general"
MANPOWER = "manpower"


@dataclass(frozen=True)
class Domain:
    code: str
    label: str
    description: str


DOMAINS: tuple[Domain, ...] = (
    Domain(
        code=MANPOWER,
        label=_("Domestic worker supply"),
        description=_(
            "Recruitment agencies supplying housemaids, drivers, cooks and "
            "carers to household sponsors."
        ),
    ),
    Domain(
        code=GENERAL,
        label=_("General business"),
        description=_("Organisation structure, people and roles only, with no industry module."),
    ),
)

DOMAIN_CODES: frozenset[str] = frozenset(d.code for d in DOMAINS)


def domain_choices() -> list[tuple[str, str]]:
    return [(d.code, d.label) for d in DOMAINS]


def get_domain(code: str) -> Domain | None:
    return next((d for d in DOMAINS if d.code == code), None)


def applies_to(domains: tuple[str, ...] | None, tenant_domain: str | None) -> bool:
    """True when an entry tagged ``domains`` is visible to ``tenant_domain``.

    ``None`` means "every domain" — that is how the shared core (dashboard,
    settings, organisation structure) stays visible whatever the industry.
    """
    if domains is None:
        return True
    return tenant_domain in domains
