"""Authentication service — password set/verify/clear with throttling."""

import time
from ..core.security import hash_password, verify_password


class AuthService:
    """Manages password state and verification with exponential-backoff throttling."""

    def __init__(self, storage):
        self._storage = storage
        self._fail_count = 0
        self._last_fail = 0.0

    # ── Password hash accessors ─────────────────────────────────────────
    def password_hash(self):
        return self._storage.get("password_hash", "")

    def parent_password_hash(self):
        return self._storage.get("parent_password_hash", "")

    def has_password(self):
        return bool(self.password_hash())

    def has_parent_password(self):
        return bool(self.parent_password_hash())

    # ── Throttling ──────────────────────────────────────────────────────
    def throttle_delay(self):
        """Return seconds to wait, or 0 if no throttle is active."""
        if self._fail_count <= 0:
            return 0
        delay = min(2 ** self._fail_count, 30)
        elapsed = time.time() - self._last_fail
        if elapsed < delay:
            return int(delay - elapsed)
        return 0

    def _record_failure(self):
        self._fail_count += 1
        self._last_fail = time.time()

    def _clear_failures(self):
        self._fail_count = 0

    # ── Verify ──────────────────────────────────────────────────────────
    def verify(self, plain_text, stored_hash):
        """Verify a password. Returns (ok, migrated_hash_or_None).

        On success, resets the failure counter.
        On failure, increments it and records the timestamp.
        """
        ok, new_hash = verify_password(plain_text, stored_hash)
        if ok:
            self._clear_failures()
        else:
            self._record_failure()
        return ok, new_hash

    def verify_session_password(self, plain_text):
        """Verify against the session password. Returns (ok, migrated_hash)."""
        ph = self.password_hash()
        if not ph:
            return True, None
        return self.verify(plain_text, ph)

    def verify_parent_password(self, plain_text):
        """Verify against the parent password. Returns (ok, migrated_hash)."""
        ph = self.parent_password_hash()
        if not ph:
            return True, None
        return self.verify(plain_text, ph)

    # ── Set / Clear ─────────────────────────────────────────────────────
    def set_session_password(self, new_plain):
        h = hash_password(new_plain)
        self._storage.set("password_hash", h)
        return h

    def set_parent_password(self, new_plain):
        h = hash_password(new_plain)
        self._storage.set("parent_password_hash", h)
        return h

    def clear_all(self):
        self._storage.set("password_hash", "")
        self._storage.set("parent_password_hash", "")
