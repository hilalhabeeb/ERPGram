"""Login flow: success, bad password, and DB-backed lockout."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import LoginAttempt, Membership
from tests.factories import DEFAULT_PASSWORD, MembershipFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_successful_login_single_tenant_redirects_to_dashboard(client):
    membership = MembershipFactory(is_default=True)
    resp = client.post(
        reverse("accounts:login"),
        {"email": membership.user.email, "password": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 302
    assert resp.url == "/"
    assert client.session["tenant_id"] == str(membership.tenant_id)


def test_wrong_password_is_rejected_and_recorded(client):
    user = UserFactory(email="who@example.test")
    resp = client.post(reverse("accounts:login"), {"email": user.email, "password": "nope"})
    assert resp.status_code == 200  # re-renders with an error
    assert "_auth_user_id" not in client.session
    assert LoginAttempt.objects.filter(email=user.email, successful=False).count() == 1


def test_lockout_after_five_failures(client, settings):
    settings.LOGIN_MAX_ATTEMPTS = 5
    user = UserFactory(email="target@example.test")
    MembershipFactory(user=user)

    for _ in range(5):
        client.post(reverse("accounts:login"), {"email": user.email, "password": "bad"})

    # Even the correct password is refused while locked out.
    resp = client.post(
        reverse("accounts:login"), {"email": user.email, "password": DEFAULT_PASSWORD}
    )
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session


def test_login_case_insensitive_email(client):
    membership = MembershipFactory()
    upper = membership.user.email.upper()
    resp = client.post(reverse("accounts:login"), {"email": upper, "password": DEFAULT_PASSWORD})
    assert resp.status_code == 302
    assert Membership.objects.filter(user=membership.user).exists()
