"""AES-256-GCM column-level encryption for sensitive inbox fields.

Ciphertext format (stored as base64url text in any TEXT column):

    version[1 byte] || nonce[12 bytes] || ciphertext[N bytes] || tag[16 bytes]

The version byte is read at decrypt time to select the correct key from the
registry, enabling transparent decryption across key rotations without any
schema or migration changes.

Key configuration (via environment variables / Doppler / Railway Secrets):

    INBOX_ENCRYPTION_KEY_V1      — 64 hex chars = 32 bytes; required in production
    INBOX_ENCRYPTION_KEY_VERSION — int (default 1); selects which key encrypts new rows

Key rotation procedure:
    1. Generate a new key: python -c "import os; print(os.urandom(32).hex())"
    2. Add it as INBOX_ENCRYPTION_KEY_V(N+1) in env vars and KEY_REGISTRY below.
    3. Set INBOX_ENCRYPTION_KEY_VERSION = N+1 and deploy.
       New rows encrypt with the new key; existing rows still decrypt via version byte.
    4. Run the re-encryption background task to migrate old rows to the new key.
    5. Remove the old key only after all rows are verified re-encrypted.
"""

from __future__ import annotations

import base64
import os
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from corpmind.core.config import settings
from corpmind.core.exceptions import DecryptionError, EncryptionError

# ── Wire constants ─────────────────────────────────────────────────────────────

_NONCE_SIZE: Final[int] = 12   # 96-bit nonce — GCM standard; safe for os.urandom()
_TAG_SIZE: Final[int] = 16     # 128-bit authentication tag — GCM standard
_VERSION_SIZE: Final[int] = 1  # 1 byte supports key versions 0–255

# Minimum valid blob length = version(1) + nonce(12) + tag(16) = 29 bytes.
# This is what encrypting an empty string produces: no ciphertext bytes, just the tag.
_MIN_BLOB_SIZE: Final[int] = _VERSION_SIZE + _NONCE_SIZE + _TAG_SIZE


# ── Key registry ───────────────────────────────────────────────────────────────

def _load_key_registry() -> dict[int, bytes]:
    """Build the key registry from settings.

    Called once at module load for fail-fast detection of misconfigured keys.
    Returns an empty dict when no keys are configured — this allows the module
    to be imported in dev/test environments that do not use the inbox module.
    Calling encrypt() or decrypt() with an empty registry raises EncryptionError.

    Raises:
        EncryptionError: A configured key is present but contains invalid hex or
                         has the wrong byte length.
    """
    registry: dict[int, bytes] = {}

    raw_v1 = settings.INBOX_ENCRYPTION_KEY_V1
    if raw_v1:
        try:
            key_bytes = bytes.fromhex(raw_v1)
        except ValueError as exc:
            raise EncryptionError(
                "INBOX_ENCRYPTION_KEY_V1 contains invalid hex characters"
            ) from exc
        if len(key_bytes) != 32:
            raise EncryptionError(
                f"INBOX_ENCRYPTION_KEY_V1 must be exactly 64 hex characters (32 bytes); "
                f"got {len(key_bytes)} bytes"
            )
        registry[1] = key_bytes

    return registry


# Module-level state — initialized once at import for fail-fast startup behaviour.
# Mutating these in tests is the correct approach:
#   patch.dict("corpmind.core.encryption._KEY_REGISTRY", {1: test_key}, clear=True)
#   patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1)
_KEY_REGISTRY: dict[int, bytes] = _load_key_registry()
_ACTIVE_KEY_VERSION: int = settings.INBOX_ENCRYPTION_KEY_VERSION


# ── Public API ─────────────────────────────────────────────────────────────────

def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM using the active key version.

    Returns a base64url-encoded string safe for storage in any TEXT column.
    Every call generates a fresh random 12-byte nonce — identical plaintexts
    intentionally produce different ciphertexts.

    Raises:
        EncryptionError: No keys are configured, or the active version is absent
                         from the registry.
    """
    if not _KEY_REGISTRY:
        raise EncryptionError(
            "No encryption keys configured. "
            "Set INBOX_ENCRYPTION_KEY_V1 in environment variables."
        )

    if _ACTIVE_KEY_VERSION not in _KEY_REGISTRY:
        raise EncryptionError(
            f"Active key version {_ACTIVE_KEY_VERSION!r} is not present in the "
            f"key registry. Available versions: {sorted(_KEY_REGISTRY)}"
        )

    key = _KEY_REGISTRY[_ACTIVE_KEY_VERSION]
    nonce = os.urandom(_NONCE_SIZE)

    aesgcm = AESGCM(key)
    # AESGCM.encrypt returns ciphertext bytes with the 16-byte GCM tag appended.
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    # Pack: version[1] || nonce[12] || ciphertext+tag[N+16]
    blob = bytes([_ACTIVE_KEY_VERSION]) + nonce + ciphertext_and_tag
    return base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt(ciphertext_b64: str) -> str:
    """Decrypt a value produced by :func:`encrypt`.

    Reads the version byte from the blob to look up the correct decryption key,
    enabling transparent decryption across key rotations.

    Raises:
        DecryptionError: Invalid base64url encoding, blob too short, unknown key
                         version, or GCM authentication failure (tampered or
                         corrupted ciphertext, or wrong decryption key).
    """
    # Step 1: decode base64url — tolerate missing padding (robust against stripped '=')
    try:
        padded = ciphertext_b64 + "=" * (-len(ciphertext_b64) % 4)
        blob = base64.urlsafe_b64decode(padded)
    except Exception as exc:
        raise DecryptionError(
            "Invalid base64url encoding in ciphertext blob"
        ) from exc

    # Step 2: validate minimum length (version + nonce + tag = 29 bytes)
    if len(blob) < _MIN_BLOB_SIZE:
        raise DecryptionError(
            f"Ciphertext blob is too short: {len(blob)} bytes "
            f"(minimum {_MIN_BLOB_SIZE} — version + nonce + tag)"
        )

    # Step 3: extract version byte and look up the corresponding key
    version = blob[0]
    if version not in _KEY_REGISTRY:
        raise DecryptionError(
            f"Unknown key version {version!r} in ciphertext blob. "
            f"Available versions: {sorted(_KEY_REGISTRY)}"
        )

    # Step 4: unpack nonce and ciphertext+tag
    key = _KEY_REGISTRY[version]
    nonce = blob[_VERSION_SIZE : _VERSION_SIZE + _NONCE_SIZE]
    ciphertext_and_tag = blob[_VERSION_SIZE + _NONCE_SIZE :]

    # Step 5: decrypt and verify the GCM authentication tag.
    # AESGCM raises InvalidTag on any authentication failure — tampered bytes,
    # wrong key, or corrupted payload all surface as the same exception type.
    aesgcm = AESGCM(key)
    try:
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
    except Exception as exc:
        raise DecryptionError(
            "Decryption failed: ciphertext is tampered, corrupted, or the wrong key was used"
        ) from exc

    return plaintext_bytes.decode("utf-8")
