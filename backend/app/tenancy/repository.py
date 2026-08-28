"""Tenant records: create, find, authenticate, and hold credentials.

``Tenant`` is the one table read without a tenant predicate, because its
primary key IS the tenant — scoping it would mean ``WHERE id = id``. Who may
LIST tenants is an authorisation question answered at the edge (admin session
only), not a repository one. The registry records that exemption explicitly so
it is a decision rather than an oversight.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.platform.db.base import utcnow
from app.platform.db.session import session_scope
from app.platform.security import passwords
from app.platform.security.envelope import Keyring, Sealed, seal, unseal
from app.tenancy.credentials import CredentialMetadata, VenueCredential
from app.tenancy.models import (Tenant, TenantCredential, TenantSecretAudit,
                                TenantWorldAccess)


class TenantExists(ValueError):
    pass


class TenantNotFound(LookupError):
    pass


# ---- lookup ---------------------------------------------------------------

def by_slug(db: Session, slug: str) -> Tenant | None:
    """Case-insensitive, because operators type their own name inconsistently
    and a login that depends on capitalisation is a support ticket."""
    return db.scalar(
        select(Tenant).where(func.lower(Tenant.slug) == slug.strip().lower())
    )


def by_id(db: Session, tenant_id: str) -> Tenant | None:
    return db.get(Tenant, tenant_id)


def list_all(db: Session) -> list[Tenant]:
    return list(db.scalars(select(Tenant).order_by(Tenant.created_at)).all())


# ---- creation -------------------------------------------------------------

def create(db: Session, *, slug: str, display_name: str, password: str,
           email: str | None = None, is_admin: bool = False) -> Tenant:
    """Onboard a customer. One INSERT, no file, no migration, no restart."""
    slug = slug.strip().lower()
    if not slug:
        raise ValueError("slug must not be empty")
    if by_slug(db, slug) is not None:
        raise TenantExists(f"operator '{slug}' already exists")

    tenant = Tenant(
        slug=slug,
        display_name=display_name.strip() or slug,
        email=email,
        password_hash=passwords.hash_password(password),
        password_algo=passwords.algorithm(),
        password_updated_at=utcnow(),
        is_admin=is_admin,
        status="active",
    )
    db.add(tenant)
    db.flush()
    return tenant


def set_password(db: Session, tenant: Tenant, password: str) -> None:
    tenant.password_hash = passwords.hash_password(password)
    tenant.password_algo = passwords.algorithm()
    tenant.password_updated_at = utcnow()


def authenticate(db: Session, slug: str, password: str) -> Tenant | None:
    """Verify a login. Returns None for every kind of failure.

    One answer for "no such operator", "wrong password" and "suspended" on
    purpose: the login screen must not confirm who exists. The equal-time
    guarantee lives in ``passwords.verify_password``, and the branch below
    calls it even when there is no tenant so the timing matches.
    """
    tenant = by_slug(db, slug)
    if tenant is None:
        # Burn the same time a real verification costs. Without this, a
        # missing operator answers measurably faster than a wrong password.
        passwords.verify_password(_DUMMY_HASH, password)
        return None
    if tenant.status != "active":
        passwords.verify_password(_DUMMY_HASH, password)
        return None
    if not passwords.verify_password(tenant.password_hash, password):
        return None

    # The only moment the plaintext exists, so the only moment the cost can
    # be raised without locking anyone out.
    if passwords.needs_rehash(tenant.password_hash):
        set_password(db, tenant, password)
    return tenant


# A real Argon2id hash of a value nobody knows, so the no-such-operator path
# does the same work as the real one instead of merely sleeping.
_DUMMY_HASH = passwords.hash_password("not-a-real-password-timing-equaliser")


def password_hash_for(slug: str) -> str:
    """The stored hash, for tests and the ops runbook to inspect.

    Returns the ENCODED HASH, never anything reversible — which is the point
    the test asserts.
    """
    with session_scope() as db:
        tenant = by_slug(db, slug)
        if tenant is None:
            raise TenantNotFound(slug)
        return tenant.password_hash


# ---- world access ---------------------------------------------------------

def set_worlds(db: Session, tenant: Tenant, worlds: dict[str, bool],
               default: str | None = None) -> None:
    """Replaces worlds.json. A runtime write, effective on the next request."""
    existing = {w.world_key: w for w in db.scalars(
        select(TenantWorldAccess).where(
            TenantWorldAccess.tenant_id == tenant.id)).all()}
    for key, enabled in worlds.items():
        row = existing.get(key)
        if row is None:
            row = TenantWorldAccess(tenant_id=tenant.id, world_key=key)
            db.add(row)
        row.enabled = bool(enabled)
        row.is_default = (key == default)
    db.flush()


def worlds_for(db: Session, tenant: Tenant) -> dict:
    rows = db.scalars(select(TenantWorldAccess).where(
        TenantWorldAccess.tenant_id == tenant.id)).all()
    worlds = {r.world_key: r.enabled for r in rows}
    default = next((r.world_key for r in rows if r.is_default and r.enabled), None)
    return {"worlds": worlds, "default": default,
            "any_enabled": any(worlds.values())}


# ---- credentials ----------------------------------------------------------

def _aad(tenant_id: str, venue: str) -> bytes:
    """Binds ciphertext to its owner.

    With this, a row copied into another tenant's record fails to decrypt
    rather than silently working — a database-level tamper is caught by the
    cipher, not by our own checks.
    """
    return f"{tenant_id}|{venue}".encode("utf-8")


def store_credential(db: Session, tenant: Tenant, *, venue: str, label: str,
                     secret: dict, keyring: Keyring, actor: str) -> TenantCredential:
    import json

    sealed = seal(json.dumps(secret, separators=(",", ":")).encode("utf-8"),
                  keyring, aad=_aad(tenant.id, venue))
    row = TenantCredential(
        tenant_id=tenant.id, venue=venue, label=label,
        ciphertext=sealed.ciphertext, wrapped_dek=sealed.wrapped_dek,
        nonce=sealed.nonce, key_version=sealed.key_version,
        created_by=actor,
    )
    db.add(row)
    db.add(TenantSecretAudit(tenant_id=tenant.id, credential_id=None,
                             action="created", actor=actor, at=utcnow()))
    db.flush()
    return row


def rotate_credential(db: Session, row: TenantCredential, *, secret: dict,
                      keyring: Keyring, actor: str) -> TenantCredential:
    """Replace the material without downtime. The old value is overwritten,
    not versioned — keeping a superseded credential readable is a liability,
    not a feature."""
    import json

    sealed = seal(json.dumps(secret, separators=(",", ":")).encode("utf-8"),
                  keyring, aad=_aad(row.tenant_id, row.venue))
    row.ciphertext = sealed.ciphertext
    row.wrapped_dek = sealed.wrapped_dek
    row.nonce = sealed.nonce
    row.key_version = sealed.key_version
    row.rotated_at = utcnow()
    row.rotated_by = actor
    db.add(TenantSecretAudit(tenant_id=row.tenant_id, credential_id=row.id,
                             action="rotated", actor=actor, at=utcnow()))
    db.flush()
    return row


def revoke_credential(db: Session, row: TenantCredential, *, actor: str) -> None:
    row.revoked_at = utcnow()
    db.add(TenantSecretAudit(tenant_id=row.tenant_id, credential_id=row.id,
                             action="revoked", actor=actor, at=utcnow()))
    db.flush()


def load_credential(db: Session, tenant_id: str, venue: str,
                    keyring: Keyring, label: str = "default") -> VenueCredential:
    """Decrypt at the point of use. Callers hold the result briefly."""
    import json

    row = db.scalar(select(TenantCredential).where(
        TenantCredential.tenant_id == tenant_id,
        TenantCredential.venue == venue,
        TenantCredential.label == label,
        TenantCredential.revoked_at.is_(None),
    ))
    if row is None:
        raise TenantNotFound(f"no active {venue} credential for this operator")

    payload = json.loads(unseal(
        Sealed(row.ciphertext, row.wrapped_dek, row.nonce, row.key_version),
        keyring, aad=_aad(tenant_id, venue),
    ).decode("utf-8"))
    return VenueCredential(
        venue=venue, label=label,
        token=payload.get("token", ""),
        account_id=payload.get("account_id"),
        base_url=payload.get("base_url"),
        private_key_pem=payload.get("private_key_pem"),
    )


def list_credentials(db: Session, tenant_id: str) -> list[CredentialMetadata]:
    """Metadata only. The secret is not read, so it cannot be leaked here."""
    rows = db.scalars(select(TenantCredential).where(
        TenantCredential.tenant_id == tenant_id).order_by(
        TenantCredential.created_at)).all()
    return [
        CredentialMetadata(
            credential_id=r.id, venue=r.venue, label=r.label,
            key_version=r.key_version, created_at=r.created_at,
            created_by=r.created_by, rotated_at=r.rotated_at,
            rotated_by=r.rotated_by, revoked_at=r.revoked_at,
        )
        for r in rows
    ]
