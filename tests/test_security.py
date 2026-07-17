"""Comprehensive tests for focuslock.core.security — password hashing.

Covers: hash_password (format, salt handling, idempotency), verify_password
(correct/wrong/empty/None, legacy migration, round-trip), and edge cases.
"""

import hashlib

import pytest

from focuslock.core.security import hash_password, verify_password


# ═══════════════════════════════════════════════════════════════════════════
# hash_password
# ═══════════════════════════════════════════════════════════════════════════

class TestHashPassword:
    """Output format, salt handling, and idempotency."""

    def test_returns_colon_separated(self):
        result = hash_password("mypassword")
        assert ":" in result

    def test_salt_is_32_hex_chars(self):
        result = hash_password("test")
        salt_hex = result.split(":")[0]
        assert len(salt_hex) == 32  # 16 bytes = 32 hex chars

    def test_hash_is_64_hex_chars(self):
        result = hash_password("test")
        hash_hex = result.split(":")[1]
        assert len(hash_hex) == 64  # SHA-256 = 64 hex chars

    def test_different_salts_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_same_password_different_results(self):
        results = {hash_password("test") for _ in range(20)}
        assert len(results) == 20  # all should be unique

    def test_already_hashed_returns_unchanged(self):
        h = hash_password("test")
        assert hash_password("any_password", salt=h) == h

    def test_empty_password_hashes(self):
        result = hash_password("")
        salt_hex, hash_hex = result.split(":")
        assert len(salt_hex) == 32
        assert len(hash_hex) == 64

    def test_unicode_password(self):
        result = hash_password("pässwörd_中文")
        assert ":" in result
        # Should be deterministic with same salt
        salt = result.split(":")[0]
        result2 = hash_password("pässwörd_中文", salt=salt)
        assert result == result2

    def test_very_long_password(self):
        long_pw = "x" * 10000
        result = hash_password(long_pw)
        assert ":" in result

    def test_explicit_hex_salt(self):
        salt = "a" * 32
        result = hash_password("test", salt=salt)
        assert result.startswith(salt + ":")

    def test_explicit_bytes_salt(self):
        salt = b'\x00' * 16
        result = hash_password("test", salt=salt)
        assert result.startswith("0" * 32 + ":")

    def test_hash_is_sha256(self):
        """The hash portion should match SHA-256(salt + password)."""
        result = hash_password("hello")
        salt_hex, hash_hex = result.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.sha256(salt + b"hello").hexdigest()
        assert hash_hex == expected


# ═══════════════════════════════════════════════════════════════════════════
# verify_password
# ═══════════════════════════════════════════════════════════════════════════

class TestVerifyPassword:
    """Password verification and legacy migration."""

    def test_correct_password(self):
        h = hash_password("secret")
        ok, new_hash = verify_password("secret", h)
        assert ok is True
        assert new_hash is None  # already salted, no migration needed

    def test_wrong_password(self):
        h = hash_password("secret")
        ok, new_hash = verify_password("wrong", h)
        assert ok is False
        assert new_hash is None

    def test_empty_stored_hash(self):
        ok, new_hash = verify_password("anything", "")
        assert ok is False
        assert new_hash is None

    def test_none_stored_hash(self):
        ok, new_hash = verify_password("anything", None)
        assert ok is False
        assert new_hash is None

    def test_empty_password_matches_empty_hash(self):
        h = hash_password("")
        ok, _ = verify_password("", h)
        assert ok is True

    def test_wrong_empty_password(self):
        h = hash_password("secret")
        ok, _ = verify_password("", h)
        assert ok is False

    def test_legacy_unsalted_correct_password(self):
        """Legacy unsalted hashes should verify and trigger migration."""
        legacy = hashlib.sha256("oldpass".encode()).hexdigest()
        ok, new_hash = verify_password("oldpass", legacy)
        assert ok is True
        assert new_hash is not None
        assert ":" in new_hash  # migrated to salted format

    def test_legacy_unsalted_wrong_password(self):
        legacy = hashlib.sha256("oldpass".encode()).hexdigest()
        ok, new_hash = verify_password("wrong", legacy)
        assert ok is False
        assert new_hash is None

    def test_migrated_password_verifies(self):
        """After migration, the new hash should verify correctly."""
        legacy = hashlib.sha256("test".encode()).hexdigest()
        ok, new_hash = verify_password("test", legacy)
        assert ok is True
        ok2, _ = verify_password("test", new_hash)
        assert ok2 is True

    def test_migrated_hash_has_colon(self):
        legacy = hashlib.sha256("pw".encode()).hexdigest()
        _, new_hash = verify_password("pw", legacy)
        assert ":" in new_hash

    def test_migrated_hash_differs_from_original(self):
        legacy = hashlib.sha256("pw".encode()).hexdigest()
        _, new_hash = verify_password("pw", legacy)
        assert new_hash != legacy

    def test_correct_password_does_not_migrate(self):
        """Already-salt-hashed passwords should not trigger migration."""
        h = hash_password("test")
        ok, new_hash = verify_password("test", h)
        assert ok is True
        assert new_hash is None


# ═══════════════════════════════════════════════════════════════════════════
# Round-trip
# ═══════════════════════════════════════════════════════════════════════════

class TestRoundTrip:
    """hash → verify → migrate → verify chain."""

    def test_full_round_trip(self):
        original = hash_password("mypassword")
        ok, migrated = verify_password("mypassword", original)
        assert ok is True
        assert migrated is None  # no migration needed

    def test_legacy_full_round_trip(self):
        legacy = hashlib.sha256("oldpw".encode()).hexdigest()
        ok, migrated = verify_password("oldpw", legacy)
        assert ok is True
        assert migrated is not None
        # Verify against migrated hash
        ok2, _ = verify_password("oldpw", migrated)
        assert ok2 is True
        # Wrong password should fail against migrated hash
        ok3, _ = verify_password("wrong", migrated)
        assert ok3 is False

    @pytest.mark.parametrize("password", ["a", "hello", "pässwörd", "", "x" * 1000])
    def test_various_passwords(self, password):
        h = hash_password(password)
        ok, _ = verify_password(password, h)
        assert ok is True
        # Wrong password always fails
        ok_wrong, _ = verify_password(password + "x", h)
        assert ok_wrong is False
