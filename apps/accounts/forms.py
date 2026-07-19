"""Auth and profile forms. Styling is applied via a shared base widget mixin."""

from __future__ import annotations

from zoneinfo import available_timezones

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.utils.translation import gettext_lazy as _

User = get_user_model()

# Widget -> component class. The shapes themselves live in static/src/input.css
# so templates and forms share one definition of a "control".
_WIDGET_CLASS = {
    forms.Select: "select",
    forms.SelectMultiple: "select",
    forms.Textarea: "textarea",
    forms.CheckboxInput: "checkbox",
    forms.ClearableFileInput: "file-input",
    forms.FileInput: "file-input",
}
_DEFAULT_WIDGET_CLASS = "input"


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_styles(self)


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_styles(self)


def _apply_input_styles(form: forms.BaseForm) -> None:
    """Give every widget its design-system class.

    Error styling is handled by the field partial (a wrapper class), not here —
    touching ``form.errors`` during ``__init__`` would force validation early.
    """
    for field in form.fields.values():
        widget = field.widget
        # Exact type lookup keeps the mapping predictable across widget subclasses.
        css = _WIDGET_CLASS.get(type(widget), _DEFAULT_WIDGET_CLASS)
        existing = widget.attrs.get("class", "")
        widget.attrs["class"] = f"{existing} {css}".strip()


class LoginForm(StyledForm):
    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class InviteForm(StyledForm):
    full_name = forms.CharField(label=_("Full name"), max_length=200)
    email = forms.EmailField(label=_("Email"))
    is_owner = forms.BooleanField(label=_("Grant owner access"), required=False)


class ActivateForm(SetPasswordForm):
    """Reuses Django's password-confirmation validation for activation."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        _apply_input_styles(self)


class StyledPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_styles(self)


class StyledSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_styles(self)


class ProfileForm(StyledModelForm):
    class Meta:
        model = User
        fields = ["full_name", "phone", "avatar", "locale"]
        labels = {
            "full_name": _("Full name"),
            "phone": _("Phone"),
            "avatar": _("Avatar"),
            "locale": _("Language"),
        }


# Curated rather than the full ~600-zone tzdata list: the Gulf first, then the
# regions this product is actually sold into. Values are validated against
# zoneinfo, so a hand-edited POST still can't store a bogus zone.
COMMON_TIMEZONES = [
    "Asia/Bahrain",
    "Asia/Riyadh",
    "Asia/Kuwait",
    "Asia/Qatar",
    "Asia/Dubai",
    "Asia/Muscat",
    "Asia/Baghdad",
    "Asia/Amman",
    "Asia/Beirut",
    "Africa/Cairo",
    "Europe/Istanbul",
    "Europe/London",
    "Europe/Paris",
    "Asia/Karachi",
    "Asia/Kolkata",
    "Asia/Singapore",
    "UTC",
]


class OrganizationForm(StyledForm):
    name = forms.CharField(label=_("Organisation name"), max_length=200)
    timezone = forms.ChoiceField(
        label=_("Timezone"),
        choices=[(tz, tz.replace("_", " ")) for tz in COMMON_TIMEZONES],
    )
    default_locale = forms.ChoiceField(
        label=_("Default language"),
        choices=[("en", _("English")), ("ar", _("العربية"))],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep a tenant's existing zone selectable even if it is outside the
        # curated list, so opening the form can never silently change it.
        current = (self.initial or {}).get("timezone")
        if current and current not in COMMON_TIMEZONES:
            self.fields["timezone"].choices = [
                (current, current.replace("_", " ")),
                *self.fields["timezone"].choices,
            ]

    def clean_timezone(self) -> str:
        value = self.cleaned_data["timezone"]
        if value not in available_timezones():
            raise forms.ValidationError(_("Unknown timezone."))
        return value
