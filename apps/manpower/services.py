"""Manpower business logic. Views orchestrate; these functions decide."""

from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.tenant import activate_tenant
from apps.manpower.models import (
    Accommodation,
    Agent,
    ChargeType,
    Country,
    DocumentType,
    Language,
    Occupation,
    Placement,
    PlacementCharge,
    Skill,
    Sponsor,
    Worker,
    WorkerDocument,
)
from apps.tenancy.models import Tenant

# Defaults a new manpower tenant starts with, so the product is usable on the
# first login instead of presenting empty dropdowns.
DEFAULT_OCCUPATIONS = [
    ("Housemaid", "HM"),
    ("Driver", "DR"),
    ("Cook", "CK"),
    ("Nanny", "NN"),
    ("Carer", "CR"),
    ("Cleaner", "CL"),
    ("Gardener", "GD"),
]

DEFAULT_SKILLS = [
    "Childcare",
    "Elderly care",
    "Cooking",
    "Arabic cooking",
    "Baby care",
    "Ironing",
    "Cleaning",
    "Driving licence",
    "Special needs care",
    "Pet care",
]

DEFAULT_DOCUMENT_TYPES = [
    ("Passport", True),
    ("Visa", True),
    ("Medical certificate", True),
    ("Police clearance", True),
    ("Employment contract", True),
    ("Photograph", False),
]

# (name, iso, is_source) — the countries this market actually recruits from,
# plus the GCC states workers are placed in.
REFERENCE_COUNTRIES = [
    ("Indonesia", "ID", True),
    ("Philippines", "PH", True),
    ("Sri Lanka", "LK", True),
    ("India", "IN", True),
    ("Nepal", "NP", True),
    ("Bangladesh", "BD", True),
    ("Ethiopia", "ET", True),
    ("Kenya", "KE", True),
    ("Uganda", "UG", True),
    ("Myanmar", "MM", True),
    ("Bahrain", "BH", False),
    ("Saudi Arabia", "SA", False),
    ("Kuwait", "KW", False),
    ("Qatar", "QA", False),
    ("United Arab Emirates", "AE", False),
    ("Oman", "OM", False),
]

REFERENCE_LANGUAGES = [
    ("Arabic", "ar"),
    ("English", "en"),
    ("Hindi", "hi"),
    ("Malayalam", "ml"),
    ("Tamil", "ta"),
    ("Sinhala", "si"),
    ("Tagalog", "tl"),
    ("Indonesian", "id"),
    ("Amharic", "am"),
    ("Swahili", "sw"),
    ("Nepali", "ne"),
    ("Bengali", "bn"),
]


@transaction.atomic
def ensure_reference_data() -> None:
    """Create the shared country/language rows. Safe to call repeatedly."""
    for name, iso, is_source in REFERENCE_COUNTRIES:
        Country.objects.update_or_create(
            iso_code=iso, defaults={"name": name, "is_source": is_source}
        )
    for name, code in REFERENCE_LANGUAGES:
        Language.objects.update_or_create(code=code, defaults={"name": name})


def ensure_tenant_defaults(tenant: Tenant, *, user=None) -> None:
    """Give a new manpower tenant its starting occupations, skills and doc types.

    Called on sign-up so an agency never faces an empty product. Idempotent, so
    re-running seed or re-saving a tenant cannot duplicate rows.

    Binds the tenant itself rather than trusting the caller to: these are
    RLS-protected tables, and an INSERT with no ``app.tenant_id`` set is
    rejected by the database — as sign-up and the demo seed both discovered.
    """
    with activate_tenant(tenant.id), transaction.atomic():
        for name, code in DEFAULT_OCCUPATIONS:
            Occupation.all_tenants.get_or_create(
                tenant=tenant,
                name=name,
                defaults={"code": code, "created_by": user, "updated_by": user},
            )
        for name in DEFAULT_SKILLS:
            Skill.all_tenants.get_or_create(
                tenant=tenant, name=name, defaults={"created_by": user, "updated_by": user}
            )
        for name, has_expiry in DEFAULT_DOCUMENT_TYPES:
            DocumentType.all_tenants.get_or_create(
                tenant=tenant,
                name=name,
                defaults={"has_expiry": has_expiry, "created_by": user, "updated_by": user},
            )


