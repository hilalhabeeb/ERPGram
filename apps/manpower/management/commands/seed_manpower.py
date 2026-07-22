"""Demo data for a GCC domestic-worker agency.

Creates a manpower tenant with agents, accommodation, sponsors and a register of
workers spread across nationalities, occupations, availability and — most
importantly — both sides of the ``location`` split, since in-country workers are
a visa transfer while overseas workers need travel and processing.

Idempotent: re-running tops the tenant up rather than duplicating it.
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Membership
from apps.accounts.services import ensure_system_roles
from apps.billing import services as billing_services
from apps.billing.models import Service
from apps.core.domains import MANPOWER
from apps.core.permissions import MANAGE_SPONSORS, MANAGE_WORKERS
from apps.core.tenant import activate_tenant
from apps.manpower import services
from apps.manpower.models import (
    Accommodation,
    Agent,
    Country,
    DocumentType,
    Language,
    Occupation,
    Placement,
    Skill,
    Sponsor,
    Worker,
    WorkerDocument,
)
from apps.tenancy.models import Tenant

try:  # the demo password matches the core seed command
    from apps.tenancy.management.commands.seed import DEMO_PASSWORD
except ImportError:  # pragma: no cover - defensive
    DEMO_PASSWORD = "demo-pass-123"

TENANT = {"slug": "gulf-domestic", "name": "Gulf Domestic Services", "timezone": "Asia/Bahrain"}

STAFF = [
    ("owner@gulfdomestic.test", "Fatima Al-Ansari", True, None),
    ("coordinator@gulfdomestic.test", "Yousif Salman", False, "Placement coordinator"),
    ("reception@gulfdomestic.test", "Mariam Hasan", False, "Reception"),
]

AGENTS = [
    ("PT Sinar Harapan", "ID", "Budi Santoso", "+62 21 5550 118"),
    ("Manila Care Recruitment", "PH", "Grace Reyes", "+63 2 8551 2204"),
    ("Lanka Bridge Agency", "LK", "Nimal Perera", "+94 11 250 7788"),
    ("Addis Horizon Agency", "ET", "Selam Bekele", "+251 11 662 1190"),
    ("Kochi Overseas Services", "IN", "Rajesh Menon", "+91 484 240 5566"),
]

ACCOMMODATION = [
    ("Manama Staff House", "Building 214, Road 1502, Hoora, Manama", 24, "Asha Kumari"),
    ("Riffa Transit House", "Villa 8, Road 77, East Riffa", 12, "Joan Mwangi"),
]

SPONSORS = [
    ("Ahmed Al-Khalifa", "أحمد آل خليفة", "individual", "780112345", "+973 3944 1122", "Saar", 6),
    (
        "Layla Al-Mannai",
        "ليلى المناعي",
        "individual",
        "830254411",
        "+973 3611 7788",
        "Janabiyah",
        4,
    ),
    ("Hassan Al-Dosari", "حسن الدوسري", "individual", "750391002", "+973 3922 4455", "Isa Town", 5),
    ("Noora Al-Sayed", "نورة السيد", "individual", "880477520", "+973 3355 9010", "Budaiya", 3),
    ("Khalid Bu Ali", "خالد بوعلي", "individual", "790188033", "+973 3688 2244", "Riffa", 7),
    ("Gulf Pearl Hotel", "فندق لؤلؤة الخليج", "company", "", "+973 1771 4000", "Seef", None),
]

# (name, iso, occupation, gender, age, experience, religion, marital, languages, skills)
WORKERS = [
    (
        "Siti Nurhaliza",
        "ID",
        "Housemaid",
        34,
        8,
        "Muslim",
        "married",
        ["id", "ar"],
        ["Cleaning", "Cooking", "Ironing"],
    ),
    (
        "Dewi Lestari",
        "ID",
        "Housemaid",
        29,
        5,
        "Muslim",
        "single",
        ["id", "en"],
        ["Cleaning", "Baby care"],
    ),
    (
        "Rina Wulandari",
        "ID",
        "Nanny",
        31,
        7,
        "Muslim",
        "married",
        ["id", "ar", "en"],
        ["Childcare", "Baby care"],
    ),
    (
        "Maria Santos",
        "PH",
        "Housemaid",
        36,
        11,
        "Christian",
        "married",
        ["tl", "en"],
        ["Cleaning", "Cooking", "Ironing"],
    ),
    (
        "Jenny Cruz",
        "PH",
        "Nanny",
        27,
        4,
        "Christian",
        "single",
        ["tl", "en"],
        ["Childcare", "Baby care", "Cleaning"],
    ),
    (
        "Angelica Ramos",
        "PH",
        "Carer",
        42,
        15,
        "Christian",
        "widowed",
        ["tl", "en", "ar"],
        ["Elderly care", "Special needs care"],
    ),
    (
        "Rosalyn Bautista",
        "PH",
        "Cook",
        39,
        12,
        "Christian",
        "married",
        ["tl", "en"],
        ["Cooking", "Arabic cooking"],
    ),
    (
        "Nilanthi Fernando",
        "LK",
        "Housemaid",
        33,
        6,
        "Buddhist",
        "married",
        ["si", "en"],
        ["Cleaning", "Cooking"],
    ),
    (
        "Kumari Silva",
        "LK",
        "Carer",
        45,
        16,
        "Buddhist",
        "married",
        ["si", "ta", "en"],
        ["Elderly care", "Cleaning"],
    ),
    (
        "Chamari Perera",
        "LK",
        "Housemaid",
        28,
        3,
        "Christian",
        "single",
        ["si", "en"],
        ["Cleaning", "Ironing"],
    ),
    ("Almaz Tesfaye", "ET", "Housemaid", 26, 2, "Christian", "single", ["am", "ar"], ["Cleaning"]),
    (
        "Hiwot Girma",
        "ET",
        "Housemaid",
        30,
        5,
        "Christian",
        "married",
        ["am", "ar", "en"],
        ["Cleaning", "Cooking"],
    ),
    (
        "Meseret Alemu",
        "ET",
        "Nanny",
        24,
        2,
        "Christian",
        "single",
        ["am", "en"],
        ["Childcare", "Baby care"],
    ),
    (
        "Grace Wanjiru",
        "KE",
        "Housemaid",
        32,
        7,
        "Christian",
        "married",
        ["sw", "en"],
        ["Cleaning", "Ironing", "Cooking"],
    ),
    (
        "Mercy Achieng",
        "KE",
        "Carer",
        38,
        10,
        "Christian",
        "divorced",
        ["sw", "en"],
        ["Elderly care", "Special needs care"],
    ),
    (
        "Lakshmi Nair",
        "IN",
        "Cook",
        41,
        14,
        "Hindu",
        "married",
        ["ml", "ta", "en"],
        ["Cooking", "Arabic cooking", "Cleaning"],
    ),
    (
        "Sunita Devi",
        "IN",
        "Housemaid",
        35,
        9,
        "Hindu",
        "married",
        ["hi", "en"],
        ["Cleaning", "Ironing"],
    ),
    (
        "Anjali Thomas",
        "IN",
        "Nanny",
        29,
        6,
        "Christian",
        "single",
        ["ml", "en", "hi"],
        ["Childcare", "Baby care", "Cooking"],
    ),
    (
        "Rajan Kumar",
        "IN",
        "Driver",
        40,
        15,
        "Hindu",
        "married",
        ["hi", "ml", "en", "ar"],
        ["Driving licence"],
    ),
    ("Sanjay Pillai", "IN", "Driver", 33, 9, "Hindu", "married", ["ml", "en"], ["Driving licence"]),
    (
        "Bikash Thapa",
        "NP",
        "Driver",
        31,
        7,
        "Hindu",
        "married",
        ["ne", "hi", "en"],
        ["Driving licence"],
    ),
    (
        "Sita Gurung",
        "NP",
        "Housemaid",
        27,
        4,
        "Hindu",
        "single",
        ["ne", "hi"],
        ["Cleaning", "Cooking"],
    ),
    (
        "Rehana Begum",
        "BD",
        "Housemaid",
        30,
        5,
        "Muslim",
        "married",
        ["bn", "ar"],
        ["Cleaning", "Cooking"],
    ),
    (
        "Josephine Nakato",
        "UG",
        "Housemaid",
        25,
        2,
        "Christian",
        "single",
        ["sw", "en"],
        ["Cleaning", "Pet care"],
    ),
    (
        "Aye Aye Win",
        "MM",
        "Carer",
        37,
        11,
        "Buddhist",
        "married",
        ["en"],
        ["Elderly care", "Cleaning"],
    ),
    (
        "Marilyn Dela Cruz",
        "PH",
        "Cook",
        44,
        18,
        "Christian",
        "married",
        ["tl", "en", "ar"],
        ["Cooking", "Arabic cooking"],
    ),
    (
        "Fatuma Ali",
        "KE",
        "Housemaid",
        29,
        4,
        "Muslim",
        "single",
        ["sw", "ar", "en"],
        ["Cleaning", "Cooking"],
    ),
    ("Tigist Haile", "ET", "Housemaid", 28, 3, "Christian", "single", ["am"], ["Cleaning"]),
]


class Command(BaseCommand):
    help = "Create a demo GCC domestic-worker agency with workers, sponsors and agents."

    def handle(self, *args, **options):
        # Deterministic so re-running gives the same demo, not a moving target.
        rng = random.Random(20260719)
        tenant, created = self._tenant()
        self.stdout.write(("created " if created else "updated ") + tenant.name)

        services.ensure_reference_data()
        services.ensure_tenant_defaults(tenant)

        owner = self._staff(tenant)
        with activate_tenant(tenant.id):
            agents = self._agents(tenant, owner)
            houses = self._accommodation(tenant, owner)
            self._sponsors(tenant, owner)
            self._workers(tenant, owner, agents, houses, rng)
            self._placements(tenant, owner)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Manpower demo ready. Sign in as:"))
        for email, _name, is_owner, role in STAFF:
            label = "owner " if is_owner else "staff "
            suffix = f"  ({role})" if role else ""
            self.stdout.write(f"  {label}→ {email}  /  {DEMO_PASSWORD}{suffix}")

    # --- pieces ---

    @transaction.atomic
    def _tenant(self):
        tenant, created = Tenant.objects.get_or_create(
            slug=TENANT["slug"],
            defaults={
                "name": TENANT["name"],
                "timezone": TENANT["timezone"],
                "domain": MANPOWER,
            },
        )
        # Billing identity, so the demo invoice prints as a valid tax invoice.
        tenant.domain = MANPOWER
        tenant.legal_name = "Gulf Domestic Services W.L.L."
        tenant.vat_number = "220000123400002"
        tenant.cr_number = "98765-1"
        tenant.address = "Office 402, Building 1420, Road 2815, Seef District, Manama"
        tenant.phone = "+973 1700 1420"
        tenant.email = "accounts@gulfdomestic.test"
        tenant.default_tax_rate = Decimal("10.00")
        tenant.save()
        return tenant, created

    @transaction.atomic
    def _staff(self, tenant):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        roles = ensure_system_roles(tenant)

        # A role that can run the desk without owning the organisation — the
        # thing the old is_owner boolean could not express.
        coordinator, _ = tenant.roles.get_or_create(
            slug="placement-coordinator",
            defaults={
                "name": "Placement coordinator",
                "permissions": [MANAGE_WORKERS, MANAGE_SPONSORS],
                "is_system": False,
            },
        )

        owner = None
        for email, name, is_owner, role_label in STAFF:
            user, made = User.objects.get_or_create(
                email=email, defaults={"full_name": name, "is_active": True}
            )
            if made:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
            Membership.objects.get_or_create(
                user=user,
                tenant=tenant,
                defaults={
                    "is_owner": is_owner,
                    "is_default": True,
                    "role": roles["owner"]
                    if is_owner
                    else (
                        coordinator if role_label == "Placement coordinator" else roles["member"]
                    ),
                },
            )
            if is_owner:
                owner = user
        return owner

    def _agents(self, tenant, owner):
        agents = []
        for name, iso, contact, phone in AGENTS:
            country = Country.objects.get(iso_code=iso)
            agent, _ = Agent.all_tenants.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "country": country,
                    "contact_person": contact,
                    "phone": phone,
                    "created_by": owner,
                    "updated_by": owner,
                },
            )
            agents.append(agent)
        return agents

    def _accommodation(self, tenant, owner):
        houses = []
        for name, address, capacity, supervisor in ACCOMMODATION:
            house, _ = Accommodation.all_tenants.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "address": address,
                    "capacity": capacity,
                    "supervisor": supervisor,
                    "created_by": owner,
                    "updated_by": owner,
                },
            )
            houses.append(house)
        return houses

    def _sponsors(self, tenant, owner):
        for name, name_ar, kind, cpr, phone, area, size in SPONSORS:
            Sponsor.all_tenants.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "name_ar": name_ar,
                    "kind": kind,
                    "national_id": cpr,
                    "phone": phone,
                    "area": area,
                    "household_size": size,
                    "created_by": owner,
                    "updated_by": owner,
                },
            )

    def _workers(self, tenant, owner, agents, houses, rng):
        occupations = {o.name: o for o in Occupation.all_tenants.filter(tenant=tenant)}
        skills = {s.name: s for s in Skill.all_tenants.filter(tenant=tenant)}
        languages = {lang.code: lang for lang in Language.objects.all()}
        agents_by_iso = {a.country.iso_code: a for a in agents}
        passport_type = DocumentType.all_tenants.filter(tenant=tenant, name="Passport").first()

        today = dt.date(2026, 7, 19)
        made = 0

        for index, row in enumerate(WORKERS, start=1):
            name, iso, occupation_name, age, experience, religion, marital, langs, skill_names = row
            reference = f"W-{index:04d}"
            if Worker.all_tenants.filter(tenant=tenant, reference=reference).exists():
                continue

            # Roughly a third are already in country: those are visa transfers.
            in_country = index % 3 == 0
            availability = (
                Worker.Availability.PLACED
                if index % 7 == 0
                else Worker.Availability.RESERVED
                if index % 11 == 0
                else Worker.Availability.AVAILABLE
            )

            worker = Worker.all_tenants.create(
                tenant=tenant,
                reference=reference,
                full_name=name,
                gender=Worker.Gender.MALE if occupation_name == "Driver" else Worker.Gender.FEMALE,
                date_of_birth=today - dt.timedelta(days=age * 365 + rng.randint(0, 300)),
                nationality=Country.objects.get(iso_code=iso),
                religion=religion,
                marital_status=marital,
                children=rng.randint(0, 3) if marital == "married" else 0,
                occupation=occupations.get(occupation_name) or next(iter(occupations.values())),
                experience_years=experience,
                experience_notes=(
                    f"{experience} years with families in "
                    f"{rng.choice(['Bahrain', 'Kuwait', 'Saudi Arabia', 'Qatar', 'UAE'])}."
                ),
                passport_no=f"{iso}{rng.randint(1000000, 9999999)}",
                passport_expiry=today + dt.timedelta(days=rng.randint(200, 1800)),
                availability=availability,
                location=Worker.Location.IN_COUNTRY if in_country else Worker.Location.OVERSEAS,
                agent=agents_by_iso.get(iso),
                accommodation=rng.choice(houses) if in_country else None,
                monthly_salary=rng.choice([100, 110, 120, 130, 140, 150]),
                available_from=today + dt.timedelta(days=rng.randint(0, 60)),
                created_by=owner,
                updated_by=owner,
            )
            worker.skills.set([skills[s] for s in skill_names if s in skills])
            worker.languages.set([languages[c] for c in langs if c in languages])

            if passport_type:
                WorkerDocument.all_tenants.get_or_create(
                    tenant=tenant,
                    worker=worker,
                    document_type=passport_type,
                    defaults={
                        "number": worker.passport_no,
                        "issued_on": worker.passport_expiry - dt.timedelta(days=3650),
                        "expires_on": worker.passport_expiry,
                        "created_by": owner,
                        "updated_by": owner,
                    },
                )
            made += 1

        self.stdout.write(f"  workers created: {made}")

    def _placements(self, tenant, owner):
        """A few placements across the pipeline, so the module has a story.

        One delivered and paid, one mid-processing overseas, one draft transfer —
        enough to show both routes, and invoices in draft, issued and paid states.
        """
        billing_services.ensure_billing_defaults(tenant, user=owner)

        if Placement.all_tenants.filter(tenant=tenant).exists():
            return

        sponsors = list(Sponsor.objects.filter(tenant=tenant).order_by("name")[:3])
        workers = list(
            Worker.objects.filter(
                tenant=tenant, availability=Worker.Availability.AVAILABLE
            ).order_by("reference")[:3]
        )
        if not sponsors or not workers:
            return

        today = dt.date(2026, 7, 19)
        plan = [
            # (status, agreed offset, paid?)
            (Placement.Status.DELIVERED, -120, True),
            (Placement.Status.PROCESSING, -35, False),
            (Placement.Status.DRAFT, -3, False),
        ]

        made = 0
        for index, (status, offset, paid) in enumerate(plan):
            if index >= len(sponsors) or index >= len(workers):
                break
            worker = workers[index]
            placement = services.create_placement(
                tenant=tenant,
                user=owner,
                sponsor=sponsors[index],
                worker=worker,
                visa_period_months=Placement.VisaPeriod.TWO_YEARS,
                agreed_on=today + dt.timedelta(days=offset),
                payment_terms="50% on signing, balance on delivery",
                terms=(
                    "1. The sponsor is responsible for the worker's residence permit.\n"
                    "2. A replacement is offered once within three months if the worker "
                    "is unable to continue.\n"
                    "3. Fees are non-refundable after the visa has been issued."
                ),
            )

            if placement.route == Placement.Route.OVERSEAS:
                placement.medical_on = placement.agreed_on + dt.timedelta(days=7)
                placement.visa_applied_on = placement.agreed_on + dt.timedelta(days=14)
                if status in (Placement.Status.DELIVERED,):
                    placement.visa_issued_on = placement.agreed_on + dt.timedelta(days=30)
                    placement.travel_on = placement.agreed_on + dt.timedelta(days=45)
                    placement.arrival_on = placement.agreed_on + dt.timedelta(days=46)
            elif status == Placement.Status.DELIVERED:
                placement.visa_issued_on = placement.agreed_on + dt.timedelta(days=10)

            placement.save()

            if status != Placement.Status.DRAFT:
                services.set_placement_status(placement, user=owner, status=status)

            # Each placement gets its invoice. A draft placement keeps a draft
            # invoice so the "not yet issued" state is visible in the demo.
            invoice = billing_services.create_invoice(
                tenant=tenant,
                user=owner,
                sponsor=placement.sponsor,
                placement=placement,
                services=list(Service.objects.filter(tenant=tenant, is_active=True)[:6]),
                payment_terms=placement.payment_terms,
                issue_date=placement.agreed_on,
            )
            if status != Placement.Status.DRAFT:
                billing_services.issue_invoice(invoice, user=owner, on=placement.agreed_on)
                if paid:
                    billing_services.record_payment(
                        invoice,
                        user=owner,
                        received_on=placement.agreed_on + dt.timedelta(days=2),
                        amount=invoice.total,
                        method="transfer",
                        reference="Demo settlement",
                    )
                elif status == Placement.Status.PROCESSING:
                    # A deposit taken, balance still outstanding.
                    billing_services.record_payment(
                        invoice,
                        user=owner,
                        received_on=placement.agreed_on,
                        amount=(invoice.total / 2).quantize(Decimal("0.001")),
                        method="cash",
                        reference="Deposit",
                    )
            made += 1

        self.stdout.write(f"  placements created: {made}")
