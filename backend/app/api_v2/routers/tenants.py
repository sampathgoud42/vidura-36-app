"""Customer administration — the endpoints that make onboarding a runtime act.

Onboarding a customer used to mean creating a folder, writing a .env, a .pem
and a .sam, and editing worlds.json. Every one of those is a deploy, and
rotating a key was a deploy too. These endpoints are what replace all of it:
three writes, no file, no migration, no restart.

Everything here needs an admin session, and a non-admin gets 404 rather than
403 — a 403 confirms the admin surface exists and that they found it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from app.api_v2 import deps
from app.platform.security import sessions as session_store
from app.platform.security.envelope import Keyring
from app.tenancy import repository as tenants
from app.tenancy.models import Tenant, TenantCredential

router = APIRouter(prefix="/tenants", tags=["tenancy"])


class TenantCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=128)
    password: str = Field(min_length=8, max_length=256)
    email: str | None = None
    is_admin: bool = False


class TenantPatch(BaseModel):
    display_name: str | None = None
    email: str | None = None
    status: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


class WorldsPut(BaseModel):
    worlds: dict[str, bool]
    default: str | None = None


class CredentialCreate(BaseModel):
    venue: str
    label: str = "default"
    # A free-form bag on purpose: Tradier needs a token and an account id,
    # Kalshi needs a key id and a PEM. Naming every field here would mean
    # editing this model to add a venue.
    secret: dict


class CredentialRotate(BaseModel):
    secret: dict


def _out(t: Tenant) -> dict:
    """Never includes the password hash. The listing is for management."""
    return {"tenant_id": t.id, "slug": t.slug, "display_name": t.display_name,
            "email": t.email, "status": t.status, "is_admin": t.is_admin,
            "created_at": t.created_at}


# ---- operators ------------------------------------------------------------

@router.get("", operation_id="listTenants")
def list_tenants(_: Tenant = Depends(deps.require_admin),
                 db: DbSession = Depends(deps.get_db)) -> list[dict]:
    return [_out(t) for t in tenants.list_all(db)]


@router.post("", status_code=status.HTTP_201_CREATED, operation_id="createTenant")
def create_tenant(payload: TenantCreate,
                  admin: Tenant = Depends(deps.require_admin),
                  db: DbSession = Depends(deps.get_db)) -> dict:
    try:
        tenant = tenants.create(
            db, slug=payload.slug, display_name=payload.display_name or payload.slug,
            password=payload.password, email=payload.email,
            is_admin=payload.is_admin,
        )
    except tenants.TenantExists as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=str(exc)) from exc
    db.commit()
    return _out(tenant)


@router.patch("/{tenant_id}", operation_id="updateTenant")
def update_tenant(tenant_id: str, payload: TenantPatch,
                  admin: Tenant = Depends(deps.require_admin),
                  db: DbSession = Depends(deps.get_db)) -> dict:
    tenant = tenants.by_id(db, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Not found")

    if payload.display_name is not None:
        tenant.display_name = payload.display_name
    if payload.email is not None:
        tenant.email = payload.email
    if payload.status is not None:
        if payload.status not in ("active", "suspended"):
            raise HTTPException(status_code=422, detail="status must be active or suspended")
        tenant.status = payload.status
        if payload.status == "suspended":
            # Revocation that leaves live sessions behind does not revoke.
            session_store.revoke_all_for(tenant.id)
    if payload.password is not None:
        tenants.set_password(db, tenant, payload.password)
        # A password change signs the operator out everywhere: the old
        # password's sessions must not outlive it.
        session_store.revoke_all_for(tenant.id)

    db.commit()
    return _out(tenant)


@router.put("/{tenant_id}/worlds", operation_id="setTenantWorlds")
def set_worlds(tenant_id: str, payload: WorldsPut,
               admin: Tenant = Depends(deps.require_admin),
               db: DbSession = Depends(deps.get_db)) -> dict:
    tenant = tenants.by_id(db, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.default and not payload.worlds.get(payload.default):
        raise HTTPException(
            status_code=422,
            detail=f"default world '{payload.default}' is not one this "
                   "operator may open",
        )
    tenants.set_worlds(db, tenant, payload.worlds, payload.default)
    db.commit()
    return tenants.worlds_for(db, tenant)


# ---- credentials ----------------------------------------------------------

@router.get("/{tenant_id}/credentials", operation_id="listTenantCredentials")
def list_credentials(tenant_id: str,
                     admin: Tenant = Depends(deps.require_admin),
                     db: DbSession = Depends(deps.get_db)) -> list[dict]:
    """Metadata only. The secret is never read here, so it cannot leak here."""
    return [
        {"credential_id": c.credential_id, "venue": c.venue, "label": c.label,
         "key_version": c.key_version, "created_at": c.created_at,
         "created_by": c.created_by, "rotated_at": c.rotated_at,
         "revoked_at": c.revoked_at, "active": c.active}
        for c in tenants.list_credentials(db, tenant_id)
    ]


@router.post("/{tenant_id}/credentials", status_code=status.HTTP_201_CREATED,
             operation_id="createTenantCredential")
def create_credential(tenant_id: str, payload: CredentialCreate,
                      admin: Tenant = Depends(deps.require_admin),
                      db: DbSession = Depends(deps.get_db),
                      kr: Keyring = Depends(deps.keyring)) -> dict:
    tenant = tenants.by_id(db, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Not found")
    row = tenants.store_credential(db, tenant, venue=payload.venue,
                                   label=payload.label, secret=payload.secret,
                                   keyring=kr, actor=admin.slug)
    db.commit()
    # The response says a credential exists. It does not say what it is.
    return {"credential_id": row.id, "venue": row.venue, "label": row.label,
            "key_version": row.key_version, "created_at": row.created_at}


@router.post("/{tenant_id}/credentials/{credential_id}/rotate",
             operation_id="rotateTenantCredential")
def rotate_credential(tenant_id: str, credential_id: str,
                      payload: CredentialRotate,
                      admin: Tenant = Depends(deps.require_admin),
                      db: DbSession = Depends(deps.get_db),
                      kr: Keyring = Depends(deps.keyring)) -> dict:
    row = db.get(TenantCredential, credential_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Not found")
    tenants.rotate_credential(db, row, secret=payload.secret, keyring=kr,
                              actor=admin.slug)
    db.commit()
    return {"credential_id": row.id, "rotated_at": row.rotated_at,
            "key_version": row.key_version}


@router.delete("/{tenant_id}/credentials/{credential_id}",
               operation_id="revokeTenantCredential")
def revoke_credential(tenant_id: str, credential_id: str,
                      admin: Tenant = Depends(deps.require_admin),
                      db: DbSession = Depends(deps.get_db)) -> dict:
    row = db.get(TenantCredential, credential_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Not found")
    tenants.revoke_credential(db, row, actor=admin.slug)
    db.commit()
    return {"credential_id": credential_id, "revoked_at": row.revoked_at}
