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
