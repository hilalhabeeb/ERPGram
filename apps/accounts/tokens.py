"""Signed token for invitation / account-activation links.

Subclasses Django's password-reset token generator so the token is bound to the
user's state — once the account is activated (``is_active`` flips to True) the
original activation link stops validating.
"""

from __future__ import annotations

from django.contrib.auth.tokens import PasswordResetTokenGenerator


class ActivationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp: int) -> str:
        return f"{user.pk}{user.is_active}{user.password}{timestamp}"


activation_token = ActivationTokenGenerator()
