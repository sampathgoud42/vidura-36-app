"""The wellness profile: one per operator, private to them.

Special-category personal data — ethnicity, gender, diet, health goals. It
inherits the credential handling rules: never logged, never in an error,
never in a diagnostic. Tenant-scoped like everything else, so the isolation
suite covers it without a special case.

``age_band`` is TEXT and named for what it holds. The source file stores
"35-44", not a number, and a column typed INTEGER would fail on the first
imported row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api_v2 import deps
from app.tenancy.models import Tenant, WellnessGoal, WellnessProfile

router = APIRouter(prefix="/wellness", tags=["wellness"])

MAX_GOALS = 12


class ProfileIn(BaseModel):
    gender: str | None = Field(default=None, max_length=32)
    age_band: str | None = Field(default=None, max_length=16)
    ethnicity: str | None = Field(default=None, max_length=64)
    diet: str | None = Field(default=None, max_length=64)
    style: str | None = Field(default=None, max_length=32)
    region: str | None = Field(default=None, max_length=64)
    notifications: bool = False
    goals: list[str] = Field(default_factory=list, max_length=MAX_GOALS)


def _serialise(profile: WellnessProfile, goals: list[WellnessGoal]) -> dict:
    return {
        "gender": profile.gender,
        "age_band": profile.age_band,
        "ethnicity": profile.ethnicity,
        "diet": profile.diet,
        "style": profile.style,
        "region": profile.region,
        "notifications": profile.notifications,
        # Order is the operator's own, preserved by position.
        "goals": [g.goal for g in sorted(goals, key=lambda g: g.position)],
    }


@router.get("/profile", operation_id="getWellnessProfile")
@deps.tenant_scoped
def get_profile(tenant: Tenant = Depends(deps.current_tenant),
                db: DbSession = Depends(deps.get_db)) -> dict:
    """An operator with no profile gets an empty one rather than a 404.

    The desk renders a form either way, and "not found" would make an
    unfilled profile look like an error.
    """
    profile = db.scalar(select(WellnessProfile).where(
        WellnessProfile.tenant_id == tenant.id))
    if profile is None:
        return {"gender": None, "age_band": None, "ethnicity": None,
                "diet": None, "style": None, "region": None,
                "notifications": False, "goals": []}
    goals = list(db.scalars(select(WellnessGoal).where(
        WellnessGoal.profile_id == profile.id)).all())
    return _serialise(profile, goals)


@router.put("/profile", operation_id="setWellnessProfile")
@deps.tenant_scoped
def set_profile(payload: ProfileIn,
                tenant: Tenant = Depends(deps.current_tenant),
                db: DbSession = Depends(deps.get_db)) -> dict:
    profile = db.scalar(select(WellnessProfile).where(
        WellnessProfile.tenant_id == tenant.id))
    if profile is None:
        profile = WellnessProfile(tenant_id=tenant.id)
        db.add(profile)
        db.flush()

    profile.gender = payload.gender
    profile.age_band = payload.age_band
    profile.ethnicity = payload.ethnicity
    profile.diet = payload.diet
    profile.style = payload.style
    profile.region = payload.region
    profile.notifications = payload.notifications

    # Replace wholesale: a PUT is the whole profile, and reconciling a
    # partial goal list against stored positions is complexity nobody asked
    # for.
    for existing in db.scalars(select(WellnessGoal).where(
            WellnessGoal.profile_id == profile.id)).all():
        db.delete(existing)
    db.flush()

    goals = []
    seen: set[str] = set()
    position = 0
    for raw in payload.goals:
        goal = raw.strip()
        if not goal or goal.lower() in seen:
            continue
        seen.add(goal.lower())
        row = WellnessGoal(tenant_id=tenant.id, profile_id=profile.id,
                           goal=goal[:64], position=position)
        db.add(row)
        goals.append(row)
        position += 1

    db.commit()
    return _serialise(profile, goals)