# --- workers -----------------------------------------------------------------


def workers_for(
    tenant: Tenant,
    *,
    search: str = "",
    occupation: str = "",
    nationality: str = "",
    availability: str = "",
    location: str = "",
    include_archived: bool = False,
) -> QuerySet[Worker]:
    """The worker list, filtered the way the office actually searches it."""
    queryset = Worker.objects.filter(tenant=tenant).select_related(
        "nationality", "occupation", "agent"
    )
    if not include_archived:
        queryset = queryset.filter(is_active=True)
    if search:
        queryset = queryset.filter(
            Q(full_name__icontains=search)
            | Q(reference__icontains=search)
            | Q(passport_no__icontains=search)
        )
    if occupation:
        queryset = queryset.filter(occupation_id=occupation)
    if nationality:
        queryset = queryset.filter(nationality_id=nationality)
    if availability:
        queryset = queryset.filter(availability=availability)
    if location:
        queryset = queryset.filter(location=location)
    return queryset


def next_worker_reference(tenant: Tenant) -> str:
    """Sequential per-tenant reference like W-0042."""
    last = (
        Worker.all_tenants.filter(tenant=tenant, reference__startswith="W-")
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )
    number = 0
    if last:
        try:
            number = int(last.split("-", 1)[1])
        except (IndexError, ValueError):
            number = 0
    return f"W-{number + 1:04d}"


@transaction.atomic
def create_worker(*, tenant: Tenant, user, skills=None, languages=None, **fields) -> Worker:
    fields.setdefault("reference", next_worker_reference(tenant))
    worker = Worker.objects.create(tenant=tenant, created_by=user, updated_by=user, **fields)
    _set_worker_relations(worker, tenant=tenant, skills=skills, languages=languages)
    return worker


@transaction.atomic
def update_worker(worker: Worker, *, user, skills=None, languages=None, **fields) -> Worker:
    for name, value in fields.items():
        setattr(worker, name, value)
    worker.updated_by = user
    worker.save()
    _set_worker_relations(worker, tenant=worker.tenant, skills=skills, languages=languages)
    return worker


def _set_worker_relations(worker: Worker, *, tenant: Tenant, skills, languages) -> None:
    """Attach skills/languages, re-checking tenant ownership.

    The join tables carry no tenant column, so RLS cannot protect them. Skills
    are re-filtered against the tenant here so a tampered POST cannot link
    another agency's row even if a form is bypassed. Languages are shared
    reference data and need no such check.
    """
    if skills is not None:
        owned = Skill.all_tenants.filter(tenant=tenant, pk__in=[s.pk for s in skills])
        worker.skills.set(owned)
    if languages is not None:
        worker.languages.set(languages)


@transaction.atomic
def set_worker_active(worker: Worker, *, user, is_active: bool) -> Worker:
    worker.is_active = is_active
    worker.updated_by = user
    worker.save(update_fields=["is_active", "updated_by", "updated_at"])
    return worker


def worker_summary(tenant: Tenant) -> list[dict]:
    """Counts for the worker dashboard cards."""
    base = Worker.objects.filter(tenant=tenant, is_active=True)
    return [
        {
            "key": "available",
            "label": _("Available"),
            "value": base.filter(availability=Worker.Availability.AVAILABLE).count(),
            "icon": "users",
        },
        {
            "key": "in_country",
            "label": _("In country"),
            "value": base.filter(location=Worker.Location.IN_COUNTRY).count(),
            "icon": "building",
        },
        {
            "key": "overseas",
            "label": _("Overseas"),
            "value": base.filter(location=Worker.Location.OVERSEAS).count(),
            "icon": "globe",
        },
        {
            "key": "placed",
            "label": _("Placed"),
            "value": base.filter(availability=Worker.Availability.PLACED).count(),
            "icon": "check-circle",
        },
    ]


# --- sponsors ----------------------------------------------------------------


