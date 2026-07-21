"""Manpower forms.

Every tenant-owned choice list (occupation, skill, agent, accommodation) is
bound to an explicit tenant queryset. Country and Language are shared reference
data and are filtered only for relevance, not isolation.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

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


class TenantScopedModelForm(forms.ModelForm):
    """ModelForm that narrows tenant-owned relations to one tenant."""

    tenant_fields: dict[str, type] = {}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        for field_name, model in self.tenant_fields.items():
            if field_name not in self.fields:
                continue
            queryset = model.all_tenants.filter(tenant=tenant)
            if hasattr(model, "is_active"):
                queryset = queryset.filter(is_active=True)
            self.fields[field_name].queryset = queryset.order_by("name")
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
