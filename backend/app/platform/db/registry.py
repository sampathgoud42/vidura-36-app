"""What the schema knows about itself.

The isolation tests read this rather than a list someone maintains by hand,
so a model added without a tenant is caught by the suite instead of by an
incident.
"""

from __future__ import annotations

from app.platform.db.base import Base, TenantOwned


def _import_all_models() -> None:
    """Every model must be imported before the metadata is complete.

    One place does this, and Alembic uses the same one, so a table cannot be
    in the models and missing from a migration.
    """
    from app.domains.botstation import models as _bot      # noqa: F401
    from app.domains.trading import models as _trading     # noqa: F401
    from app.tenancy import models as _tenancy             # noqa: F401


def all_models() -> list[type]:
    _import_all_models()
    return [m.class_ for m in Base.registry.mappers]


def tenant_owned_models() -> list[type]:
    """Models that carry a tenant and must never be queried unscoped."""
    return [m for m in all_models() if getattr(m, "__tenant_scoped__", False)]


def unscoped_models() -> list[type]:
    """The enumerated exceptions.

    Market data only. Anything else appearing here is a decision someone has
    to defend, which is why the test asserts the exact set rather than a
    count.
    """
    return [m for m in all_models()
            if not getattr(m, "__tenant_scoped__", False)
            and m.__name__ not in _INFRASTRUCTURE]


# Not operator data, and not market data either — these two are the scaffolding
# tenancy is built ON, so asking whether they are "tenant-scoped" is a category
# error rather than a gap:
#
#   Tenant          IS the scope. Its primary key is the tenant id, so a
#                   tenant_id column would be the same value twice and
#                   "scoping" it would mean `WHERE id = id`. Who may LIST
#                   tenants is an authorisation question answered at the edge
#                   (admin session only), not a repository one.
#   ExecutionLease  transient bookkeeping whose resource key already carries
#                   the tenant it belongs to.
#
# Everything else is either tenant-owned or market data. That is the whole
# taxonomy, and unscoped_models() asserts it.
_INFRASTRUCTURE = {"Tenant", "ExecutionLease"}


def is_scope_enforced(model: type) -> bool:
    """True when the model both declares tenancy and has the column to back
    it. A declaration without a column would pass a naive check and leak."""
    if not getattr(model, "__tenant_scoped__", False):
        return False
    if not issubclass(model, TenantOwned):
        return False
    table = getattr(model, "__table__", None)
    if table is None or "tenant_id" not in table.columns:
        return False
    return not table.columns["tenant_id"].nullable
