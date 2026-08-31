"""The declarative base every model in the rebuild inherits from.

Two things are decided here and nowhere else.

CONSTRAINT NAMING. SQLite cannot ALTER a constraint, so Alembic rewrites the
whole table to change one — and it can only do that if every constraint has a
name it can refer to. Unnamed constraints are the reason "just add a column"
migrations fail on SQLite six months later, so the convention is set once,
here, before the first table exists.

TENANT OWNERSHIP. A model declares whether it carries a tenant by inheriting
``TenantOwned``. Nothing infers it from a column name, because a convention
that is inferred is a convention that is silently broken. The registry reads
these declarations, and the isolation tests read the registry.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Naive UTC, one convention, converted only at the edge.

    SQLite does not round-trip tzinfo: an aware datetime goes in and a naive
    one comes back, and comparing the two silently misbehaves. The India
    signal bug in the old build was exactly this. Storing naive UTC
    everywhere means the value that comes back is the value that went in.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Timestamped:
    """created_at / updated_at, on everything that is not a lease."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class TenantOwned:
    """Marks a model as belonging to exactly one tenant.

    Inheriting this is the declaration the whole isolation story rests on:
    it supplies the column, and it is what ``registry`` counts when it
    answers "is every tenant-owned model scope-enforced".
    """

    __tenant_scoped__ = True

    @property
    def _tenant_scope_column(self) -> str:
        return "tenant_id"


def tenant_fk() -> Mapped[str]:
    """The tenant column itself. NOT NULL and a real foreign key, so a row
    without a tenant cannot be written even by a raw INSERT."""
    return mapped_column(
        String(36),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
