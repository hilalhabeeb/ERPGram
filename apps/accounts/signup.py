"""Public sign-up: create an organisation, pick an industry, become its owner.

This is the only place a tenant is created from outside the back office, so it
is also where a tenant's domain is chosen — the choice decides which modules
exist for that customer from the first login.

Everything happens in one transaction: tenant, owner user, membership, system
roles and the domain's starting data. A half-created tenant would leave someone
looking at a product with no roles to assign and no occupations to pick.
"""

from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import StyledForm
from apps.accounts.models import Membership
from apps.accounts.services import ensure_system_roles
from apps.core.domains import MANPOWER, domain_choices
from apps.manpower import services as manpower_services
from apps.tenancy.models import Tenant

User = get_user_model()


class SignupForm(StyledForm):
    organisation = forms.CharField(label=_lazy("Organisation name"), max_length=200)
    domain = forms.ChoiceField(
        label=_lazy("Industry"),
        choices=domain_choices,
        initial=MANPOWER,
        help_text=_lazy("This decides which modules your organisation gets."),
    )
    full_name = forms.CharField(label=_lazy("Your name"), max_length=200)
    email = forms.EmailField(label=_lazy("Work email"))
    password = forms.CharField(label=_lazy("Password"), widget=forms.PasswordInput, min_length=8)

    def clean_email(self) -> str:
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _("An account with this email already exists. Sign in instead.")
            )
        return email

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        validate_password(password)
        return password


def _unique_slug(name: str) -> str:
    base = slugify(name)[:80] or "org"
    slug = base
    suffix = 2
    while Tenant.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"[:100]
        suffix += 1
    return slug


@transaction.atomic
def create_organisation(
    *, organisation: str, domain: str, full_name: str, email: str, password: str
):
    """Create the tenant, its owner, and whatever the chosen domain needs."""
    tenant = Tenant.objects.create(
        name=organisation.strip(), slug=_unique_slug(organisation), domain=domain
    )

    user = User(email=email, full_name=full_name.strip(), is_active=True)
    user.set_password(password)
    user.save()

    roles = ensure_system_roles(tenant)
    Membership.objects.create(
        user=user, tenant=tenant, is_owner=True, is_default=True, role=roles["owner"]
    )

    if domain == MANPOWER:
        manpower_services.ensure_reference_data()
        manpower_services.ensure_tenant_defaults(tenant, user=user)

    return tenant, user


@require_http_methods(["GET", "POST"])
def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("ui:dashboard")

    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        tenant, user = create_organisation(**form.cleaned_data)
        # The backend must be named explicitly: two are configured, and the user
        # was just created rather than returned by authenticate(), so it carries
        # no `backend` attribute for login() to read.
        login(request, user, backend="apps.accounts.backends.EmailBackend")
        request.session[settings.SESSION_TENANT_KEY] = str(tenant.id)
        return redirect("ui:dashboard")

    return render(request, "accounts/signup.html", {"form": form})
