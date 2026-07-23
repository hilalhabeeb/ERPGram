"""Comments: a generic thread on any document, isolated per tenant.

The model is shared across every commentable doctype, so the tests that matter
are the boundary ones — you can only comment on a commentable document you own,
and one agency's notes never reach another's, at both the ORM and DB layers.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.urls import reverse

from apps.accounts.services import ensure_system_roles
from apps.billing import services as billing
from apps.billing.models import Invoice, Service
from apps.comments.models import Comment
from apps.core.domains import MANPOWER
from apps.core.tenant import activate_tenant
from apps.manpower import services as manpower
from tests.factories import MembershipFactory, TenantFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def agency():
    tenant = TenantFactory(domain=MANPOWER)
    ensure_system_roles(tenant)
    manpower.ensure_reference_data()
    manpower.ensure_tenant_defaults(tenant)
    billing.ensure_billing_defaults(tenant)
    return tenant


def _sign_in(client, tenant):
    user = UserFactory()
    MembershipFactory(user=user, tenant=tenant, is_owner=True, is_default=True)
    client.force_login(user)
    client.post(reverse("accounts:switch_tenant"), {"tenant_id": str(tenant.id)})
    return user


def _invoice(tenant, user):
    with activate_tenant(tenant.id):
        sponsor = manpower.create_sponsor(
            tenant=tenant, user=user, name="Sponsor", national_id="800110011"
        )
        return billing.create_invoice(tenant=tenant, user=user, sponsor=sponsor)


def _add_url(obj) -> str:
    ct = ContentType.objects.get_for_model(obj)
    return reverse("comments:add", args=[ct.id, obj.pk])


# --- adding -----------------------------------------------------------------


def test_a_member_can_comment_on_an_invoice(client, agency):
    user = _sign_in(client, agency)
    invoice = _invoice(agency, user)

    resp = client.post(_add_url(invoice), {"body": "Called the sponsor; paying Sunday."})
    assert resp.status_code == 302

    with activate_tenant(agency.id):
        comment = Comment.objects.get()
        assert comment.body.startswith("Called the sponsor")
        assert comment.created_by_id == user.id
        assert comment.target == invoice  # the generic relation resolves back


def test_an_empty_comment_is_ignored(client, agency):
    user = _sign_in(client, agency)
    invoice = _invoice(agency, user)

    client.post(_add_url(invoice), {"body": "   "})

    with activate_tenant(agency.id):
        assert Comment.objects.count() == 0


def test_htmx_add_returns_the_refreshed_thread(client, agency):
    user = _sign_in(client, agency)
    invoice = _invoice(agency, user)

    resp = client.post(_add_url(invoice), {"body": "Deposit received."}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert b"Deposit received." in resp.content
    assert f'id="comments-{invoice.pk}"'.encode() in resp.content


# --- the boundaries ----------------------------------------------------------


def test_cannot_comment_on_a_non_commentable_document(client, agency):
    """A Service is a real tenant object, but it is not in the allowlist."""
    _sign_in(client, agency)
    with activate_tenant(agency.id):
        service = Service.objects.first()

    ct = ContentType.objects.get_for_model(Service)
    resp = client.post(reverse("comments:add", args=[ct.id, service.pk]), {"body": "x"})
    assert resp.status_code == 404

    with activate_tenant(agency.id):
        assert Comment.objects.count() == 0


def test_cannot_comment_on_another_tenants_invoice(client, agency):
    other = TenantFactory(domain=MANPOWER)
    ensure_system_roles(other)
    manpower.ensure_tenant_defaults(other)
    billing.ensure_billing_defaults(other)
    foreign_invoice = _invoice(other, UserFactory())

    _sign_in(client, agency)  # signed into `agency`, not `other`
    resp = client.post(_add_url(foreign_invoice), {"body": "sneaky"})
    assert resp.status_code == 404  # not found, so we never confirm it exists

    with activate_tenant(other.id):
        assert Comment.objects.filter(object_id=foreign_invoice.pk).count() == 0


# --- deleting ----------------------------------------------------------------


def test_the_author_can_delete_their_comment(client, agency):
    user = _sign_in(client, agency)
    invoice = _invoice(agency, user)
    client.post(_add_url(invoice), {"body": "typo"})
    with activate_tenant(agency.id):
        comment = Comment.objects.get()

    resp = client.post(reverse("comments:delete", args=[comment.pk]))
    assert resp.status_code == 302
    with activate_tenant(agency.id):
        assert Comment.objects.count() == 0


def test_a_non_author_cannot_delete_a_comment(client, agency):
    author = UserFactory()
    invoice = _invoice(agency, author)
    with activate_tenant(agency.id):
        ct = ContentType.objects.get_for_model(Invoice)
        comment = Comment.objects.create(
            tenant=agency,
            content_type=ct,
            object_id=invoice.pk,
            body="not yours",
            created_by=author,
        )

    _sign_in(client, agency)  # a different user
    resp = client.post(reverse("comments:delete", args=[comment.pk]))
    assert resp.status_code == 403
    with activate_tenant(agency.id):
        assert Comment.objects.filter(pk=comment.pk).exists()


# --- safety ------------------------------------------------------------------


def test_comment_body_is_escaped_on_the_page(client, agency):
    user = _sign_in(client, agency)
    invoice = _invoice(agency, user)
    client.post(_add_url(invoice), {"body": "<script>alert('x')</script>"})

    html = client.get(reverse("billing:invoice_detail", args=[invoice.pk])).content
    assert b"<script>alert('x')</script>" not in html  # not injected raw
    assert b"&lt;script&gt;" in html  # rendered as escaped text


# --- isolation, both layers --------------------------------------------------


def _raw_comment_ids() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM comments_comment")
        return {str(row[0]) for row in cursor.fetchall()}


def test_comments_are_isolated_at_both_layers(bind_tenant):
    tenant_a = TenantFactory(domain=MANPOWER)
    tenant_b = TenantFactory(domain=MANPOWER)
    ct = ContentType.objects.get_for_model(Invoice)

    with bind_tenant(tenant_a.id):
        comment_a = Comment.all_tenants.create(
            tenant=tenant_a, content_type=ct, object_id=uuid.uuid4(), body="A's note"
        )

    # Layer 1 (ORM): tenant B's manager cannot see A's comment.
    with bind_tenant(tenant_b.id):
        assert comment_a.id not in set(Comment.objects.values_list("id", flat=True))
        # Layer 2 (RLS): raw SQL under B's GUC does not return A's row either.
        assert str(comment_a.id) not in _raw_comment_ids()

    with bind_tenant(tenant_a.id):
        assert comment_a.id in set(Comment.objects.values_list("id", flat=True))
