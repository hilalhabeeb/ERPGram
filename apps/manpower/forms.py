"""Manpower forms.

Every tenant-owned choice list (occupation, skill, agent, accommodation) is
bound to an explicit tenant queryset. Country and Language are shared reference
data and are filtered only for relevance, not isolation.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.billing.models import TermsTemplate
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
)


class TenantScopedModelForm(forms.ModelForm):
    """ModelForm that narrows tenant-owned relations to one tenant."""

    tenant_fields: dict[str, type] = {}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        for field_name, model in self.tenant_fields.items():
            # A missing field or model is a declaration error, not a runtime one:
            # skip rather than raising AttributeError deep in form construction.
            if model is None or field_name not in self.fields:
                continue
            queryset = model.all_tenants.filter(tenant=tenant)
            if hasattr(model, "is_active"):
                queryset = queryset.filter(is_active=True)
            # Use each model's own Meta.ordering rather than assuming a `name`
            # field — Worker sorts by full_name, and hard-coding "name" here
            # raised FieldError the moment a Worker relation was scoped.
            self.fields[field_name].queryset = queryset.order_by(*model._meta.ordering or ["pk"])
        _style(self)


def _style(form: forms.BaseForm) -> None:
    """Apply the design-system control classes (mirrors apps.accounts.forms)."""
    mapping = {
        forms.Select: "select",
        forms.SelectMultiple: "select",
        forms.Textarea: "textarea",
        forms.CheckboxInput: "checkbox",
        forms.CheckboxSelectMultiple: "",
        forms.ClearableFileInput: "file-input",
        forms.FileInput: "file-input",
        forms.DateInput: "input",
    }
    for field in form.fields.values():
        widget = field.widget
        css = mapping.get(type(widget), "input")
        if not css:
            continue
        existing = widget.attrs.get("class", "")
        widget.attrs["class"] = f"{existing} {css}".strip()


class WorkerForm(TenantScopedModelForm):
    tenant_fields = {
        "occupation": Occupation,
        "agent": Agent,
        "accommodation": Accommodation,
        "skills": Skill,
    }

    class Meta:
        model = Worker
        fields = [
            "full_name",
            "photo",
            "gender",
            "date_of_birth",
            "nationality",
            "religion",
            "marital_status",
            "children",
            "occupation",
            "skills",
            "languages",
            "experience_years",
            "experience_notes",
            "passport_no",
            "passport_expiry",
            "availability",
            "location",
            "agent",
            "accommodation",
            "monthly_salary",
            "available_from",
            "notes",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "passport_expiry": forms.DateInput(attrs={"type": "date"}),
            "available_from": forms.DateInput(attrs={"type": "date"}),
            "experience_notes": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "skills": forms.CheckboxSelectMultiple,
            "languages": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only countries marked as recruitment sources are offered as a
        # nationality; the GCC states in the table are placement destinations.
        self.fields["nationality"].queryset = Country.objects.filter(is_source=True)
        self.fields["languages"].queryset = Language.objects.all()


class SponsorForm(TenantScopedModelForm):
    class Meta:
        model = Sponsor
        fields = [
            "name",
            "name_ar",
            "kind",
            "national_id",
            "cr_number",
            "phone",
            "email",
            "area",
            "address",
            "household_size",
            "notes",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class PlacementForm(TenantScopedModelForm):
    """Open a placement. Route is derived from the worker, never chosen here."""

    tenant_fields = {"sponsor": Sponsor, "worker": Worker}

    class Meta:
        model = Placement
        fields = ["sponsor", "worker", "visa_period_months", "agreed_on", "payment_terms", "notes"]
        widgets = {
            "agreed_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only workers who can actually be offered. The one already on this
        # placement stays selectable so editing does not silently drop it.
        offerable = Worker.all_tenants.filter(
            tenant=self.tenant, is_active=True, availability=Worker.Availability.AVAILABLE
        )
        if self.instance and self.instance.pk:
            offerable = offerable | Worker.all_tenants.filter(pk=self.instance.worker_id)
        self.fields["worker"].queryset = offerable.select_related("occupation").order_by(
            "full_name"
        )
        self.fields["worker"].label_from_instance = lambda worker: (
            f"{worker.reference} · {worker.full_name} · {worker.occupation.name}"
        )


class PlacementAgreementForm(TenantScopedModelForm):
    """Contract dates and the agreement wording. Money lives on the invoice."""

    terms_template = forms.ModelChoiceField(
        label=_("Insert terms template"),
        queryset=TermsTemplate.objects.none(),
        required=False,
        help_text=_(
            "Copies the template text below. Editing it later will not change this agreement."
        ),
    )

    class Meta:
        model = Placement
        fields = ["contract_start", "contract_end", "payment_terms", "terms", "notes"]
        widgets = {
            "contract_start": forms.DateInput(attrs={"type": "date"}),
            "contract_end": forms.DateInput(attrs={"type": "date"}),
            "terms": forms.Textarea(attrs={"rows": 6}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["terms_template"].queryset = TermsTemplate.objects.filter(
            tenant=self.tenant, is_active=True
        ).exclude(applies_to=TermsTemplate.Applies.INVOICE)

    def clean(self):
        cleaned = super().clean()
        # Choosing a template copies its text in, unless terms were typed.
        template = cleaned.get("terms_template")
        if template and not (cleaned.get("terms") or "").strip():
            cleaned["terms"] = template.body
        cleaned.pop("terms_template", None)
        return cleaned


class PlacementPipelineForm(TenantScopedModelForm):
    """The milestone dates the office fills in as processing moves along."""

    class Meta:
        model = Placement
        fields = [
            "agreed_on",
            "medical_on",
            "visa_applied_on",
            "visa_issued_on",
            "travel_on",
            "arrival_on",
            "delivered_on",
        ]
        widgets = {
            field: forms.DateInput(attrs={"type": "date"})
            for field in [
                "agreed_on",
                "medical_on",
                "visa_applied_on",
                "visa_issued_on",
                "travel_on",
                "arrival_on",
                "delivered_on",
            ]
        }


class OccupationForm(TenantScopedModelForm):
    class Meta:
        model = Occupation
        fields = ["name", "code", "description"]


class SkillForm(TenantScopedModelForm):
    class Meta:
        model = Skill
        fields = ["name"]


class AgentForm(TenantScopedModelForm):
    class Meta:
        model = Agent
        fields = ["name", "country", "contact_person", "phone", "email", "licence_no", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["country"].queryset = Country.objects.filter(is_source=True)


class AccommodationForm(TenantScopedModelForm):
    class Meta:
        model = Accommodation
        fields = ["name", "address", "capacity", "supervisor", "phone"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}


class DocumentTypeForm(TenantScopedModelForm):
    class Meta:
        model = DocumentType
        fields = ["name", "has_expiry"]


SETUP_FORMS = {
    "occupations": (Occupation, OccupationForm, _("Occupations")),
    "skills": (Skill, SkillForm, _("Skills")),
    "agents": (Agent, AgentForm, _("Agents")),
    "accommodation": (Accommodation, AccommodationForm, _("Accommodation")),
    "document-types": (DocumentType, DocumentTypeForm, _("Document types")),
}
