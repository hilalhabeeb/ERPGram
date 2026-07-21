"""Masters for GCC domestic-worker supply agencies.

The business these model: a household **sponsor** asks for a housemaid, driver,
cook or carer; the agency offers **workers** sourced from partner **agents**
abroad (Indonesia, the Philippines, Sri Lanka, Ethiopia, Kenya, India, Nepal);
once the sponsor agrees the worker ends up **on the sponsor's visa** for a fixed
period (typically one or two years).

Two things drive almost every screen:

* ``Worker.availability`` — can this worker be offered right now?
* ``Worker.location``     — already in-country (a visa *transfer*, quick) or
  still overseas (needs travel, medical and visa processing before delivery).

``Country`` and ``Language`` are shared reference data, not tenant-scoped:
they are objective facts, identical for every agency, and keeping one row per
country avoids re-seeding the world for each tenant. Everything an agency
actually owns or configures is ``TenantScopedModel`` with an RLS policy.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantScopedModel, TimeStampedModel, UUIDPrimaryKeyModel

# --- shared reference data ---------------------------------------------------


class Country(UUIDPrimaryKeyModel, TimeStampedModel):
    """A source country workers are recruited from."""

    name = models.CharField(_("name"), max_length=100, unique=True)
    iso_code = models.CharField(_("ISO code"), max_length=2, unique=True)
    is_source = models.BooleanField(
        _("recruitment source"),
        default=True,
        help_text=_("Shown when choosing where a worker was recruited from."),
    )

    class Meta:
        verbose_name = _("country")
        verbose_name_plural = _("countries")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Language(UUIDPrimaryKeyModel, TimeStampedModel):
    """A language a worker may speak — the main matching criterion after skills."""

    name = models.CharField(_("name"), max_length=60, unique=True)
    code = models.CharField(_("code"), max_length=10, unique=True)

    class Meta:
        verbose_name = _("language")
        verbose_name_plural = _("languages")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


# --- tenant configuration ----------------------------------------------------


class Occupation(TenantScopedModel):
    """What the worker is hired as: housemaid, driver, cook, nanny, carer."""

    name = models.CharField(_("name"), max_length=100)
    code = models.CharField(_("code"), max_length=20, blank=True)
    description = models.CharField(_("description"), max_length=200, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("occupation")
        verbose_name_plural = _("occupations")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


class Skill(TenantScopedModel):
    """A capability used to match a worker to a sponsor's request."""

    name = models.CharField(_("name"), max_length=100)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("skill")
        verbose_name_plural = _("skills")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


