"""Per-user credential discovery inside a user_root_folder.

Contract (inherited from the 38trades customer folders):
- ``<root>/.env`` first, else the first sorted ``*.env`` — dotenv format with
  keys KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY, BASE_URI, optional DRY_RUN_MODE.
- KALSHI_PRIVATE_KEY may be an absolute path or a bare filename resolved
  against the root; if unset/unresolvable, fall back to the first ``*.pem``.
- ``<root>/.sam`` is a single-line plaintext password used by the apps'
  login flow (compared timing-safely, never returned by any endpoint).

Credentials are parsed into a plain dict and NEVER loaded into
``os.environ`` — one user's secrets must not leak into another user's bot
subprocess (a real bug in the legacy bots this refactor fixes).
"""

from __future__ import annotations

import hmac
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

from app.core import paths

DEFAULT_BASE_URI = "https://external-api.kalshi.com/trade-api/v2"


class CredentialsError(Exception):
    """Raised when a user folder does not yield a usable credential set."""


@dataclass(frozen=True)
class KalshiCredentials:
    api_key_id: str
    private_key_path: Path
    base_uri: str
    env_file: Path
    dry_run: bool

    @property
    def api_key_id_masked(self) -> str:
        kid = self.api_key_id
        return kid[:4] + "..." + kid[-4:] if len(kid) > 10 else "***"


def _find_env_file(root: Path) -> Path | None:
    direct = root / ".env"
    if direct.is_file():
        return direct
    candidates = sorted(root.glob("*.env"))
    return candidates[0] if candidates else None


def _resolve_pem(root: Path, configured: str | None) -> Path | None:
    if configured:
        p = Path(configured)
        if p.is_absolute() and p.is_file():
            return p
        try:
            rel = paths.resolve_user_file(root, configured)
        except paths.PathSecurityError:
            rel = None
        if rel is not None and rel.is_file():
            return rel
    pems = sorted(root.glob("*.pem"))
    return pems[0] if pems else None


def load_kalshi_credentials(user_root_folder: str) -> KalshiCredentials:
    root = paths.normalize_root(user_root_folder)
    if not root.is_dir():
        raise CredentialsError(f"User root folder does not exist: {root}")
    env_file = _find_env_file(root)
    if env_file is None:
        raise CredentialsError(f"No .env credentials file in {root}")
    values = {k: v for k, v in dotenv_values(env_file).items() if v is not None}
    api_key_id = values.get("KALSHI_API_KEY_ID", "").strip()
    if not api_key_id:
        raise CredentialsError(f"KALSHI_API_KEY_ID missing in {env_file.name}")
    pem = _resolve_pem(root, values.get("KALSHI_PRIVATE_KEY"))
    if pem is None:
        raise CredentialsError(f"No private key PEM found in {root}")
    dry_run = values.get("DRY_RUN_MODE", "TRUE").strip().upper() != "FALSE"
    return KalshiCredentials(
        api_key_id=api_key_id,
        private_key_path=pem,
        base_uri=values.get("BASE_URI", DEFAULT_BASE_URI).strip() or DEFAULT_BASE_URI,
        env_file=env_file,
        dry_run=dry_run,
    )


def verify_password(user_root_folder: str, password: str) -> bool:
    """Timing-safe check against the folder's .sam file (legacy contract:
    stripped plaintext compare + constant 1s delay on any failure path)."""
    ok = False
    try:
        sam = paths.resolve_user_file(user_root_folder, ".sam")
        if sam.is_file():
            stored = sam.read_text(encoding="utf-8").strip()
            # Compare as bytes: compare_digest(str, str) raises TypeError on
            # non-ASCII input, which would surface as a 500.
            ok = hmac.compare_digest(stored.encode("utf-8"), password.strip().encode("utf-8"))
    except (paths.PathSecurityError, ValueError, OSError):
        ok = False
    if not ok:
        time.sleep(1.0)
    return ok


def load_tradier_credentials(user_root_folder: str, *, sandbox: bool):
    """Tradier host + token + account id from the user's .env.

    Separate keys per environment on purpose — the sandbox is a different
    venue with its own token, so a paper session physically cannot reach the
    live account by a flag being misread:

        TRADIER_SANDBOX_URI / _TOKEN / _ACCOUNT_ID    (paper)
        TRADIER_PROD_URI    / _TOKEN / _ACCOUNT_ID    (live)

    The pre-2026-08 live names (TRADIER_ACCESS_TOKEN / TRADIER_ACCOUNT_ID)
    are still accepted so an un-migrated customer folder keeps working.
    """
    from app.services.tradier_client import TradierCredentials, normalize_base_url

    root = paths.normalize_root(user_root_folder)
    if not root.is_dir():
        raise CredentialsError(f"User root folder does not exist: {root}")
    env_file = _find_env_file(root)
    if env_file is None:
        raise CredentialsError(f"No .env credentials file in {root}")
    values = {k: v for k, v in dotenv_values(env_file).items() if v is not None}

    def get(*names: str) -> str:
        for n in names:
            v = values.get(n, "").strip()
            if v:
                return v
        return ""

    if sandbox:
        token = get("TRADIER_SANDBOX_TOKEN")
        account = get("TRADIER_SANDBOX_ACCOUNT_ID")
        uri = get("TRADIER_SANDBOX_URI")
        which = "TRADIER_SANDBOX_TOKEN / TRADIER_SANDBOX_ACCOUNT_ID"
    else:
        token = get("TRADIER_PROD_TOKEN", "TRADIER_ACCESS_TOKEN")
        account = get("TRADIER_PROD_ACCOUNT_ID", "TRADIER_ACCOUNT_ID")
        uri = get("TRADIER_PROD_URI")
        which = "TRADIER_PROD_TOKEN / TRADIER_PROD_ACCOUNT_ID"
    if not token or not account:
        raise CredentialsError(
            f"{which} missing in {env_file.name} — add the "
            f"{'sandbox' if sandbox else 'live'} Tradier keys to trade there"
        )
    try:
        base_url = normalize_base_url(uri, sandbox=sandbox)
    except Exception as exc:                      # noqa: BLE001 - as config error
        raise CredentialsError(str(exc)) from exc
    return TradierCredentials(access_token=token, account_id=account,
                              sandbox=sandbox, base_url=base_url)
