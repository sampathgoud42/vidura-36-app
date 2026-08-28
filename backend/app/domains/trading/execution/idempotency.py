"""Guard 1: a duplicate order is impossible to express, not merely unlikely.

The row is written BEFORE the venue is called, and ``UNIQUE(tenant_id,
idempotency_key)`` is what does the work. A second submit does not race a
check — it hits a constraint, and the stored outcome of the first attempt is
returned instead of a second order being placed.

Two keys, because two different things can go wrong:

  the CLIENT key   a caller that sends Idempotency-Key gets exact-once
                   semantics for that gesture
  the FINGERPRINT  a caller that sends nothing still cannot double-submit,
                   because tenant + contract + side + size + a short time
                   bucket hashes to the same value on a double-tap

The fingerprint is deliberately coarse in time and exact in everything else.
Coarse enough that a double-tap collides; exact enough that a deliberate
second order a minute later does not.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.trading.models import ExecutionAttempt
from app.platform.db.base import utcnow

# How long two identical unkeyed requests are treated as the same gesture.
# Long enough to absorb a client timeout and a re-tap; short enough that
# deliberately repeating a trade is not blocked.
FINGERPRINT_WINDOW_S = 90


class DuplicateRequest(Exception):
    """A repeat of an attempt that already exists.

    Carries the ORIGINAL outcome, so the caller answers with what actually
    happened rather than an error. A double-tap should show the operator the
    order they placed, not a failure.
    """

    def __init__(self, attempt: ExecutionAttempt) -> None:
        super().__init__("duplicate request")
        self.attempt = attempt


class KeyReused(Exception):
    """One key, two different intents.

    Answering with the first result would hide a client bug and could show the
    operator an order they did not just ask for, so this is refused loudly.
    """


@dataclass(frozen=True)
class RequestIdentity:
    key: str
    fingerprint: str


def fingerprint(tenant_id: str, intent: str, payload: dict) -> str:
    bucket = int(time.time() // FINGERPRINT_WINDOW_S)
    material = json.dumps(
        {"t": tenant_id, "i": intent, "p": payload, "b": bucket},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()[:48]


def identity(tenant_id: str, intent: str, payload: dict,
             client_key: str | None) -> RequestIdentity:
    fp = fingerprint(tenant_id, intent, payload)
    if not client_key:
        # No client key: the fingerprint IS the key, so an un-updated client
        # gets the same protection as an updated one.
        return RequestIdentity(key=fp, fingerprint=fp)

    # A CLIENT KEY DEFINES THE GESTURE, and then the fingerprint must not also
    # dedupe. Two deliberate orders for the same contract carry the same
    # fingerprint by construction, so leaving it as a second uniqueness key
    # made the second one silently return the first one's result -- an
    # operator who meant to add to a position would be told they already had.
    key = client_key.strip()[:128]
    return RequestIdentity(
        key=key,
        fingerprint=hashlib.sha256(f"{tenant_id}|{key}".encode()).hexdigest()[:48],
    )


def _payload_digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:32]


def begin(db: Session, *, tenant_id: str, intent: str, payload: dict,
          client_key: str | None) -> ExecutionAttempt:
    """Claim this request, or raise because someone already has.

    The INSERT is the claim. Nothing reads-then-writes, so there is no window
    between deciding to act and being the one who acts.
    """
    ident = identity(tenant_id, intent, payload, client_key)
    digest = _payload_digest(payload)

    existing = db.scalar(select(ExecutionAttempt).where(
        ExecutionAttempt.tenant_id == tenant_id,
        ExecutionAttempt.idempotency_key == ident.key,
    ))
    if existing is not None:
        stored = json.loads(existing.response_json or "{}")
        if stored.get("_payload_digest") not in (None, digest):
            raise KeyReused(
                "this Idempotency-Key was already used for a different "
                "request; use a new key for a new order"
            )
        raise DuplicateRequest(existing)

    attempt = ExecutionAttempt(
        tenant_id=tenant_id, idempotency_key=ident.key,
        request_fingerprint=ident.fingerprint, intent=intent,
        status="in_flight",
        response_json=json.dumps({"_payload_digest": digest}),
    )
    db.add(attempt)
    try:
        db.flush()
    except IntegrityError:
        # Lost the race to another process between the SELECT and the INSERT.
        # The constraint caught it, which is the entire point — recover the
        # winner's row and treat this as the duplicate it is.
        db.rollback()
        winner = db.scalar(select(ExecutionAttempt).where(
            ExecutionAttempt.tenant_id == tenant_id,
            ExecutionAttempt.idempotency_key == ident.key,
        )) or db.scalar(select(ExecutionAttempt).where(
            ExecutionAttempt.tenant_id == tenant_id,
            ExecutionAttempt.request_fingerprint == ident.fingerprint,
        ))
        if winner is None:
            raise
        raise DuplicateRequest(winner) from None
    return attempt


def succeed(db: Session, attempt: ExecutionAttempt, *, result: dict,
            position_id: int | None = None,
            venue_order_id: str | None = None) -> None:
    stored = json.loads(attempt.response_json or "{}")
    stored.update(result)
    attempt.status = "succeeded"
    attempt.position_id = position_id
    attempt.venue_order_id = venue_order_id
    attempt.response_json = json.dumps(stored, default=str)
    attempt.completed_at = utcnow()
    db.flush()


def fail(db: Session, attempt: ExecutionAttempt, *, reason: str) -> None:
    """Record the failure and RELEASE the key.

    A failed attempt must not block a retry: the operator's order did not go
    through, and telling them "duplicate" when they try again would be a lie.
    Clearing the key is what makes the retry possible; the fingerprint is left
    in place so an instant double-tap on a failing path is still absorbed.
    """
    attempt.status = "failed"
    attempt.completed_at = utcnow()
    attempt.idempotency_key = f"failed:{attempt.id}"
    stored = json.loads(attempt.response_json or "{}")
    stored["error"] = reason
    attempt.response_json = json.dumps(stored)
    db.flush()


def stored_result(attempt: ExecutionAttempt) -> dict:
    body = json.loads(attempt.response_json or "{}")
    body.pop("_payload_digest", None)
    return body
