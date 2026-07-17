"""Tests for focuslock.services.session_service — SessionService.

Covers: work-time tracking, session recording, timer replacement, and edge cases.
"""

import time

import pytest

from focuslock.config import Storage
from focuslock.core.timer import PomodoroTimer
from focuslock.services.session_service import SessionService


# ── stubs ─────────────────────────────────────────────────────────────────

class FakeTimer:
    """Lightweight timer stub — no threads, fully controllable."""

    def __init__(self, work_min=25, break_min=5):
        self.work_sec = work_min * 60
        self.break_sec = break_min * 60
        self._phase = "work"
        self._remaining = self.work_sec
        self.is_running = False

    @property
    def phase(self):
        return self._phase

    @property
    def remaining(self):
        return self._remaining

    def set_phase(self, p):
        self._phase = p

    def set_remaining(self, r):
        self._remaining = r


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
def timer():
    return FakeTimer(work_min=25, break_min=5)


@pytest.fixture
def svc(storage, timer):
    return SessionService(storage, timer)


# ═══════════════════════════════════════════════════════════════════════════
# Timer replacement
# ═══════════════════════════════════════════════════════════════════════════

class TestReplaceTimer:

    def test_replace_timer_updates_ref(self, svc):
        new_timer = FakeTimer(work_min=10, break_min=2)
        svc.replace_timer(new_timer)
        assert svc.timer is new_timer

    def test_initial_timer_ref(self, svc, timer):
        assert svc.timer is timer


# ═══════════════════════════════════════════════════════════════════════════
# Work-time tracking
# ═══════════════════════════════════════════════════════════════════════════

class TestWorkTimeTracking:

    def test_initial_work_minutes_zero(self, svc):
        assert svc.actual_work_minutes == 0.0

    def test_track_start_records_time(self, svc):
        svc.track_start()
        assert svc._work_start_time is not None

    def test_track_start_only_in_work_phase(self, svc, timer):
        timer.set_phase("break")
        svc.track_start()
        assert svc._work_start_time is None

    def test_track_pause_accumulates_minutes(self, svc):
        svc.track_start()
        time.sleep(0.05)
        svc.track_pause()
        assert svc.actual_work_minutes > 0

    def test_track_pause_clears_start_time(self, svc):
        svc.track_start()
        svc.track_pause()
        assert svc._work_start_time is None

    def test_track_pause_noop_without_start(self, svc):
        svc.track_pause()
        assert svc.actual_work_minutes == 0.0

    def test_track_reset_clears_everything(self, svc):
        svc.track_start()
        time.sleep(0.01)
        svc.track_pause()
        svc.track_reset()
        assert svc.actual_work_minutes == 0.0
        assert svc._work_start_time is None

    def test_multiple_start_pause_accumulates(self, svc):
        svc.track_start()
        time.sleep(0.05)
        svc.track_pause()
        first = svc.actual_work_minutes

        svc.track_start()
        time.sleep(0.05)
        svc.track_pause()
        assert svc.actual_work_minutes > first


# ═══════════════════════════════════════════════════════════════════════════
# Session recording
# ═══════════════════════════════════════════════════════════════════════════

class TestRecordSession:

    def test_record_session_uses_actual_minutes(self, svc, storage):
        svc._actual_work_minutes = 15.3
        svc.record_session()
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 1
        assert total_mins == 15

    def test_record_session_clamps_to_minimum_one(self, svc, storage):
        svc._actual_work_minutes = 0.1
        svc.record_session()
        _, total_mins = storage.get_total_stats()
        assert total_mins >= 1

    def test_record_session_falls_back_to_timer_work_sec(self, svc, storage):
        svc.record_session()
        _, total_mins = storage.get_total_stats()
        assert total_mins == 25

    def test_record_session_resets_tracking(self, svc, storage):
        svc._actual_work_minutes = 10.0
        svc._work_start_time = time.time()
        svc.record_session()
        assert svc.actual_work_minutes == 0.0
        assert svc._work_start_time is None

    def test_record_multiple_sessions(self, svc, storage):
        svc._actual_work_minutes = 10.0
        svc.record_session()
        svc._actual_work_minutes = 20.0
        svc.record_session()
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 2
        assert total_mins == 30
