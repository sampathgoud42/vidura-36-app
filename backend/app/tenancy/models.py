"""Tenancy: who an operator is, what they may open, and their secrets.

Every column here is cited in the Phase 3 evidence table. Anything that could
not be cited is not present.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey,
                        Integer, LargeBinary, String, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base, TenantOwned, Timestamped, tenant_fk


def _uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base, Timestamped):
    """One operator. There is no organisation above this.

    Phase 0 proved it from four independent directions: no tenant column in
    the old user table, one credential folder per person, one password beside
    those credentials, and world access keyed by username.
    """

    __tablename__ = "tenant"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # The username. Phase 3: this IS the natural key, and the wellness
    # profile's uniqueness is expressed through it.
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)

    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Argon2id, never reversible. See Phase 3: a venue key must be decrypted
    # because it is presented to a venue; a password only ever needs
    # comparing, so hashing removes the master key from the blast radius.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_algo: Mapped[str] = mapped_column(String(32), default="argon2id",
                                               nullable=False)
    password_updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    credentials = relationship("TenantCredential", back_populates="tenant",
                               cascade="all, delete-orphan")
    worlds = relationship("TenantWorldAccess", back_populates="tenant",
                          cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status in ('active','suspended')", name="status_known"),
        CheckConstraint("length(slug) > 0", name="slug_not_blank"),
    )


class TenantCredential(Base, TenantOwned, Timestamped):
    """A venue credential, encrypted at rest with envelope encryption.

    Reversible on purpose, unlike the password: the system has to present
    this to Tradier or Kalshi. The plaintext never leaves the decrypt call.
    """

    __tablename__ = "tenant_credential"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = tenant_fk()

    venue: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)

    # Envelope encryption: a per-record data key, itself wrapped by the
    # master key from the environment. key_version says which master key did
    # the wrapping, which is what makes a re-key possible at all.
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_by: Mapped[str | None] = mapped_column(String(64))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime)
    rotated_by: Mapped[str | None] = mapped_column(String(64))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    tenant = relationship("Tenant", back_populates="credentials")

    __table_args__ = (
        UniqueConstraint("tenant_id", "venue", "label", name="tenant_venue_label"),
        CheckConstraint("venue in ('tradier','tradier_sandbox','kalshi')",
                        name="venue_known"),
    )

    def __repr__(self) -> str:
        # Stack traces print locals. A credential that prints itself is a
        # leak waiting for the next unhandled exception.
        return (f"<TenantCredential {self.venue}/{self.label} "
                f"tenant={self.tenant_id} [encrypted]>")


class TenantWorldAccess(Base, TenantOwned, Timestamped):
    """Which tiles this operator may open. Replaces worlds.json.

    A file edit per operator failed the customer onboarding contract; this is
    a runtime write that takes effect on the next request.
    """

    __tablename__ = "tenant_world_access"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = tenant_fk()
    world_key: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tenant = relationship("Tenant", back_populates="worlds")

    __table_args__ = (
        UniqueConstraint("tenant_id", "world_key", name="tenant_world"),
    )


class TenantSecretAudit(Base, TenantOwned):
    """Who changed a credential, and when.

    The one audit table in the schema. It exists because the brief requires
    recording credential changes — not because audit tables are good practice
    in the abstract.
    """

    __tablename__ = "tenant_secret_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()
    credential_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenant_credential.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("action in ('created','rotated','revoked','verified')",
                        name="action_known"),
    )


class WellnessProfile(Base, TenantOwned, Timestamped):
    """Special-category personal data. Never logged, never exported.

    UNIQUE on tenant_id: the operator's username is the unique id you asked
    for, expressed through the tenant rather than duplicated as a string, so
    a rename moves the profile with it instead of orphaning it.
    """

    __tablename__ = "wellness_profile"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id", ondelete="CASCADE"),
        unique=True, nullable=False)

    gender: Mapped[str | None] = mapped_column(String(32))
    # A BAND, not a number: the source file holds "35-44", not 35. Named so
    # that nobody types it INTEGER later and breaks the import on row one.
    age_band: Mapped[str | None] = mapped_column(String(16))
    ethnicity: Mapped[str | None] = mapped_column(String(64))
    diet: Mapped[str | None] = mapped_column(String(64))
    style: Mapped[str | None] = mapped_column(String(32))
    region: Mapped[str | None] = mapped_column(String(64))
    notifications: Mapped[bool] = mapped_column(Boolean, default=False,
                                                nullable=False)

    goals = relationship("WellnessGoal", cascade="all, delete-orphan",
                         order_by="WellnessGoal.position")

    def __repr__(self) -> str:
        return f"<WellnessProfile tenant={self.tenant_id} [private]>"


class WellnessGoal(Base, TenantOwned):
    """One goal. A child table rather than a JSON array, because the value is
    genuinely multi-valued and a blob would make "add a goal" a
    read-modify-write. ``position`` preserves the operator's own order."""

    __tablename__ = "wellness_goal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wellness_profile.id", ondelete="CASCADE"),
        nullable=False)
    goal: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("profile_id", "position", name="profile_goal_order"),
    )
