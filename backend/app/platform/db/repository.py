"""The tenant-scoped repository — where the isolation guarantee lives.

SQLite has no row-level security, so the database cannot refuse a leaking
query on our behalf. That loss was accepted deliberately in Phase 0, and this
module is what replaces it: the only way a request handler reaches a
tenant-owned table is through an object that was constructed with a tenant,
and one constructed without a tenant raises instead of returning rows.

The rule that matters most is the one that looks smallest:

    if user_id:                     <- the old code. "" and None widened
        stmt = stmt.where(...)         to every tenant.

An absent tenant is not a wider query. It is a bug, and it is treated as one.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.platform.db import registry


class TenantScopeMissing(RuntimeError):
    """Raised when a query would run without a tenant.

    Deliberately not an HTTP error: reaching here means a programming
    mistake, not a bad request. It should surface as a 500 and a loud log
    line, never as something a caller can trigger and shrug at.
    """


class UnscopedModelRefused(RuntimeError):
    """Raised when a tenant-owned model is asked for through the unscoped
    escape hatch."""


def _require_tenant(tenant_id: Any) -> str:
    # str() first: a UUID object is a perfectly good tenant and would fail a
    # naive isinstance check. Whitespace is not — " " is the same class of
    # falsy-adjacent value that "" was, and it must fail the same way.
    if tenant_id is None:
        raise TenantScopeMissing("no tenant in scope")
    text = str(tenant_id).strip()
    if not text:
        raise TenantScopeMissing(f"blank tenant in scope: {tenant_id!r}")
    return text


class TenantRepository:
    """Every read and write for one tenant goes through one of these."""

    def __init__(self, session: Session | None, tenant_id: Any) -> None:
        # Validated at construction AND at use. Construction catches the
        # common case early; use catches an object that was built before the
        # tenant was known and mutated afterwards.
        self._session = session
        self._tenant_id = None if tenant_id is None else str(tenant_id).strip() or None

    @property
    def tenant_id(self) -> str:
        return _require_tenant(self._tenant_id)

    @property
    def session(self) -> Session:
        if self._session is None:
            raise TenantScopeMissing("repository has no session")
        return self._session

    def query(self, model: type | None = None) -> Select:
        """A SELECT that already carries this tenant's predicate.

        There is no way to ask this object for a statement without one, which
        is the difference between a guarantee and a habit.
        """
        tenant = self.tenant_id
        if model is None:
            return select().where(False)  # nothing asked for, nothing returned
        if not registry.is_scope_enforced(model):
            raise UnscopedModelRefused(
                f"{model.__name__} is not tenant-scoped; read it through "
                "market_data() and say so explicitly"
            )
        return select(model).where(model.tenant_id == tenant)

    def get(self, model: type, pk: Any):
        """Fetch by primary key, scoped.

        Returns None for another tenant's row rather than raising, so the
        caller answers 404 — never 403. A 403 confirms the record exists,
        which turns an id into an oracle.
        """
        row = self.session.get(model, pk)
        if row is None:
            return None
        if getattr(row, "tenant_id", None) != self.tenant_id:
            return None
        return row

    def add(self, obj):
        """Writes are stamped, not trusted.

        A caller that sets tenant_id itself is a caller that can set it
        wrong, so the repository overwrites it either way.
        """
        setattr(obj, "tenant_id", self.tenant_id)
        self.session.add(obj)
        return obj


def market_data(session: Session, model: type) -> Select:
    """The enumerated escape hatch, for signals and nothing else.

    Explicit and greppable on purpose: an unscoped read should be visible in
    review, and the registry test asserts the exact set of models allowed
    through here.
    """
    if registry.is_scope_enforced(model):
        raise UnscopedModelRefused(
            f"{model.__name__} is tenant-owned and cannot be read unscoped"
        )
    return select(model)
