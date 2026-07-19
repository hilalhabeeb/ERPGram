"""Back-office admin for tenancy models."""

from __future__ import annotations

from django.contrib import admin

from apps.core.admin import AllTenantsAdmin
from apps.tenancy.models import Branch, Company, Department, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "timezone", "default_locale"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Company)
class CompanyAdmin(AllTenantsAdmin):
    list_display = ["name", "tenant", "registration_no", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "legal_name", "registration_no"]


@admin.register(Branch)
class BranchAdmin(AllTenantsAdmin):
    list_display = ["name", "company", "tenant", "code"]
    search_fields = ["name", "code"]


@admin.register(Department)
class DepartmentAdmin(AllTenantsAdmin):
    list_display = ["name", "branch", "tenant", "parent"]
    search_fields = ["name", "code"]
