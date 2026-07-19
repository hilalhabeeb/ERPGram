"""factory-boy factories for the non-tenant-scoped models.

Tenant-scoped rows (Company/Branch/Department) are created inside an
``activate_tenant`` block in the tests that need them, because inserting them
requires the database GUC to be set (FORCE ROW LEVEL SECURITY).
"""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model

from apps.accounts.models import Membership
from apps.tenancy.models import Tenant

User = get_user_model()

DEFAULT_PASSWORD = "test-pass-123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.test")
    full_name = factory.Faker("name")
    is_active = True

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or DEFAULT_PASSWORD)
        if create:
            obj.save()


class TenantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tenant

    name = factory.Sequence(lambda n: f"Tenant {n}")
    slug = factory.Sequence(lambda n: f"tenant-{n}")
    is_active = True


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    tenant = factory.SubFactory(TenantFactory)
    is_owner = False
    is_default = True