def sponsors_for(
    tenant: Tenant, *, search: str = "", include_archived: bool = False
) -> QuerySet[Sponsor]:
    queryset = Sponsor.objects.filter(tenant=tenant)
    if not include_archived:
        queryset = queryset.filter(is_active=True)
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(national_id__icontains=search)
            | Q(phone__icontains=search)
        )
    return queryset


@transaction.atomic
def create_sponsor(*, tenant: Tenant, user, **fields) -> Sponsor:
    return Sponsor.objects.create(tenant=tenant, created_by=user, updated_by=user, **fields)


@transaction.atomic
def update_sponsor(sponsor: Sponsor, *, user, **fields) -> Sponsor:
    for name, value in fields.items():
        setattr(sponsor, name, value)
    sponsor.updated_by = user
    sponsor.save()
    return sponsor


@transaction.atomic
def set_sponsor_active(sponsor: Sponsor, *, user, is_active: bool) -> Sponsor:
    sponsor.is_active = is_active
    sponsor.updated_by = user
    sponsor.save(update_fields=["is_active", "updated_by", "updated_at"])
    return sponsor


# --- placements --------------------------------------------------------------


def add_months(start: dt.date, months: int) -> dt.date:
    """Date `months` later, clamped to the end of the target month.

    Hand-rolled rather than pulling in python-dateutil for one call: a visa
    period is always a whole number of months, and 31 Jan + 1 month must land on
    28/29 Feb rather than raise.
    """
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def placements_for(tenant: Tenant, *, search: str = "", status: str = "") -> QuerySet[Placement]:
    queryset = Placement.objects.filter(tenant=tenant).select_related("sponsor", "worker")
    if search:
        queryset = queryset.filter(
            Q(reference__icontains=search)
            | Q(worker_name__icontains=search)
            | Q(sponsor__name__icontains=search)
        )
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def next_placement_reference(tenant: Tenant) -> str:
    last = (
        Placement.all_tenants.filter(tenant=tenant, reference__startswith="PL-")
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )
    number = 0
    if last:
        try:
            number = int(last.split("-", 1)[1])
        except (IndexError, ValueError):
            number = 0
    return f"PL-{number + 1:04d}"


DEFAULT_CHARGE_TYPES = [
    # (name, default amount, taxable) — the lines a GCC agency actually bills.
    ("Service fee", Decimal("450.000"), True),
    ("Visa processing", Decimal("150.000"), True),
    ("Air ticket", Decimal("120.000"), False),
    ("Medical examination", Decimal("40.000"), True),
    ("Insurance", Decimal("25.000"), True),
    ("Agency margin", Decimal("100.000"), True),
]


def ensure_charge_types(tenant: Tenant, *, user=None) -> None:
    """Starting price list, so a new agency can raise an invoice immediately."""
    with activate_tenant(tenant.id), transaction.atomic():
        for order, (name, amount, taxable) in enumerate(DEFAULT_CHARGE_TYPES):
            ChargeType.all_tenants.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "default_amount": amount,
                    "is_taxable": taxable,
                    "sort_order": order,
                    "created_by": user,
                    "updated_by": user,
                },
            )


@transaction.atomic
def create_placement(
    *, tenant: Tenant, user, sponsor: Sponsor, worker: Worker, **fields
) -> Placement:
    """Open a placement and pre-fill it from the agency's price list.

    The route is taken from where the worker actually is, not from user input:
    an in-country worker is a visa transfer, an overseas one needs the full
    travel/medical/visa pipeline.
    """
    route = (
        Placement.Route.TRANSFER
        if worker.location == Worker.Location.IN_COUNTRY
        else Placement.Route.OVERSEAS
    )
    placement = Placement.objects.create(
        tenant=tenant,
        reference=next_placement_reference(tenant),
        sponsor=sponsor,
        worker=worker,
        # Snapshots: the invoice must keep saying what was agreed even if the
        # worker record is edited later.
        worker_name=worker.full_name,
        occupation_name=worker.occupation.name,
        route=route,
        created_by=user,
        updated_by=user,
        **fields,
    )
    apply_default_charges(placement, user=user)
    return placement


