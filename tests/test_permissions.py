"""Only owners may reach the organisation settings page."""

from __future__ import annotations

import pytest
from django.urls import reverse

from tests.factories import MembershipFactory, UserFactory

pytestmark = pytest.mark.django_db


def _login_with_membership(client, *, is_owner: bool):
    user = UserFactory()
    membership = MembershipFactory(user=user, is_owner=is_owner, is_default=True)
    client.force_login(user)
    client.session["tenant_id"] = str(membership.tenant_id)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(membership.tenant_id)})
    return user, membership


def test_owner_can_open_organization_settings(client):
    _login_with_membership(client, is_owner=True)
    resp = client.get(reverse("ui:settings_organization"))
    assert resp.status_code == 200


def test_non_owner_is_forbidden_from_organization_settings(client):
    _login_with_membership(client, is_owner=False)
    resp = client.get(reverse("ui:settings_organization"))
    assert resp.status_code == 403


def test_anonymous_is_redirected_to_login(client):
    resp = client.get(reverse("ui:settings_profile"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp.url


def test_settings_nav_hides_owner_only_tab_from_members(client):
    """The sub-nav must not advertise a page the member would only get a 403 on."""
    _login_with_membership(client, is_owner=False)
    resp = client.get(reverse("ui:settings_profile"))

    tab_keys = {tab.key for tab in resp.context["tabs"]}
    assert tab_keys == {"profile", "users"}
    assert reverse("ui:settings_organization") not in resp.content.decode()


def test_settings_nav_shows_all_tabs_to_owners(client):
    _login_with_membership(client, is_owner=True)
    resp = client.get(reverse("ui:settings_profile"))

    tab_keys = {tab.key for tab in resp.context["tabs"]}
    assert tab_keys == {"profile", "organization", "users"}


def test_members_do_not_see_the_invite_action(client):
    """Invites are owner-only server-side, so members must not see the button."""
    _login_with_membership(client, is_owner=False)
    resp = client.get(reverse("ui:settings_users"))

    assert resp.status_code == 200
    assert "open-modal-invite" not in resp.content.decode()
