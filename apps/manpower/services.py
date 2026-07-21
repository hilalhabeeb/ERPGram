"""Manpower business logic. Views orchestrate; these functions decide."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils.translation import gettext as _

from apps.core.tenant import activate_tenant
from apps.manpower.models import (
    Accommodation,
    Agent,
    Country,
    DocumentType,
    Language,
    Occupation,
    Skill,
    Sponsor,
    Worker,
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


# --- setup lists -------------------------------------------------------------

SETUP_MODELS = {
    "occupations": Occupation,
    "skills": Skill,
    "agents": Agent,
    "accommodation": Accommodation,
    "document-types": DocumentType,
}