def apply_default_charges(placement: Placement, *, user=None) -> None:
    """Copy the price list onto a placement that has no lines yet."""
    if placement.charges.exists():
        return
    for charge_type in ChargeType.objects.filter(tenant=placement.tenant, is_active=True):
        PlacementCharge.objects.create(
            tenant=placement.tenant,
            placement=placement,
            description=charge_type.name,
            amount=charge_type.default_amount,
            is_taxable=charge_type.is_taxable,
            sort_order=charge_type.sort_order,
            created_by=user,
            updated_by=user,
        )


@transaction.atomic
def update_placement(placement: Placement, *, user, **fields) -> Placement:
    for name, value in fields.items():
        setattr(placement, name, value)
    placement.updated_by = user
    placement.save()
    return placement


# Which worker availability each placement status implies. Keeping this as one
# table means the worker register can never drift from the placements: there is
# a single place that decides what "confirmed" or "cancelled" does to a worker.
_WORKER_STATE_FOR_STATUS = {
    Placement.Status.DRAFT: None,  # a draft reserves nothing
    Placement.Status.CONFIRMED: Worker.Availability.RESERVED,
    Placement.Status.PROCESSING: Worker.Availability.RESERVED,
    Placement.Status.DELIVERED: Worker.Availability.PLACED,
    Placement.Status.CANCELLED: Worker.Availability.AVAILABLE,
}


@transaction.atomic
def set_placement_status(placement: Placement, *, user, status: str) -> Placement:
    """Move a placement along and keep the worker's availability in step."""
    placement.status = status
    today = timezone.localdate()

    if status == Placement.Status.CONFIRMED and placement.agreed_on is None:
        placement.agreed_on = today
    if status == Placement.Status.DELIVERED:
        placement.delivered_on = placement.delivered_on or today
        if placement.contract_start is None:
            placement.contract_start = placement.delivered_on
        if placement.contract_end is None:
            placement.contract_end = add_months(
                placement.contract_start, placement.visa_period_months
            )

    placement.updated_by = user
    placement.save()

    new_state = _WORKER_STATE_FOR_STATUS.get(status)
    if new_state is not None:
        worker = placement.worker
        worker.availability = new_state
        if status == Placement.Status.DELIVERED:
            # Delivered means the worker is now on the sponsor's visa, in country.
            worker.location = Worker.Location.IN_COUNTRY
        worker.updated_by = user
        worker.save(update_fields=["availability", "location", "updated_by", "updated_at"])

    return placement


def expiring_documents(tenant: Tenant, *, within_days: int = 90, limit: int = 8):
    """Worker documents about to expire — the thing that bites an agency.

    A lapsed passport or permit stops a placement dead, so the dashboard leads
    with it. Only types flagged as tracking expiry are considered.
    """
    today = timezone.localdate()
    horizon = today + dt.timedelta(days=within_days)
    return (
        WorkerDocument.objects.filter(
            tenant=tenant,
            document_type__has_expiry=True,
            expires_on__isnull=False,
            expires_on__lte=horizon,
            worker__is_active=True,
        )
        .select_related("worker", "document_type")
        .order_by("expires_on")[:limit]
    )


def placement_summary(tenant: Tenant) -> list[dict]:
    base = Placement.objects.filter(tenant=tenant)
    return [
        {
            "key": "processing",
            "label": _("In progress"),
            "value": base.filter(
                status__in=[Placement.Status.CONFIRMED, Placement.Status.PROCESSING]
            ).count(),
            "icon": "briefcase",
        },
        {
            "key": "delivered",
            "label": _("Delivered"),
            "value": base.filter(status=Placement.Status.DELIVERED).count(),
            "icon": "check-circle",
        },
        {
            "key": "unpaid",
            "label": _("Awaiting payment"),
            "value": sum(
                1
                for placement in base.exclude(status=Placement.Status.CANCELLED).prefetch_related(
                    "charges"
                )
                if not placement.is_paid
            ),
            "icon": "file-text",
        },
    ]


# --- setup lists -------------------------------------------------------------

SETUP_MODELS = {
    "occupations": Occupation,
    "skills": Skill,
    "agents": Agent,
    "accommodation": Accommodation,
    "document-types": DocumentType,
}
