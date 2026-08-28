"""Venue credentials in memory: decrypt at the point of use, hold briefly.

The rule from the specification is that a credential is never logged, never
returned by an API, never in an error, a stack trace, a debug dump or a
support export. Most of those are enforced at the edge. Two of them —
tracebacks and log lines that interpolate an object — are enforced HERE, by
making the object refuse to print itself.

That is why every accessor is explicit. Reading ``.token`` is a visible act in
review; a dataclass that renders its fields on ``repr`` is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REDACTED = "[redacted]"


@dataclass(frozen=True)
class VenueCredential:
    """One venue's secret material for one tenant."""

    venue: str
    token: str = field(repr=False)
    account_id: str | None = field(default=None, repr=False)
    base_url: str | None = None
    label: str = "default"
    # Kalshi signs requests with a private key rather than a bearer token.
    private_key_pem: str | None = field(default=None, repr=False)

    # ---- printing: the part that stops the accidental leak ----------------

    def __repr__(self) -> str:
        return f"<VenueCredential {self.venue}/{self.label} {REDACTED}>"

    def __str__(self) -> str:
        return self.__repr__()

    def __format__(self, spec: str) -> str:
        # An f-string with a format spec bypasses __str__ on some types.
        return self.__repr__()

    def public(self) -> dict[str, Any]:
        """What may cross an API boundary or reach a log.

        Deliberately NOT a masked token. The brief rules out
        masked-and-then-unmasked, and a prefix is enough to confirm a guess.
        An operator needs to know a credential EXISTS and when it changed —
        never any part of its value.
        """
        return {
            "venue": self.venue,
            "label": self.label,
            "base_url": self.base_url,
            "has_token": bool(self.token),
            "has_private_key": bool(self.private_key_pem),
            "account_id_present": bool(self.account_id),
        }


@dataclass(frozen=True)
class CredentialMetadata:
    """What a listing returns: enough to manage, nothing to use."""

    credential_id: str
    venue: str
    label: str
    key_version: int
    created_at: Any
    created_by: str | None
    rotated_at: Any = None
    rotated_by: str | None = None
    revoked_at: Any = None

    @property
    def active(self) -> bool:
        return self.revoked_at is None
