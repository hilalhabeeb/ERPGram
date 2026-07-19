"""Forms for the organisation structure.

Two things matter here beyond field definitions:

1. Every foreign-key choice list is bound to an explicit tenant/parent queryset.
   The tenant-filtered default manager already scopes reads, but a form is the
   one place where another tenant's names would become *visible* in a <select>,
   so the narrowing is written out rather than inherited.
2. ``parent`` on a department is a self-FK, so a department can be made its own
   ancestor. That corrupts every tree walk, so it is rejected at validation.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.accounts.forms import StyledForm
from apps.tenancy.models import Branch, Company, Department


class CompanyForm(StyledForm):
    name = forms.CharField(label=_("Company name"), max_length=200)
    legal_name = forms.CharField(label=_("Legal name"), max_length=200, required=False)
    registration_no = forms.CharField(label=_("Registration no."), max_length=100, required=False)


class BranchForm(StyledForm):
    name = forms.CharField(label=_("Branch name"), max_length=200)
    code = forms.CharField(label=_("Code"), max_length=40, required=False)
    address = forms.CharField(label=_("Address"), required=False, widget=forms.Textarea)


class DepartmentForm(StyledForm):
    name = forms.CharField(label=_("Department name"), max_length=200)
    code = forms.CharField(label=_("Code"), max_length=40, required=False)
    parent = forms.ModelChoiceField(
        label=_("Parent department"),
        queryset=Department.objects.none(),
        required=False,
        empty_label=_("None (top level)"),
    )

    def __init__(self, *args, branch: Branch, instance: Department | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.instance = instance

        # Only departments of this branch may be a parent. Excluding the record
        # itself stops the most obvious cycle before validation has to.
        choices = Department.objects.filter(branch=branch, is_active=True)
        if instance is not None:
            choices = choices.exclude(pk=instance.pk)
        self.fields["parent"].queryset = choices.order_by("name")

    def clean_parent(self) -> Department | None:
        parent = self.cleaned_data.get("parent")
        if parent is None or self.instance is None:
            return parent

        # Walk up from the proposed parent: meeting ourselves means this edit
        # would create a cycle (A -> B -> A), which would hang any tree walk.
        seen: set = set()
        node: Department | None = parent
        while node is not None:
            if node.pk == self.instance.pk:
                raise forms.ValidationError(
                    _("A department cannot be moved under itself or one of its own children.")
                )
            if node.pk in seen:  # pre-existing bad data — stop rather than loop forever
                break
            seen.add(node.pk)
            node = node.parent

        return parent


class ArchiveForm(forms.Form):
    """Deliberately empty: archiving is a POST with CSRF, not a GET link."""


def company_choices(tenant) -> forms.ModelChoiceField:
    """Helper for future modules that need a tenant-scoped company picker."""
    return forms.ModelChoiceField(
        queryset=Company.objects.filter(tenant=tenant, is_active=True).order_by("name"),
        label=_("Company"),
    )
