"""Unit tests for focuslock.core.security — password hashing."""

from focuslock.core.security import hash_password, verify_password


class TestHashPassword:
    def test_returns_colon_separated(self):
        result = hash_password("mypassword")
        assert ":" in result
        salt_hex, hash_hex = result.split(":")
        assert len(salt_hex) == 32  # 16 bytes hex
        assert len(hash_hex) == 64  # SHA-256 hex

    def test_different_salts_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_already_hashed_returns_unchanged(self):
        h = hash_password("test")
        assert hash_password("any_password", salt=h) == h


class TestVerifyPassword:
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

    def test_empty_stored(self):
        ok, _ = verify_password("anything", "")
        assert ok is False

    def test_none_stored(self):
        ok, _ = verify_password("anything", None)
        assert ok is False

    def test_legacy_unsalted(self):
        """Legacy unsalted hashes should verify and trigger migration."""
        import hashlib
        legacy = hashlib.sha256("oldpass".encode()).hexdigest()
        ok, new_hash = verify_password("oldpass", legacy)
        assert ok is True
        assert new_hash is not None
        assert ":" in new_hash  # migrated to salted format

    def test_legacy_unsalted_wrong_password(self):
        import hashlib
        legacy = hashlib.sha256("oldpass".encode()).hexdigest()
        ok, new_hash = verify_password("wrong", legacy)
        assert ok is False
        assert new_hash is None

    def test_empty_password(self):
        h = hash_password("")
        ok, _ = verify_password("", h)
        assert ok is True

    def test_migrated_password_verifies(self):
        """After migration, the new hash should verify correctly."""
        import hashlib
        legacy = hashlib.sha256("test".encode()).hexdigest()
        ok, new_hash = verify_password("test", legacy)
        assert ok is True
        # Verify against the migrated hash
        ok2, _ = verify_password("test", new_hash)
        assert ok2 is True
