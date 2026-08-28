from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core import paths


class UserCreate(BaseModel):
    # Same contract as the legacy customer folders: safe filename characters
    # only (the name is also used in log filenames and subprocess argv).
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    email: EmailStr | None = None
    user_root_folder: str | None = Field(
        default=None,
        description="Windows (D:\\...) or POSIX (/home/...) path to the user's "
        "secrets folder (API keys, PEM, wellness profile). Omit it and the "
        "server defaults to <TBOT_CUSTOMERS_ROOT>/<username> — clients "
        "should NOT hardcode machine paths.",
        min_length=1,
        max_length=1024,
    )

    @field_validator("user_root_folder")
    @classmethod
    def _canonicalize(cls, v: str | None) -> str | None:
        # Normalizes either notation to forward-slash canonical form and
        # rejects strings that cannot be parsed as a path at all.
        return paths.canonical_str(v.strip()) if v is not None else None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    username: str
    email: str | None
    user_root_folder: str
    root_folder_exists: bool | None = None
    created_at: datetime
    updated_at: datetime
