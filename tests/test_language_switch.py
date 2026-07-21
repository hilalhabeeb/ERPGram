"""Switching language must work in both directions.

Arabic -> English used to be impossible: the switcher posted the current
`/ar/...` path as `next`, and `set_language` (which lives outside i18n_patterns,
where prefix_default_language=False forces English) could no longer resolve that
path, so Django returned it untranslated and redirected the user straight back
to the Arabic page.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.services import ensure_system_roles
from apps.core.domains import MANPOWER
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client):
    tenant = TenantFactory(domain=MANPOWER)
    ensure_system_roles(tenant)
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=True, is_default=True)
    client.force_login(user)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant.id)})
    return user


def _switch(client, *, language: str, next_url: str):
    return client.post(
        reverse("set_language"),
        {"language": language, "next": next_url},
        HTTP_REFERER=next_url,
    )


def test_language_links_carry_the_translated_url(client, signed_in):
    """The switcher's `next` is pre-translated while the right language is active."""
    response = client.get("/ar/workers/")
    links = {link["code"]: link for link in response.context["language_links"]}

    assert links["ar"]["url"] == "/ar/workers/"
    assert links["en"]["url"] == "/workers/"
    assert links["ar"]["is_current"] is True


def test_switching_from_arabic_to_english_leaves_the_arabic_url(client, signed_in):
    response = _switch(client, language="en", next_url="/workers/")

    assert response.status_code == 302
    assert response.url == "/workers/"

    page = client.get(response.url)
    assert page.context["LANGUAGE_CODE"] == "en"


def test_switching_from_english_to_arabic_reaches_the_arabic_url(client, signed_in):
    response = _switch(client, language="ar", next_url="/ar/workers/")

    assert response.status_code == 302
    assert response.url == "/ar/workers/"

    page = client.get(response.url)
    assert page.context["LANGUAGE_CODE"] == "ar"


def test_round_trip_returns_to_english(client, signed_in):
    """ar -> en -> ar -> en, the sequence that used to get stuck in Arabic."""
    for language, target in (("ar", "/ar/workers/"), ("en", "/workers/"), ("ar", "/ar/workers/")):
        assert _switch(client, language=language, next_url=target).url == target

    final = _switch(client, language="en", next_url="/workers/")
    assert final.url == "/workers/"
    assert client.get(final.url).context["LANGUAGE_CODE"] == "en"


def test_language_switcher_is_available_before_signing_in(client):
    """The login page carries the switcher too, so anonymous users can change it."""
    response = client.get(reverse("accounts:login"))
    codes = {link["code"] for link in response.context["language_links"]}
    assert codes == {"en", "ar"}
