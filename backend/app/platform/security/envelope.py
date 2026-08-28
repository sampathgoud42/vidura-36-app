"""Envelope encryption for tenant credentials.

Every credential gets its OWN random data key (a DEK). The DEK encrypts the
secret; the master key encrypts the DEK. Two things fall out of that, and both
are why the brief asks for it rather than for plain encryption:

  * Re-keying does not touch the secrets. Rotating the master key means
    unwrapping and re-wrapping N small DEKs — the ciphertext of every
    credential is untouched, so a re-key cannot corrupt one.
  * A leaked DEK exposes exactly one credential, not the store.

``key_version`` records which master key wrapped which DEK, so old rows stay
readable during a rotation instead of everything having to move at once.

IF THE MASTER KEY IS LOST, EVERY TENANT CREDENTIAL IS UNRECOVERABLE. There is
no recovery path and there is deliberately no backdoor. Provisioning and
backup of that key is an ops procedure, documented in secrets.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

_DEK_BYTES = 32          # AES-256
_NONCE_BYTES = 12        # GCM standard


class MasterKeyMissing(RuntimeError):
    """Raised at startup when no master key is configured.

    Deliberately fatal. The brief is explicit: startup fails loudly on a
    missing secret and never defaults one. A generated-on-the-fly key would
    silently make every existing credential unreadable, which is worse than
    refusing to start.
    """


@dataclass(frozen=True)
class Sealed:
    """What gets stored. Nothing here is the secret."""

    ciphertext: bytes
    wrapped_dek: bytes
    nonce: bytes
    key_version: int

    def __repr__(self) -> str:
        return (f"<Sealed {len(self.ciphertext)}B v{self.key_version} "
                f"[encrypted]>")


def _derive(raw: str) -> bytes:
    """Turn whatever the environment supplies into a 32-byte key.

    Operators paste passphrases, not 32 raw bytes. HKDF gives a uniform key
    from any input length without silently truncating a long one or padding a
    short one — both of which quietly weaken the key while appearing to work.
    """
    return HKDF(
        algorithm=hashes.SHA256(),
        length=_DEK_BYTES,
        salt=None,
        info=b"vidura-36-app tenant credential master key",
    ).derive(raw.encode("utf-8"))


class Keyring:
    """The master key, plus any older versions still needed to read old rows."""

    def __init__(self, keys: dict[int, bytes], current: int) -> None:
        self._keys = keys
        self._current = current

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Keyring":
        env = dict(os.environ if env is None else env)
        current_raw = (env.get("TBOT_ENCRYPTION_MASTER_KEY") or "").strip()
        if not current_raw:
            raise MasterKeyMissing(
                "TBOT_ENCRYPTION_MASTER_KEY is not set. Tenant credentials "
                "cannot be read or written without it. See docs/ops/secrets.md "
                "for how it is provisioned per environment."
            )
        version = int(env.get("TBOT_ENCRYPTION_KEY_VERSION", "1"))
        keys = {version: _derive(current_raw)}

        # Older keys, for reading rows a previous key wrapped. Present only
        # during a rotation; absent the rest of the time.
        for name, value in env.items():
            if not name.startswith("TBOT_ENCRYPTION_MASTER_KEY_V"):
                continue
            try:
                v = int(name.rsplit("_V", 1)[1])
            except (IndexError, ValueError):
                continue
            if value.strip() and v not in keys:
                keys[v] = _derive(value.strip())
        return cls(keys, version)

    @property
    def current_version(self) -> int:
        return self._current

    def key(self, version: int) -> bytes:
        try:
            return self._keys[version]
        except KeyError:
            raise MasterKeyMissing(
                f"no master key for version {version}. A credential wrapped "
                f"with it cannot be read until TBOT_ENCRYPTION_MASTER_KEY_V"
                f"{version} is supplied."
            ) from None


def seal(plaintext: bytes, keyring: Keyring, *,
         aad: bytes | None = None) -> Sealed:
    """Encrypt with a fresh DEK, then wrap the DEK with the master key.

    ``aad`` binds the ciphertext to its context — pass the tenant id and venue,
    and a row physically cannot be decrypted as if it belonged to another
    tenant even by someone who can edit the database.
    """
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(dek).encrypt(nonce, plaintext, aad)

    version = keyring.current_version
    dek_nonce = os.urandom(_NONCE_BYTES)
    wrapped = AESGCM(keyring.key(version)).encrypt(dek_nonce, dek, None)
    # The DEK's own nonce travels with it; one stored column, no second one.
    return Sealed(ciphertext=ciphertext, wrapped_dek=dek_nonce + wrapped,
                  nonce=nonce, key_version=version)


def unseal(sealed: Sealed, keyring: Keyring, *,
           aad: bytes | None = None) -> bytes:
    """Recover the plaintext. Callers hold it for as short a time as possible."""
    master = keyring.key(sealed.key_version)
    dek_nonce, wrapped = sealed.wrapped_dek[:_NONCE_BYTES], sealed.wrapped_dek[_NONCE_BYTES:]
    dek = AESGCM(master).decrypt(dek_nonce, wrapped, None)
    return AESGCM(dek).decrypt(sealed.nonce, sealed.ciphertext, aad)


def rewrap(sealed: Sealed, keyring: Keyring) -> Sealed:
    """Move a record to the current master key without touching its ciphertext.

    This is the re-key procedure. The secret is never decrypted, so a re-key
    cannot corrupt one and does not need the plaintext to be available.
    """
    old = keyring.key(sealed.key_version)
    dek_nonce, wrapped = sealed.wrapped_dek[:_NONCE_BYTES], sealed.wrapped_dek[_NONCE_BYTES:]
    dek = AESGCM(old).decrypt(dek_nonce, wrapped, None)

    version = keyring.current_version
    new_nonce = os.urandom(_NONCE_BYTES)
    new_wrapped = AESGCM(keyring.key(version)).encrypt(new_nonce, dek, None)
    return Sealed(ciphertext=sealed.ciphertext,
                  wrapped_dek=new_nonce + new_wrapped,
                  nonce=sealed.nonce, key_version=version)
