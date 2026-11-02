"""When a new Google or Apple sign-in may join an existing account by email.

A provider that verified an address has not proven the person controls it: a
Google Workspace admin can make a verified Google account on any address in
their domain, a lapsed domain can be registered again, and an old Google or
Apple account can still carry an address its owner has since lost. So a
sign-in that matches no account by its own provider id joins the account that
holds the same email only when that provider is the address's authority:

- Google for ``@gmail.com`` and ``@googlemail.com``, and for a Workspace
  address whose token's ``hd`` (hosted domain) claim is the address's domain.
- Apple for its relay addresses (``is_private_email``) and for ``@icloud.com``,
  ``@me.com`` and ``@mac.com``.

Otherwise the sign-in is refused with ``AccountExistsError``, which names the
way the account signed in before. Email is unique, so no second account can
be made for the address either.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from app.core.validation import claim_is_true
from app.exceptions import DomainError
from app.models.orm import User

SignInProvider = Literal["google", "apple"]

_GOOGLE_MAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})
_APPLE_MAIL_DOMAINS = frozenset({"icloud.com", "me.com", "mac.com", "privaterelay.appleid.com"})
_PROVIDER_LABELS: dict[SignInProvider, str] = {"google": "Google", "apple": "Apple"}


class AccountExistsError(DomainError):
    """The email belongs to an account this sign-in may not join: 409 ``account_exists``,
    with ``sign_in_with`` naming the way the phone offers instead."""

    status_code = 409
    default_code = "account_exists"

    def __init__(self, sign_in_with: SignInProvider) -> None:
        super().__init__(
            "This email already has a Recall account. Sign in with "
            f"{_PROVIDER_LABELS[sign_in_with]}, the way you signed in before.",
            sign_in_with=sign_in_with,
        )
        self.sign_in_with: SignInProvider = sign_in_with


def _domain(email: str) -> str:
    _, at, domain = email.strip().rpartition("@")
    return domain.lower() if at else ""


def google_owns_email(payload: Mapping[str, Any], email: str) -> bool:
    """Google is the authority for this address (see the module docstring)."""
    domain = _domain(email)
    if not domain:
        return False
    if domain in _GOOGLE_MAIL_DOMAINS:
        return True
    hosted = payload.get("hd")
    return isinstance(hosted, str) and hosted.strip().lower() == domain


def apple_owns_email(payload: Mapping[str, Any], email: str) -> bool:
    """Apple is the authority for this address (see the module docstring)."""
    domain = _domain(email)
    if not domain:
        return False
    return claim_is_true(payload.get("is_private_email")) or domain in _APPLE_MAIL_DOMAINS


def previous_sign_in(existing: User, attempted: SignInProvider) -> SignInProvider:
    """How the account that holds the email signs in: the other provider when
    it is linked, else the same provider with another account of theirs."""
    if attempted == "google":
        return "apple" if existing.apple_sub else "google"
    return "google" if existing.google_sub else "apple"
