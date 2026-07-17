"""Unit tests for focuslock.core.timer — PomodoroTimer."""

import threading
import time

import pytest

from focuslock.core.timer import PomodoroTimer


# ── helpers ──────────────────────────────────────────────────────────────
def _make_timer(work=1, break_min=1, long_break=2, cycles=2, **kw):
    """Create a PomodoroTimer with durations in *minutes*."""
    return PomodoroTimer(
        work_min=work,
        break_min=break_min,
        long_break_min=long_break,
        cycles_per_set=cycles,
        **kw,
    )


# ── basic construction ──────────────────────────────────────────────────
class TestConstruction:
    def test_initial_state(self):
        t = _make_timer(work=1, break_min=1)
        assert t.phase == "work"
        assert t.remaining == 60  # 1 min
        assert not t.is_running
        assert t.cycles == 0

    def test_long_break_defaults_to_work_if_zero(self):
        t = PomodoroTimer(work_min=5, break_min=1, long_break_min=0)
        assert t.long_break_sec == 5 * 60

    def test_cycles_per_set_minimum_is_one(self):
        t = PomodoroTimer(work_min=1, break_min=1, cycles_per_set=0)
        assert t.cycles_per_set == 1


# ── start / pause / reset ───────────────────────────────────────────────
class TestControls:
    def test_start_sets_running(self):
        t = _make_timer(work=10)
        t.start()
        assert t.is_running
        t.pause()
        assert not t.is_running

    def test_pause_is_idempotent(self):
        t = _make_timer(work=10)
        t.pause()
        assert not t.is_running

    def test_reset_restores_initial_state(self):
        t = _make_timer(work=2, break_min=1)
        t.start()
        time.sleep(0.1)
        t.reset()
        assert t.phase == "work"
        assert t.remaining == 120
        assert t.cycles == 0
        assert not t.is_running

    def test_start_is_noop_when_already_running(self):
        """BUG-04: start() should not spawn a second thread."""
        t = _make_timer(work=10)
        t.start()
        # Second start should be a no-op
        t.start()
        assert t.is_running
        t.pause()


# ── BUG-04: start() reentrancy ─────────────────────────────────────────
class TestStartReentrancy:
    def test_concurrent_start_calls_spawn_single_thread(self):
        """Two near-simultaneous start() calls must not spawn two loops."""
        t = _make_timer(work=60)
        barrier = threading.Barrier(2)

        def _threaded_start():
            barrier.wait()
            t.start()

        threads = [threading.Thread(target=_threaded_start) for _ in range(2)]
        threads[0].start()
        threads[1].start()
        threads[0].join(timeout=2)
        threads[1].join(timeout=2)

        assert t.is_running
        t.pause()
        time.sleep(0.1)
        # If reentrancy guard works, timer should still be in "work" phase
        assert t.phase == "work"


# ── BUG-02: set_remaining clamp ─────────────────────────────────────────
class TestSetRemaining:
    def test_clamp_work_phase(self):
        t = _make_timer(work=10, break_min=5)
        t.set_remaining(9999)
        assert t.remaining == 600  # 10 min cap

    def test_clamp_short_break(self):
        t = _make_timer(work=10, break_min=5)
        t.set_phase("break")
        t.set_remaining(9999)
        assert t.remaining == 300  # 5 min cap

    def test_clamp_long_break(self):
        """BUG-02: set_remaining must clamp against long_break_sec during long breaks."""
        t = _make_timer(work=10, break_min=5, long_break=20, cycles=2)
        t.cycles = 2  # Simulate completing a set
        t.set_phase("break")
        t.set_remaining(9999)
        # Should clamp to long_break (20 min), not short break (5 min)
        assert t.remaining == 1200


# ── phase_total ─────────────────────────────────────────────────────────
class TestPhaseTotal:
    def test_work_total(self):
        t = _make_timer(work=10, break_min=5)
        assert t.phase_total == 600

    def test_short_break_total(self):
        t = _make_timer(work=10, break_min=5, long_break=20, cycles=4)
        t.set_phase("break")
        assert t.phase_total == 300

    def test_long_break_total(self):
        t = _make_timer(work=10, break_min=5, long_break=20, cycles=2)
        t.cycles = 2
        t.set_phase("break")
        assert t.phase_total == 1200

    def test_phase_total_work_unaffected_by_cycles(self):
        t = _make_timer(work=10, break_min=5, cycles=4)
        t.cycles = 4
        assert t.phase_total == 600  # still work_sec


# ── phase transitions (fast tests) ──────────────────────────────────────
class TestPhaseTransitions:
    def test_work_to_break_via_skip(self):
        """Use skip() to test transition without waiting for timer."""
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=4)
        t.start()
        time.sleep(0.1)
        t.skip()
        # Wait for the skip to process
        deadline = time.time() + 2
        while t.phase == "work" and time.time() < deadline:
            time.sleep(0.05)
        assert t.phase == "break"
        t.pause()

    def test_long_break_after_cycles_via_skip(self):
        """After cycles_per_set work phases, a long break occurs."""
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=2)
        t.cycles = 1  # One more work phase will trigger long break
        t._phase = "work"
        t._rem = 1
        t.start()
        deadline = time.time() + 3
        while t.phase == "work" and time.time() < deadline:
            time.sleep(0.05)
        # Should now be in break with long break duration
        assert t.phase == "break"
        assert 299 <= t.remaining <= 300  # 5 min long break (timing tolerance)
        t.pause()

    def test_short_break_after_non_set_cycle_via_skip(self):
        """After a work phase that doesn't complete a set, short break."""
        t = _make_timer(work=10, break_min=3, long_break=10, cycles=4)
        t.start()
        time.sleep(0.1)
        t.skip()
        deadline = time.time() + 2
        while t.phase == "work" and time.time() < deadline:
            time.sleep(0.05)
        assert t.phase == "break"
        assert 179 <= t.remaining <= 180  # 3 min short break (timing tolerance)
        t.pause()

    def test_skip_is_noop_when_paused(self):
        """skip() should not transition when timer is not running."""
        t = _make_timer(work=10, break_min=1)
        t.skip()
        assert t.phase == "work"
        assert t.remaining == 600


# ── callbacks ───────────────────────────────────────────────────────────
class TestCallbacks:
    def test_on_tick_fires(self):
        ticks = []
        t = _make_timer(work=10, break_min=1)
        t.on_tick = lambda rem, phase: ticks.append((rem, phase))
        t.start()
        time.sleep(1.5)
        t.pause()
        assert len(ticks) >= 1

    def test_on_phase_fires_on_transition(self):
        phases = []
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=4)
        t.on_phase = lambda ph, cyc: phases.append(ph)
        t.start()
        time.sleep(0.1)
        t.skip()
        deadline = time.time() + 2
        while "break" not in phases and time.time() < deadline:
            time.sleep(0.05)
        assert "break" in phases
        t.pause()


# ── thread safety ───────────────────────────────────────────────────────
class TestThreadSafety:
    def test_concurrent_read_write(self):
        """Properties should not raise under concurrent access."""
        t = _make_timer(work=10, break_min=5)
        t.start()
        errors = []

        def _reader():
            try:
                for _ in range(50):
                    _ = t.remaining
                    _ = t.phase
                    _ = t.is_running
                    _ = t.phase_total
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_reader) for _ in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5)
        t.pause()
        assert not errors
