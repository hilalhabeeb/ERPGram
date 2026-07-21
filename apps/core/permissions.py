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

from apps.core.domains import MANPOWER, applies_to


@dataclass(frozen=True)
class Permission:
    codename: str
    label: str
    description: str
    group: str
    # Domains this permission belongs to; None means every domain. A tenant
    # never sees permissions for an industry it is not in.
    domains: tuple[str, ...] | None = None


# --- the catalogue -----------------------------------------------------------

MANAGE_STRUCTURE = "tenancy.manage_structure"
MANAGE_ORGANIZATION = "tenancy.manage_organization"
MANAGE_MEMBERS = "accounts.manage_members"
MANAGE_ROLES = "accounts.manage_roles"

# manpower domain
MANAGE_WORKERS = "manpower.manage_workers"
MANAGE_SPONSORS = "manpower.manage_sponsors"
MANAGE_MANPOWER_SETUP = "manpower.manage_setup"
MANAGE_PLACEMENTS = "manpower.manage_placements"

# billing / accounting
MANAGE_INVOICES = "billing.manage_invoices"
RECORD_PAYMENTS = "billing.record_payments"
MANAGE_BILLING_SETUP = "billing.manage_setup"

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
    # --- manpower domain ---
    Permission(
        codename=MANAGE_WORKERS,
        label=_("Manage workers"),
        description=_("Add and update worker profiles, documents and availability."),
        group=_("Manpower"),
        domains=(MANPOWER,),
    ),
    Permission(
        codename=MANAGE_SPONSORS,
        label=_("Manage sponsors"),
        description=_("Add and update the households and companies that hire workers."),
        group=_("Manpower"),
        domains=(MANPOWER,),
    ),
    Permission(
        codename=MANAGE_PLACEMENTS,
        label=_("Manage placements"),
        description=_("Place workers with sponsors, price the contract and issue invoices."),
        group=_("Manpower"),
        domains=(MANPOWER,),
    ),
    Permission(
        codename=MANAGE_INVOICES,
        label=_("Manage invoices"),
        description=_("Create, price, issue and credit invoices."),
        group=_("Accounting"),
        domains=(MANPOWER,),
    ),
    Permission(
        codename=RECORD_PAYMENTS,
        label=_("Record payments"),
        description=_("Enter money received against an invoice."),
        group=_("Accounting"),
        domains=(MANPOWER,),
    ),
    Permission(
        codename=MANAGE_BILLING_SETUP,
        label=_("Manage services and terms"),
        description=_("Edit the price list of services and the terms templates."),
        group=_("Accounting"),
        domains=(MANPOWER,),
    ),
    Permission(
        codename=MANAGE_MANPOWER_SETUP,
        label=_("Manage manpower setup"),
        description=_("Edit occupations, skills, agents, accommodation and document types."),
        group=_("Manpower"),
        domains=(MANPOWER,),
    ),
)

ALL_CODENAMES: frozenset[str] = frozenset(p.codename for p in PERMISSIONS)


def permissions_for_domain(tenant_domain: str | None) -> tuple[Permission, ...]:
    """The catalogue as it applies to one tenant's industry."""
    return tuple(p for p in PERMISSIONS if applies_to(p.domains, tenant_domain))


def codenames_for_domain(tenant_domain: str | None) -> frozenset[str]:
    return frozenset(p.codename for p in permissions_for_domain(tenant_domain))


def grouped_permissions(tenant_domain: str | None = None) -> dict[str, list[Permission]]:
    """Permissions bucketed by group, for rendering the role editor."""
    groups: dict[str, list[Permission]] = {}
    for permission in permissions_for_domain(tenant_domain):
        groups.setdefault(str(permission.group), []).append(permission)
    return groups


def clean_codenames(codenames, tenant_domain: str | None = None) -> list[str]:
    """Keep only codenames this build knows about, in catalogue order.

    Roles are stored as JSON, so a stale or hand-edited value could otherwise
    grant a permission that no longer exists — or persist one that was renamed.
    Passing a domain also drops permissions belonging to another industry.
    """
    selected = set(codenames or ())
    catalogue = permissions_for_domain(tenant_domain) if tenant_domain else PERMISSIONS
    return [p.codename for p in catalogue if p.codename in selected]
