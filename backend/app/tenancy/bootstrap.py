"""Creating the first operator, which nothing else can authorise.

Onboarding a customer requires an admin session. Creating the FIRST admin
cannot, because there is no admin yet. That chicken-and-egg is real, and the
honest answer is a narrow, explicit, one-time path rather than pretending the
normal flow covers it.

It is still a runtime call — no file, no migration, no deploy — so it does not
break the customer onboarding contract. It refuses to run once any tenant
exists, so it cannot be used as a back door later.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.platform.db.session import session_scope
from app.tenancy import repository
from app.tenancy.models import Tenant

logger = logging.getLogger(__name__)

DEFAULT_WORLDS = {
    "tradier-platform": True,
    "36-trade-desk": True,
    "bot-station": True,
}


class AlreadyBootstrapped(RuntimeError):
    """Raised when a tenant already exists.

    The whole safety of this path rests on being usable exactly once. If it
    could run again it would be an unauthenticated way to mint an admin.
    """


def create_first_admin(*, slug: str, password: str,
                       display_name: str | None = None,
                       email: str | None = None) -> str:
    """Create the initial admin operator. Returns the tenant id."""
    with session_scope() as db:
        existing = db.scalar(select(func.count()).select_from(Tenant))
        if existing:
            raise AlreadyBootstrapped(
                f"{existing} operator(s) already exist; create further "
                "operators through POST /api/v1/tenants with an admin session"
            )
        tenant = repository.create(
            db, slug=slug, display_name=display_name or slug.title(),
            password=password, email=email, is_admin=True,
        )
        repository.set_worlds(db, tenant, DEFAULT_WORLDS,
                              default="tradier-platform")
        # Deliberately loud, and deliberately without the password. An admin
        # appearing in a system that can place real orders should be visible
        # in the log afterwards.
        logger.warning("bootstrap: created first admin operator '%s' (%s)",
                       tenant.slug, tenant.id)
        return tenant.id


def has_any_tenant() -> bool:
    """Used by the readiness endpoint and the ops runbook: a running system
    with no operators is a system nobody can sign in to."""
    with session_scope() as db:
        return bool(db.scalar(select(func.count()).select_from(Tenant)))
