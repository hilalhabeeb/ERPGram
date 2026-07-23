"""Shell-level UI concerns: the global confirmation dialog.

Destructive actions must warn before they fire, through one dialog rather than a
scatter of native confirm() calls. The behaviour is JS, but these pin the two
things a template must get right: the dialog is mounted, and destructive forms
carry the data-confirm attribute that routes them through it.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.services import ensure_system_roles
from apps.core.domains import MANPOWER
from apps.core.tenant import activate_tenant
from apps.manpower import services as manpower
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


def _sign_in(client, tenant):
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=True, is_default=True)
    client.force_login(user)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant.id)})
    return user


def test_confirm_dialog_is_mounted_on_every_shell_page(client):
    tenant = TenantFactory(domain=MANPOWER)
    ensure_system_roles(tenant)
    _sign_in(client, tenant)

    html = client.get(reverse("ui:dashboard")).content.decode()
    assert 'Alpine.store("confirm"' in html  # available app-wide


def test_a_destructive_action_carries_a_confirmation(client):
    tenant = TenantFactory(domain=MANPOWER)
    ensure_system_roles(tenant)
    manpower.ensure_reference_data()
    manpower.ensure_tenant_defaults(tenant)
    user = _sign_in(client, tenant)
    with activate_tenant(tenant.id):
        manpower.create_sponsor(tenant=tenant, user=user, name="Household X", national_id="123")

    html = client.get(reverse("manpower:sponsor_list")).content.decode()
    assert "data-confirm" in html  # archiving a sponsor warns first
