"""Back-office admin for accounts models."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import LoginAttempt, Membership, User


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    # Membership has two FKs to User (the member, and who invited them), so the
    # inline has to say which one it is listing.
    fk_name = "user"
    autocomplete_fields = ["tenant"]


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["email"]
    list_display = ["email", "full_name", "is_active", "is_staff", "last_login_at"]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    search_fields = ["email", "full_name"]
    inlines = [MembershipInline]
    readonly_fields = ["last_login", "last_login_at", "date_joined"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Profile"), {"fields": ("full_name", "phone", "avatar", "locale")}),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("Dates"), {"fields": ("last_login", "last_login_at", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2")}),
    )


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "is_owner", "is_default", "joined_at"]
    list_filter = ["is_owner", "is_default"]
    search_fields = ["user__email", "tenant__name"]
    autocomplete_fields = ["user", "tenant"]


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ["email", "ip_address", "successful", "created_at"]
    list_filter = ["successful"]
    search_fields = ["email"]
