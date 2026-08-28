"""Login passwords: hashed with Argon2id, never encrypted.

The distinction is the whole point. A venue API key has to be reversible
because the system presents it to Tradier and Kalshi — that is what
``envelope`` is for. A login password only ever needs COMPARING, so making it
reversible would add risk and buy nothing: anyone holding the master key, or
a leaked backup plus a leaked key, would recover every operator's password.

Argon2id is memory-hard, so a stolen hash cannot be attacked at GPU speed the
way a fast hash can. The parameters are stored alongside the hash (Argon2's
encoded form carries them), which is what makes it possible to raise the cost
later without guessing what the old rows used.
"""

from __future__ import annotations

import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Tuned for an interactive login on a desk machine: comfortably under a
# second, comfortably above what a cracking rig gets for free. The values are
# encoded into every hash, so raising them later re-hashes on next login
# rather than invalidating anyone.
_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,   # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

# Every failure path costs the same wall time, so a missing operator cannot be
# told apart from a wrong password by how fast the answer comes back. The old
# build did this with a flat sleep in the verify function; keeping it here
# means every caller inherits it rather than remembering to.
_MIN_FAILURE_SECONDS = 1.0


def hash_password(password: str) -> str:
    """Return the encoded Argon2id hash. Never returns the password."""
    if not password:
        raise ValueError("password must not be empty")
    return _HASHER.hash(password)


def verify_password(encoded_hash: str, password: str) -> bool:
    """Constant-ish time check.

    Returns False rather than raising for every failure mode — a corrupt hash
    and a wrong password are both "no", and distinguishing them for the caller
    would eventually distinguish them for an attacker.
    """
    started = time.monotonic()
    ok = False
    try:
        ok = _HASHER.verify(encoded_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, TypeError):
        ok = False
    if not ok:
        elapsed = time.monotonic() - started
        if elapsed < _MIN_FAILURE_SECONDS:
            time.sleep(_MIN_FAILURE_SECONDS - elapsed)
    return ok


def needs_rehash(encoded_hash: str) -> bool:
    """True when the hash was made with weaker parameters than we now use.

    Called after a SUCCESSFUL login, which is the only moment the plaintext
    is available to re-hash with. This is how the cost gets raised over time
    without a migration and without locking anyone out.
    """
    try:
        return _HASHER.check_needs_rehash(encoded_hash)
    except (InvalidHashError, TypeError):
        return True


def algorithm() -> str:
    return "argon2id"