class Agent(TenantScopedModel):
    """An overseas partner agency that supplies workers."""

    name = models.CharField(_("name"), max_length=200)
    country = models.ForeignKey(
        Country,
        verbose_name=_("country"),
        on_delete=models.PROTECT,
        related_name="agents",
    )
    contact_person = models.CharField(_("contact person"), max_length=200, blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    email = models.EmailField(_("email"), blank=True)
    licence_no = models.CharField(_("licence no."), max_length=60, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("agent")
        verbose_name_plural = _("agents")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


class Accommodation(TenantScopedModel):
    """Agency housing where workers stay between placements."""

    name = models.CharField(_("name"), max_length=150)
    address = models.TextField(_("address"), blank=True)
    capacity = models.PositiveIntegerField(_("capacity"), default=0)
    supervisor = models.CharField(_("supervisor"), max_length=150, blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("accommodation")
        verbose_name_plural = _("accommodation")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


class DocumentType(TenantScopedModel):
    """A kind of document held against a worker (passport, medical, visa…)."""

    name = models.CharField(_("name"), max_length=100)
    has_expiry = models.BooleanField(
        _("tracks expiry"),
        default=True,
        help_text=_("Documents of this type are watched for upcoming expiry."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("document type")
        verbose_name_plural = _("document types")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


# --- the customer ------------------------------------------------------------


class Sponsor(TenantScopedModel):
    """The customer: the household (or company) the worker will be sponsored by.

    In this market the sponsor is usually an individual with a national ID
    (CPR/Iqama), not a company — the visa is issued in their name, which is why
    the ID and contact details matter more than trade registration.
    """

    class Kind(models.TextChoices):
        INDIVIDUAL = "individual", _("Individual")
        COMPANY = "company", _("Company")

    name = models.CharField(_("name"), max_length=200)
    name_ar = models.CharField(_("name (Arabic)"), max_length=200, blank=True)
    kind = models.CharField(_("type"), max_length=20, choices=Kind.choices, default=Kind.INDIVIDUAL)
    national_id = models.CharField(
        _("national ID / CPR"),
        max_length=40,
        blank=True,
        help_text=_("The ID the residence permit will be issued against."),
    )
    cr_number = models.CharField(_("CR number"), max_length=60, blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    email = models.EmailField(_("email"), blank=True)
    area = models.CharField(_("area"), max_length=120, blank=True)
    address = models.TextField(_("address"), blank=True)
    household_size = models.PositiveIntegerField(_("household size"), null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("sponsor")
        verbose_name_plural = _("sponsors")
        ordering = ["name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


# --- the worker --------------------------------------------------------------


class Worker(TenantScopedModel):
    """A domestic worker the agency can offer to a sponsor."""

    class Availability(models.TextChoices):
        AVAILABLE = "available", _("Available")
        RESERVED = "reserved", _("Reserved")
        PLACED = "placed", _("Placed")
        RETURNED = "returned", _("Returned")
        UNAVAILABLE = "unavailable", _("Unavailable")

    class Location(models.TextChoices):
        # Drives the whole pipeline: in-country is a visa transfer (days),
        # overseas needs travel, medical and visa processing (weeks).
        IN_COUNTRY = "in_country", _("In country")
        OVERSEAS = "overseas", _("Overseas")

    class Gender(models.TextChoices):
        FEMALE = "female", _("Female")
        MALE = "male", _("Male")

    class MaritalStatus(models.TextChoices):
        SINGLE = "single", _("Single")
        MARRIED = "married", _("Married")
        DIVORCED = "divorced", _("Divorced")
        WIDOWED = "widowed", _("Widowed")

    reference = models.CharField(
        _("reference"),
        max_length=30,
        help_text=_("The code sponsors see when choosing a worker."),
    )
    full_name = models.CharField(_("full name"), max_length=200)
    photo = models.FileField(_("photo"), upload_to="workers/", blank=True)
    gender = models.CharField(
        _("gender"), max_length=10, choices=Gender.choices, default=Gender.FEMALE
    )
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    nationality = models.ForeignKey(
        Country,
        verbose_name=_("nationality"),
        on_delete=models.PROTECT,
        related_name="workers",
    )
    religion = models.CharField(_("religion"), max_length=60, blank=True)
    marital_status = models.CharField(
        _("marital status"), max_length=20, choices=MaritalStatus.choices, blank=True
    )
    children = models.PositiveIntegerField(_("children"), null=True, blank=True)

    occupation = models.ForeignKey(
        Occupation,
        verbose_name=_("occupation"),
        on_delete=models.PROTECT,
        related_name="workers",
    )
    skills = models.ManyToManyField(
        Skill, verbose_name=_("skills"), blank=True, related_name="workers"
    )
    languages = models.ManyToManyField(
        Language, verbose_name=_("languages"), blank=True, related_name="workers"
    )
    experience_years = models.PositiveIntegerField(_("years of experience"), default=0)
    experience_notes = models.TextField(_("experience"), blank=True)

    passport_no = models.CharField(_("passport no."), max_length=40, blank=True)
    passport_expiry = models.DateField(_("passport expiry"), null=True, blank=True)

    availability = models.CharField(
        _("availability"),
        max_length=20,
        choices=Availability.choices,
        default=Availability.AVAILABLE,
    )
    location = models.CharField(
        _("location"), max_length=20, choices=Location.choices, default=Location.OVERSEAS
    )
    agent = models.ForeignKey(
        Agent,
        verbose_name=_("agent"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workers",
    )
    accommodation = models.ForeignKey(
        Accommodation,
        verbose_name=_("accommodation"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workers",
        help_text=_("Where the worker stays while in country and unplaced."),
    )
    monthly_salary = models.DecimalField(
        _("monthly salary"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    available_from = models.DateField(_("available from"), null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("worker")
        verbose_name_plural = _("workers")
        ordering = ["full_name"]
        base_manager_name = "all_tenants"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "reference"], name="uniq_worker_tenant_reference"
            ),
        ]
        indexes = [
            # The worker list is filtered on these on almost every request.
            models.Index(fields=["tenant", "availability", "location"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} · {self.full_name}"

    @property
    def is_offerable(self) -> bool:
        """Can this worker be shown to a sponsor as available right now?"""
        return self.is_active and self.availability == self.Availability.AVAILABLE


class ChargeType(TenantScopedModel):
    """A line an agency puts on a placement invoice, with its usual price."""

    name = models.CharField(_("name"), max_length=120)
    default_amount = models.DecimalField(
        _("default amount"), max_digits=10, decimal_places=3, default=0
    )
    is_taxable = models.BooleanField(_("taxable"), default=True)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("charge type")
        verbose_name_plural = _("charge types")
        ordering = ["sort_order", "name"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return self.name


class Placement(TenantScopedModel):
    """A worker placed with a sponsor — and the invoice for it.

    This is the agency's final document: it carries the agreement (which worker,
    which sponsor, how long the visa runs) *and* the money (ticket, visa
    processing, medical, margin, tax, terms). One record rather than two because
    that is how the trade works — the signed paper the sponsor takes away is the
    same paper that says what they owe.

    Worker and occupation are snapshotted onto the row. An invoice must keep
    saying what was agreed even after someone renames an occupation or corrects
    a worker's name years later.
    """

    class Route(models.TextChoices):
        # The two pipelines: a worker already here only needs the visa moved to
        # the sponsor; one abroad needs travel, medical and visa processing.
        TRANSFER = "transfer", _("Visa transfer (in country)")
        OVERSEAS = "overseas", _("Overseas recruitment")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        CONFIRMED = "confirmed", _("Confirmed")
        PROCESSING = "processing", _("Processing")
        DELIVERED = "delivered", _("Delivered")
        CANCELLED = "cancelled", _("Cancelled")

    class VisaPeriod(models.IntegerChoices):
        ONE_YEAR = 12, _("1 year")
        TWO_YEARS = 24, _("2 years")

    reference = models.CharField(_("reference"), max_length=30)
    sponsor = models.ForeignKey(
        Sponsor, verbose_name=_("sponsor"), on_delete=models.PROTECT, related_name="placements"
    )
    worker = models.ForeignKey(
        Worker, verbose_name=_("worker"), on_delete=models.PROTECT, related_name="placements"
    )
    worker_name = models.CharField(_("worker name"), max_length=200, blank=True)
    occupation_name = models.CharField(_("occupation"), max_length=100, blank=True)

    route = models.CharField(_("route"), max_length=20, choices=Route.choices)
    visa_period_months = models.PositiveSmallIntegerField(
        _("visa period"), choices=VisaPeriod.choices, default=VisaPeriod.TWO_YEARS
    )
    status = models.CharField(
        _("status"), max_length=20, choices=Status.choices, default=Status.DRAFT
    )

    agreed_on = models.DateField(_("agreed on"), null=True, blank=True)
    # Overseas milestones; a transfer skips most of these.
    medical_on = models.DateField(_("medical completed"), null=True, blank=True)
    visa_applied_on = models.DateField(_("visa applied"), null=True, blank=True)
    visa_issued_on = models.DateField(_("visa issued"), null=True, blank=True)
    travel_on = models.DateField(_("travel date"), null=True, blank=True)
    arrival_on = models.DateField(_("arrival date"), null=True, blank=True)
    delivered_on = models.DateField(_("delivered on"), null=True, blank=True)

    contract_start = models.DateField(_("contract start"), null=True, blank=True)
    contract_end = models.DateField(_("contract end"), null=True, blank=True)

    # --- invoice ---
    invoice_date = models.DateField(_("invoice date"), null=True, blank=True)
    tax_rate = models.DecimalField(
        _("tax rate %"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        help_text=_("Applied to taxable lines only."),
    )
    discount = models.DecimalField(_("discount"), max_digits=10, decimal_places=3, default=0)
    amount_paid = models.DecimalField(_("amount paid"), max_digits=10, decimal_places=3, default=0)
    payment_terms = models.CharField(_("payment terms"), max_length=200, blank=True)
    terms = models.TextField(_("terms and conditions"), blank=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("placement")
        verbose_name_plural = _("placements")
        ordering = ["-created_at"]
        base_manager_name = "all_tenants"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "reference"], name="uniq_placement_tenant_reference"
            ),
        ]
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self) -> str:
        return f"{self.reference} · {self.worker_name}"

    # --- money ---
    # Derived rather than stored: the charge lines are the source of truth, and
    # a stored total is one edit away from disagreeing with them.

    @property
    def subtotal(self) -> Decimal:
        return sum((line.amount for line in self.charges.all()), Decimal("0"))

    @property
    def taxable_base(self) -> Decimal:
        return sum((line.amount for line in self.charges.all() if line.is_taxable), Decimal("0"))

    @property
    def tax_amount(self) -> Decimal:
        base = self.taxable_base - self.discount
        if base <= 0:
            return Decimal("0.000")
        return (base * self.tax_rate / Decimal("100")).quantize(Decimal("0.001"))

    @property
    def total(self) -> Decimal:
        return (self.subtotal - self.discount + self.tax_amount).quantize(Decimal("0.001"))

    @property
    def balance_due(self) -> Decimal:
        return (self.total - self.amount_paid).quantize(Decimal("0.001"))

    @property
    def is_paid(self) -> bool:
        return self.balance_due <= 0

    @property
    def milestones(self) -> list[dict]:
        """The pipeline for this route, in order, with the date reached."""
        steps = [(_("Agreed"), self.agreed_on)]
        if self.route == self.Route.OVERSEAS:
            steps += [
                (_("Medical"), self.medical_on),
                (_("Visa applied"), self.visa_applied_on),
                (_("Visa issued"), self.visa_issued_on),
                (_("Travel"), self.travel_on),
                (_("Arrival"), self.arrival_on),
            ]
        else:
            steps += [(_("Visa transferred"), self.visa_issued_on)]
        steps.append((_("Delivered"), self.delivered_on))
        return [{"label": label, "date": date, "done": date is not None} for label, date in steps]


class PlacementCharge(TenantScopedModel):
    """One priced line on a placement invoice."""

    placement = models.ForeignKey(
        Placement, verbose_name=_("placement"), on_delete=models.CASCADE, related_name="charges"
    )
    description = models.CharField(_("description"), max_length=200)
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=3, default=0)
    is_taxable = models.BooleanField(_("taxable"), default=True)
    sort_order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("charge")
        verbose_name_plural = _("charges")
        ordering = ["sort_order", "id"]
        base_manager_name = "all_tenants"

    def __str__(self) -> str:
        return f"{self.description}: {self.amount}"


class WorkerDocument(TenantScopedModel):
    """A document held against a worker, with the expiry the agency chases."""

    worker = models.ForeignKey(
        Worker, verbose_name=_("worker"), on_delete=models.CASCADE, related_name="documents"
    )
    document_type = models.ForeignKey(
        DocumentType,
        verbose_name=_("document type"),
        on_delete=models.PROTECT,
        related_name="documents",
    )
    number = models.CharField(_("number"), max_length=80, blank=True)
    issued_on = models.DateField(_("issued on"), null=True, blank=True)
    expires_on = models.DateField(_("expires on"), null=True, blank=True)
    file = models.FileField(_("file"), upload_to="worker-documents/", blank=True)
    notes = models.CharField(_("notes"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("worker document")
        verbose_name_plural = _("worker documents")
        ordering = ["-issued_on", "document_type__name"]
        base_manager_name = "all_tenants"
        indexes = [models.Index(fields=["tenant", "expires_on"])]

    def __str__(self) -> str:
        return f"{self.document_type} · {self.worker_id}"
