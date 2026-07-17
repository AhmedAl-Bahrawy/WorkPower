"""Tests for focuslock.services.auth_service — AuthService.

Covers: password hash accessors, verify with throttling, set/clear,
migration delegation, and edge cases.
"""

import time

import pytest

from focuslock.config import Storage
from focuslock.core.security import hash_password, verify_password
from focuslock.services.auth_service import AuthService


# ── fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def storage(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("focuslock.config.DB_FILE", db_path)
    monkeypatch.setattr("focuslock.config.DATA_DIR", tmp_path)
    s = Storage()
    yield s
    s.close()


@pytest.fixture
def auth(storage):
    return AuthService(storage)


# ═══════════════════════════════════════════════════════════════════════════
# Hash accessors
# ═══════════════════════════════════════════════════════════════════════════

class TestHashAccessors:

    def test_has_password_false_when_empty(self, auth):
        assert auth.has_password() is False

    def test_has_password_true_after_set(self, auth):
        auth.set_session_password("secret")
        assert auth.has_password() is True

    def test_has_parent_password_false_when_empty(self, auth):
        assert auth.has_parent_password() is False

    def test_has_parent_password_true_after_set(self, auth):
        auth.set_parent_password("secret")
        assert auth.has_parent_password() is True

    def test_password_hash_returns_empty_string(self, auth):
        assert auth.password_hash() == ""

    def test_password_hash_returns_stored_hash(self, auth):
        h = auth.set_session_password("test")
        assert auth.password_hash() == h

    def test_parent_password_hash_returns_stored_hash(self, auth):
        h = auth.set_parent_password("test")
        assert auth.parent_password_hash() == h


# ═══════════════════════════════════════════════════════════════════════════
# Set / Clear
# ═══════════════════════════════════════════════════════════════════════════

class TestSetClear:

    def test_set_session_password_stores_hash(self, auth):
        h = auth.set_session_password("mypassword")
        assert ":" in h
        ok, _ = verify_password("mypassword", h)
        assert ok is True

    def test_set_parent_password_stores_hash(self, auth):
        h = auth.set_parent_password("parentpw")
        assert ":" in h
        ok, _ = verify_password("parentpw", h)
        assert ok is True

    def test_clear_all_removes_both(self, auth):
        auth.set_session_password("a")
        auth.set_parent_password("b")
        auth.clear_all()
        assert auth.has_password() is False
        assert auth.has_parent_password() is False

    def test_clear_all_with_none_set(self, auth):
        auth.clear_all()
        assert auth.has_password() is False

    def test_set_overwrites_previous(self, auth):
        auth.set_session_password("first")
        auth.set_session_password("second")
        ok, _ = verify_password("second", auth.password_hash())
        assert ok is True
        ok2, _ = verify_password("first", auth.password_hash())
        assert ok2 is False


# ═══════════════════════════════════════════════════════════════════════════
# Verify
# ═══════════════════════════════════════════════════════════════════════════

class TestVerify:

    def test_verify_correct_password(self, auth):
        h = hash_password("correct")
        ok, new_hash = auth.verify("correct", h)
        assert ok is True
        assert new_hash is None  # already salted, no migration

    def test_verify_wrong_password(self, auth):
        h = hash_password("correct")
        ok, new_hash = auth.verify("wrong", h)
        assert ok is False
        assert new_hash is None

    def test_verify_legacy_hash_migrates(self, auth):
        import hashlib
        legacy = hashlib.sha256("legacy".encode()).hexdigest()
        ok, new_hash = auth.verify("legacy", legacy)
        assert ok is True
        assert new_hash is not None
        assert ":" in new_hash

    def test_verify_correct_resets_throttle(self, auth):
        h = hash_password("pw")
        auth.verify("wrong", h)
        auth.verify("wrong", h)
        assert auth.throttle_delay() > 0
        auth.verify("pw", h)
        assert auth.throttle_delay() == 0

    def test_verify_wrong_records_failure(self, auth):
        h = hash_password("pw")
        auth.verify("wrong", h)
        assert auth._fail_count == 1
        assert auth._last_fail > 0

    def test_verify_empty_hash_returns_false(self, auth):
        ok, _ = auth.verify("pw", "")
        assert ok is False

    def test_verify_none_hash_returns_false(self, auth):
        ok, _ = auth.verify("pw", None)
        assert ok is False


# ═══════════════════════════════════════════════════════════════════════════
# Session / Parent verify shortcuts
# ═══════════════════════════════════════════════════════════════════════════

class TestVerifySessionParent:

    def test_verify_session_password_no_hash_returns_true(self, auth):
        ok, migrated = auth.verify_session_password("anything")
        assert ok is True
        assert migrated is None

    def test_verify_parent_password_no_hash_returns_true(self, auth):
        ok, migrated = auth.verify_parent_password("anything")
        assert ok is True
        assert migrated is None

    def test_verify_session_password_correct(self, auth):
        auth.set_session_password("secret")
        ok, _ = auth.verify_session_password("secret")
        assert ok is True

    def test_verify_session_password_wrong(self, auth):
        auth.set_session_password("secret")
        ok, _ = auth.verify_session_password("wrong")
        assert ok is False

    def test_verify_parent_password_correct(self, auth):
        auth.set_parent_password("parent")
        ok, _ = auth.verify_parent_password("parent")
        assert ok is True

    def test_verify_parent_password_wrong(self, auth):
        auth.set_parent_password("parent")
        ok, _ = auth.verify_parent_password("wrong")
        assert ok is False

    def test_verify_session_legacy_migrates(self, auth):
        import hashlib
        legacy = hashlib.sha256("old".encode()).hexdigest()
        auth._storage.set("password_hash", legacy)
        ok, migrated = auth.verify_session_password("old")
        assert ok is True
        assert migrated is not None
        assert ":" in migrated


# ═══════════════════════════════════════════════════════════════════════════
# Throttling
# ═══════════════════════════════════════════════════════════════════════════

class TestThrottling:

    def test_no_throttle_initially(self, auth):
        assert auth.throttle_delay() == 0

    def test_throttle_after_one_failure(self, auth):
        h = hash_password("pw")
        auth.verify("wrong", h)
        delay = auth.throttle_delay()
        assert delay >= 1
        assert delay <= 2

    def test_throttle_doubles_after_each_failure(self, auth):
        h = hash_password("pw")
        delays = []
        for _ in range(3):
            auth.verify("wrong", h)
            delays.append(auth.throttle_delay())
        assert delays[0] <= delays[1] <= delays[2]

    def test_throttle_capped_at_30(self, auth):
        h = hash_password("pw")
        for _ in range(10):
            auth.verify("wrong", h)
        assert auth.throttle_delay() <= 30

    def test_throttle_resets_on_success(self, auth):
        h = hash_password("pw")
        auth.verify("wrong", h)
        auth.verify("wrong", h)
        assert auth.throttle_delay() > 0
        auth.verify("pw", h)
        assert auth.throttle_delay() == 0

    def test_throttle_expires_after_delay(self, auth):
        h = hash_password("pw")
        auth._fail_count = 1
        auth._last_fail = time.time() - 10
        assert auth.throttle_delay() == 0

    def test_clear_failures(self, auth):
        auth._fail_count = 5
        auth._clear_failures()
        assert auth.throttle_delay() == 0
        assert auth._fail_count == 0

    def test_record_failure(self, auth):
        before = time.time()
        auth._record_failure()
        assert auth._fail_count == 1
        assert auth._last_fail >= before
