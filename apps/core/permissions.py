"""The permission catalogue.

One flat registry of permission codenames, grouped for display. Modules add
their own entries here as they are built — the point of this step is the
*mechanism*, not a guess at every role a customer might want, so only the
permissions that correspond to screens that actually exist are defined.

Codenames are ``<app>.<action>`` strings stored on ``Role.permissions``. They
are deliberately plain strings rather than Django's ``auth.Permission`` rows:
permissions here are per-tenant configuration, not global database objects, and
they must not be confused with staff access to the back office.

A tenant owner (``Membership.is_owner``) implicitly holds every permission —
see ``apps.accounts.permissions.has_permission`` for why that matters.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Permission:
    codename: str
    label: str
    description: str
    group: str


# --- the catalogue -----------------------------------------------------------

MANAGE_STRUCTURE = "tenancy.manage_structure"
MANAGE_ORGANIZATION = "tenancy.manage_organization"
MANAGE_MEMBERS = "accounts.manage_members"
MANAGE_ROLES = "accounts.manage_roles"

PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        codename=MANAGE_STRUCTURE,
        label=_("Manage organisation structure"),
        description=_("Create, edit and archive companies, branches and departments."),
        group=_("Organisation"),
    ),
    Permission(
        codename=MANAGE_ORGANIZATION,
        label=_("Manage organisation settings"),
        description=_("Change the organisation name, timezone and default language."),
        group=_("Organisation"),
    ),
    Permission(
        codename=MANAGE_MEMBERS,
        label=_("Manage members"),
        description=_("Invite people and change who has access to this organisation."),
        group=_("People"),
    ),
    Permission(
        codename=MANAGE_ROLES,
        label=_("Manage roles"),
        description=_("Create roles and choose what each role is allowed to do."),
        group=_("People"),
    ),
)

ALL_CODENAMES: frozenset[str] = frozenset(p.codename for p in PERMISSIONS)


def grouped_permissions() -> dict[str, list[Permission]]:
    """Permissions bucketed by group, for rendering the role editor."""
    groups: dict[str, list[Permission]] = {}
    for permission in PERMISSIONS:
        groups.setdefault(str(permission.group), []).append(permission)
    return groups


def clean_codenames(codenames) -> list[str]:
    """Keep only codenames this build knows about, in catalogue order.

    Roles are stored as JSON, so a stale or hand-edited value could otherwise
    grant a permission that no longer exists — or persist one that was renamed.
    """
    selected = set(codenames or ())
    return [p.codename for p in PERMISSIONS if p.codename in selected]
