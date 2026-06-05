"""Unit tests for corpmind.core.encryption — 100% line and branch coverage.

Tests inject keys by patching module-level state directly:
    patch.dict("corpmind.core.encryption._KEY_REGISTRY", {...}, clear=True)
    patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", N)

This avoids touching environment variables or the live settings object, and
correctly simulates how the production module reads these globals at call time.
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest

from corpmind.core.exceptions import DecryptionError, EncryptionError

# ── Test key material ──────────────────────────────────────────────────────────

# Deterministic test keys — never used in production.
# bytes(range(32))  =  0x00 0x01 … 0x1F  (32 unique non-zero-repeat bytes)
# bytes(range(32, 64)) =  0x20 … 0x3F    (different 32 bytes for V2)
_KEY_V1 = bytes(range(32))
_KEY_V2 = bytes(range(32, 64))

_REGISTRY_V1 = {1: _KEY_V1}
_REGISTRY_V1_AND_V2 = {1: _KEY_V1, 2: _KEY_V2}

# ── Shared fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def keys_v1():
    """Inject V1 as the sole key, V1 active. Used by the majority of tests."""
    with patch.dict("corpmind.core.encryption._KEY_REGISTRY", _REGISTRY_V1, clear=True):
        with patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1):
            yield


# ── _load_key_registry ─────────────────────────────────────────────────────────


class TestLoadKeyRegistry:
    """Tests for the module-level key registry builder."""

    def _call(self, key_v1_hex: str) -> dict:
        from corpmind.core import encryption as enc

        with patch("corpmind.core.encryption.settings") as mock_s:
            mock_s.INBOX_ENCRYPTION_KEY_V1 = key_v1_hex
            return enc._load_key_registry()

    def test_empty_key_returns_empty_registry(self):
        result = self._call("")
        assert result == {}

    def test_valid_key_populates_v1_slot(self):
        result = self._call(_KEY_V1.hex())
        assert result == {1: _KEY_V1}

    def test_invalid_hex_raises_encryption_error(self):
        with pytest.raises(EncryptionError, match="invalid hex"):
            self._call("zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")

    def test_key_too_short_raises_encryption_error(self):
        # 3 bytes = 6 hex chars — nowhere near 32
        with pytest.raises(EncryptionError, match="32 bytes"):
            self._call("aabbcc")

    def test_key_too_long_raises_encryption_error(self):
        # 33 bytes = 66 hex chars
        with pytest.raises(EncryptionError, match="32 bytes"):
            self._call("aa" * 33)


# ── encrypt ────────────────────────────────────────────────────────────────────


class TestEncrypt:
    """Tests for the encrypt() public function."""

    def test_no_keys_raises_encryption_error(self):
        with patch.dict("corpmind.core.encryption._KEY_REGISTRY", {}, clear=True):
            with pytest.raises(EncryptionError, match="No encryption keys"):
                from corpmind.core.encryption import encrypt

                encrypt("anything")

    def test_active_version_missing_from_registry_raises(self, keys_v1):
        with patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 99):
            with pytest.raises(EncryptionError, match="not present in the key registry"):
                from corpmind.core.encryption import encrypt

                encrypt("anything")

    def test_returns_base64url_string(self, keys_v1):
        from corpmind.core.encryption import encrypt

        ct = encrypt("hello@example.com")
        # base64url uses A-Z a-z 0-9 - _ and optional = padding
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=" for c in ct)

    def test_version_byte_is_embedded_in_output(self, keys_v1):
        from corpmind.core.encryption import encrypt

        ct = encrypt("test")
        blob = base64.urlsafe_b64decode(ct)
        assert blob[0] == 1  # version byte matches the active key version

    def test_unique_nonce_per_call_produces_different_ciphertexts(self, keys_v1):
        from corpmind.core.encryption import encrypt

        ct1 = encrypt("same plaintext")
        ct2 = encrypt("same plaintext")
        assert ct1 != ct2  # different random nonces → different outputs

    def test_unicode_plaintext_is_accepted(self, keys_v1):
        from corpmind.core.encryption import encrypt

        # Hindi + Chinese + Japanese + emoji — real inbox subject lines look like this
        encrypt("नमस्ते — 你好 — こんにちは 🎉")

    def test_empty_string_produces_minimum_size_blob(self, keys_v1):
        from corpmind.core.encryption import _MIN_BLOB_SIZE, encrypt

        ct = encrypt("")
        blob = base64.urlsafe_b64decode(ct)
        # Empty plaintext → zero ciphertext bytes → only version + nonce + tag
        assert len(blob) == _MIN_BLOB_SIZE

    def test_long_string_does_not_raise(self, keys_v1):
        from corpmind.core.encryption import encrypt

        encrypt("x" * 100_000)


# ── decrypt ────────────────────────────────────────────────────────────────────


class TestDecrypt:
    """Tests for the decrypt() public function."""

    def test_roundtrip_ascii(self, keys_v1):
        from corpmind.core.encryption import decrypt, encrypt

        plaintext = "admin@corpmind.example"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_roundtrip_unicode(self, keys_v1):
        from corpmind.core.encryption import decrypt, encrypt

        plaintext = "Priya Sharma — प्रिया शर्मा — Subject: Leadership Training"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_roundtrip_empty_string(self, keys_v1):
        from corpmind.core.encryption import decrypt, encrypt

        assert decrypt(encrypt("")) == ""

    def test_roundtrip_long_string(self, keys_v1):
        from corpmind.core.encryption import decrypt, encrypt

        plaintext = "email body content — " * 5_000
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_invalid_base64_raises_decryption_error(self, keys_v1):
        from corpmind.core.encryption import decrypt

        with pytest.raises(DecryptionError, match="Invalid base64url"):
            decrypt("not!valid!base64!!!")

    def test_blob_too_short_raises_decryption_error(self, keys_v1):
        from corpmind.core.encryption import decrypt

        # 10 bytes — well below the 29-byte minimum
        short = base64.urlsafe_b64encode(bytes(10)).decode()
        with pytest.raises(DecryptionError, match="too short"):
            decrypt(short)

    def test_unknown_version_raises_decryption_error(self, keys_v1):
        from corpmind.core.encryption import _MIN_BLOB_SIZE, decrypt

        # Construct a valid-length blob with version byte = 99 (not in registry)
        blob = bytes([99]) + bytes(_MIN_BLOB_SIZE - 1)
        ct = base64.urlsafe_b64encode(blob).decode()
        with pytest.raises(DecryptionError, match="Unknown key version"):
            decrypt(ct)

    def test_tampered_ciphertext_raises_decryption_error(self, keys_v1):
        from corpmind.core.encryption import _NONCE_SIZE, _VERSION_SIZE, decrypt, encrypt

        ct_b64 = encrypt("sensitive inbox data")
        blob = bytearray(base64.urlsafe_b64decode(ct_b64))
        # Flip a bit in the ciphertext region (byte 13 = first ciphertext byte,
        # safely past version[1] + nonce[12])
        blob[_VERSION_SIZE + _NONCE_SIZE] ^= 0xFF
        bad_ct = base64.urlsafe_b64encode(bytes(blob)).decode()
        with pytest.raises(DecryptionError, match="tampered"):
            decrypt(bad_ct)

    def test_wrong_key_raises_decryption_error(self, keys_v1):
        from corpmind.core.encryption import decrypt, encrypt

        ct = encrypt("secret value")
        wrong_key = bytes([0xAA] * 32)
        with patch.dict("corpmind.core.encryption._KEY_REGISTRY", {1: wrong_key}, clear=True):
            with pytest.raises(DecryptionError, match="tampered"):
                decrypt(ct)

    def test_missing_base64_padding_is_tolerated(self, keys_v1):
        """Padding-stripped stored values must still decrypt correctly."""
        from corpmind.core.encryption import decrypt, encrypt

        ct_b64 = encrypt("padding tolerance test")
        stripped = ct_b64.rstrip("=")
        assert decrypt(stripped) == "padding tolerance test"


# ── Key rotation scenarios ─────────────────────────────────────────────────────


class TestKeyRotation:
    """End-to-end rotation tests validating the version-byte contract."""

    def test_old_ciphertext_decrypts_after_rotation(self):
        """V1-encrypted rows remain readable when V2 is the active key."""
        from corpmind.core.encryption import decrypt, encrypt

        # Phase 1: encrypt with V1
        with patch.dict("corpmind.core.encryption._KEY_REGISTRY", _REGISTRY_V1, clear=True):
            with patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1):
                ct_v1 = encrypt("trainer@example.com")

        # Phase 2: V2 is now active; V1 is still in the registry for decryption
        with patch.dict(
            "corpmind.core.encryption._KEY_REGISTRY", _REGISTRY_V1_AND_V2, clear=True
        ):
            with patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 2):
                ct_v2 = encrypt("new-hire@example.com")
                # Old V1 row decrypts correctly via the embedded version byte
                assert decrypt(ct_v1) == "trainer@example.com"
                # New V2 row decrypts correctly too
                assert decrypt(ct_v2) == "new-hire@example.com"

    def test_v1_and_v2_blobs_carry_correct_version_bytes(self):
        """Version byte in the blob must match the active version at encrypt time."""
        from corpmind.core.encryption import encrypt

        with patch.dict("corpmind.core.encryption._KEY_REGISTRY", _REGISTRY_V1, clear=True):
            with patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1):
                ct_v1 = encrypt("value")

        with patch.dict(
            "corpmind.core.encryption._KEY_REGISTRY", _REGISTRY_V1_AND_V2, clear=True
        ):
            with patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 2):
                ct_v2 = encrypt("value")

        assert base64.urlsafe_b64decode(ct_v1)[0] == 1
        assert base64.urlsafe_b64decode(ct_v2)[0] == 2

    def test_premature_key_removal_raises_decryption_error(self):
        """Removing V1 before re-encryption completes must raise, not silently fail."""
        from corpmind.core.encryption import decrypt, encrypt

        with patch.dict("corpmind.core.encryption._KEY_REGISTRY", _REGISTRY_V1, clear=True):
            with patch("corpmind.core.encryption._ACTIVE_KEY_VERSION", 1):
                ct_v1 = encrypt("orphaned ciphertext")

        # V1 removed prematurely — V2 only in registry
        with patch.dict(
            "corpmind.core.encryption._KEY_REGISTRY", {2: _KEY_V2}, clear=True
        ):
            with pytest.raises(DecryptionError, match="Unknown key version"):
                decrypt(ct_v1)
