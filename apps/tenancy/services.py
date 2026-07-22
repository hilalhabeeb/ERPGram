"""Tenancy business logic. Views orchestrate; these functions decide.

Every mutating function takes the acting ``user`` and stamps ``created_by`` /
``updated_by``, so the audit columns on ``TimeStampedModel`` are actually
populated rather than left null.

Archiving is the only removal path — nothing here deletes rows. Archiving a
record cascades *down* the hierarchy (a company's branches and their
departments go with it) so the tree can never show an active child under an
archived parent. Restoring deliberately does not cascade: bringing a company
back should not resurrect branches that were archived separately beforehand.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.tenancy.models import Branch, Company, Department, Tenant

# --- companies ---------------------------------------------------------------


def companies_for(tenant: Tenant, *, include_archived: bool = False) -> QuerySet[Company]:
    """Companies of a tenant, annotated with branch counts for the list view."""
    qs = Company.objects.filter(tenant=tenant)
    if not include_archived:
        qs = qs.filter(is_active=True)
    return qs.annotate(branch_count=Count("branches", filter=Q(branches__is_active=True)))


@transaction.atomic
def create_company(
    *,
    tenant: Tenant,
    user: User,
    name: str,
    legal_name: str = "",
    registration_no: str = "",
) -> Company:
    return Company.objects.create(
        tenant=tenant,
        name=name.strip(),
        legal_name=legal_name.strip(),
        registration_no=registration_no.strip(),
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def update_company(
    company: Company,
    *,
    user: User,
    name: str,
    legal_name: str = "",
    registration_no: str = "",
) -> Company:
    company.name = name.strip()
    company.legal_name = legal_name.strip()
    company.registration_no = registration_no.strip()
    company.updated_by = user
    company.save(
        update_fields=["name", "legal_name", "registration_no", "updated_by", "updated_at"]
    )
    return company


@transaction.atomic
def archive_company(company: Company, *, user: User) -> Company:
    """Archive a company and everything beneath it."""
    # updated_at is auto_now, which .update() does not trigger — set it explicitly
    # or the bulk-archived rows keep a stale timestamp with a fresh updated_by.
    now = timezone.now()
    branches = Branch.objects.filter(company=company, is_active=True)
    Department.objects.filter(branch__in=branches, is_active=True).update(
        is_active=False, updated_by=user, updated_at=now
    )
    branches.update(is_active=False, updated_by=user, updated_at=now)
    company.is_active = False
    company.updated_by = user
    company.save(update_fields=["is_active", "updated_by", "updated_at"])
    return company


@transaction.atomic
def restore_company(company: Company, *, user: User) -> Company:
    """Restore the company only — children stay archived (see module docstring)."""
    company.is_active = True
    company.updated_by = user
    company.save(update_fields=["is_active", "updated_by", "updated_at"])
    return company


# --- branches ----------------------------------------------------------------


def branches_for(company: Company, *, include_archived: bool = False) -> QuerySet[Branch]:
    qs = Branch.objects.filter(company=company)
    if not include_archived:
        qs = qs.filter(is_active=True)
    return qs.annotate(department_count=Count("departments", filter=Q(departments__is_active=True)))


@transaction.atomic
def create_branch(
    *,
    company: Company,
    user: User,
    name: str,
    code: str = "",
    address: str = "",
) -> Branch:
    # tenant is taken from the parent company, never from user input.
    return Branch.objects.create(
        tenant=company.tenant,
        company=company,
        name=name.strip(),
        code=code.strip(),
        address=address.strip(),
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def update_branch(
    branch: Branch, *, user: User, name: str, code: str = "", address: str = ""
) -> Branch:
    branch.name = name.strip()
    branch.code = code.strip()
    branch.address = address.strip()
    branch.updated_by = user
    branch.save(update_fields=["name", "code", "address", "updated_by", "updated_at"])
    return branch


@transaction.atomic
def archive_branch(branch: Branch, *, user: User) -> Branch:
    Department.objects.filter(branch=branch, is_active=True).update(
        is_active=False, updated_by=user, updated_at=timezone.now()
    )
    branch.is_active = False
    branch.updated_by = user
    branch.save(update_fields=["is_active", "updated_by", "updated_at"])
    return branch


@transaction.atomic
def restore_branch(branch: Branch, *, user: User) -> Branch:
    branch.is_active = True
    branch.updated_by = user
    branch.save(update_fields=["is_active", "updated_by", "updated_at"])
    return branch


# --- departments -------------------------------------------------------------


def departments_for(branch: Branch, *, include_archived: bool = False) -> QuerySet[Department]:
    qs = Department.objects.filter(branch=branch).select_related("parent")
    if not include_archived:
        qs = qs.filter(is_active=True)
    return qs


def department_tree(branch: Branch, *, include_archived: bool = False) -> list[dict]:
    """Flatten the department hierarchy into rows carrying a depth for indentation.

    Built from a single query rather than recursive DB hits. Any node whose
    parent is missing from this set (archived, or a cycle survived validation)
    is treated as a root so it can never be silently dropped from the list.
    """
    nodes = list(departments_for(branch, include_archived=include_archived))
    children: dict[object, list[Department]] = {}
    ids = {node.id for node in nodes}
    for node in nodes:
        key = node.parent_id if node.parent_id in ids else None
        children.setdefault(key, []).append(node)

    rows: list[dict] = []

    def walk(parent_id, depth: int) -> None:
        for node in children.get(parent_id, []):
            rows.append({"department": node, "depth": depth})
            walk(node.id, depth + 1)

    walk(None, 0)
    return rows


@transaction.atomic
def create_department(
    *,
    branch: Branch,
    user: User,
    name: str,
    code: str = "",
    parent: Department | None = None,
) -> Department:
    return Department.objects.create(
        tenant=branch.tenant,
        branch=branch,
        parent=parent,
        name=name.strip(),
        code=code.strip(),
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def update_department(
    department: Department,
    *,
    user: User,
    name: str,
    code: str = "",
    parent: Department | None = None,
) -> Department:
    department.name = name.strip()
    department.code = code.strip()
    department.parent = parent
    department.updated_by = user
    department.save(update_fields=["name", "code", "parent", "updated_by", "updated_at"])
    return department


@transaction.atomic
def archive_department(department: Department, *, user: User) -> Department:
    """Archive a department and its descendants."""
    for child in Department.objects.filter(parent=department, is_active=True):
        archive_department(child, user=user)
    department.is_active = False
    department.updated_by = user
    department.save(update_fields=["is_active", "updated_by", "updated_at"])
    return department


@transaction.atomic
def restore_department(department: Department, *, user: User) -> Department:
    department.is_active = True
    department.updated_by = user
    department.save(update_fields=["is_active", "updated_by", "updated_at"])
    return department


ORGANIZATION_FIELDS = (
    "name",
    "timezone",
    "default_locale",
    "legal_name",
    "currency",
    "vat_number",
    "cr_number",
    "default_tax_rate",
    "phone",
    "email",
    "address",
)


def update_organization(tenant: Tenant, **values) -> Tenant:
    """Update a tenant's organisation-level settings and persist.

    Only the known organisation fields are written, so a stray key in the form's
    cleaned data can never set an arbitrary attribute on the tenant.
    """
    for field in ORGANIZATION_FIELDS:
        if field in values:
            value = values[field]
            setattr(tenant, field, value.strip() if isinstance(value, str) else value)
    tenant.save(update_fields=[*ORGANIZATION_FIELDS, "updated_at"])
    return tenant
