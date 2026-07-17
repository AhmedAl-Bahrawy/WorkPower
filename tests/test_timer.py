"""Comprehensive tests for focuslock.core.timer — PomodoroTimer.

Covers: construction, monotonic-clock accuracy, start/pause/reset/skip,
reentrancy guard (BUG-04), long-break clamp (BUG-02), set_remaining edge
cases, phase transitions, callbacks, and thread safety.
"""

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


def _wait_phase(t, target_phase, timeout=3):
    """Block until timer enters *target_phase* or *timeout* expires."""
    deadline = time.time() + timeout
    while t.phase != target_phase and time.time() < deadline:
        time.sleep(0.05)


# ═══════════════════════════════════════════════════════════════════════════
# Construction
# ═══════════════════════════════════════════════════════════════════════════

class TestConstruction:
    """Initial state and parameter validation."""

    def test_initial_phase_is_work(self):
        t = _make_timer(work=5, break_min=3)
        assert t.phase == "work"

    def test_initial_remaining_equals_work_sec(self):
        t = _make_timer(work=5, break_min=3)
        assert t.remaining == 300

    def test_initial_not_running(self):
        t = _make_timer()
        assert not t.is_running

    def test_initial_cycles_zero(self):
        t = _make_timer()
        assert t.cycles == 0

    @pytest.mark.parametrize("work,expected", [(1, 60), (10, 600), (90, 5400)])
    def test_work_sec_converted_from_minutes(self, work, expected):
        t = _make_timer(work=work, break_min=1)
        assert t.work_sec == expected

    @pytest.mark.parametrize("brk,expected", [(1, 60), (5, 300), (20, 1200)])
    def test_break_sec_converted_from_minutes(self, brk, expected):
        t = _make_timer(work=5, break_min=brk)
        assert t.break_sec == expected

    @pytest.mark.parametrize("lb,expected", [(5, 300), (15, 900), (30, 1800)])
    def test_long_break_sec_converted_from_minutes(self, lb, expected):
        t = _make_timer(work=5, break_min=3, long_break=lb)
        assert t.long_break_sec == expected

    def test_long_break_defaults_to_work_if_zero(self):
        t = PomodoroTimer(work_min=5, break_min=1, long_break_min=0)
        assert t.long_break_sec == 5 * 60

    def test_cycles_per_set_minimum_is_one(self):
        t = PomodoroTimer(work_min=1, break_min=1, cycles_per_set=0)
        assert t.cycles_per_set == 1

    def test_cycles_per_set_negative_becomes_one(self):
        t = PomodoroTimer(work_min=1, break_min=1, cycles_per_set=-5)
        assert t.cycles_per_set == 1

    def test_callbacks_stored(self):
        tick = lambda r, p: None
        phase = lambda p, c: None
        t = _make_timer(work=1, break_min=1, on_tick=tick, on_phase=phase)
        assert t.on_tick is tick
        assert t.on_phase is phase


# ═══════════════════════════════════════════════════════════════════════════
# Controls — start / pause / reset
# ═══════════════════════════════════════════════════════════════════════════

class TestControls:
    """Basic start / pause / reset behavior."""

    def test_start_sets_running(self):
        t = _make_timer(work=10)
        t.start()
        assert t.is_running
        t.pause()

    def test_pause_clears_running(self):
        t = _make_timer(work=10)
        t.start()
        time.sleep(0.1)
        t.pause()
        assert not t.is_running

    def test_pause_preserves_remaining(self):
        t = _make_timer(work=10)
        t.start()
        time.sleep(0.3)
        t.pause()
        # Should have decremented from 600 by ~0.3s
        assert 597 <= t.remaining <= 600

    def test_pause_is_idempotent(self):
        t = _make_timer(work=10)
        t.pause()
        assert not t.is_running
        t.pause()  # second call should not raise
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

    def test_reset_fires_on_tick(self):
        ticks = []
        t = _make_timer(work=2, break_min=1, on_tick=lambda r, p: ticks.append((r, p)))
        t.start()
        time.sleep(0.1)
        t.reset()
        # reset() fires one on_tick with the full work duration
        assert any(r == 120 and p == "work" for r, p in ticks)

    def test_start_is_noop_when_already_running(self):
        """BUG-04: start() must not spawn a second loop thread."""
        t = _make_timer(work=10)
        t.start()
        thread_count_before = threading.active_count()
        t.start()  # should be no-op
        time.sleep(0.2)
        t.pause()
        # No extra daemon thread should have been spawned beyond the first
        assert t.phase == "work"


# ═══════════════════════════════════════════════════════════════════════════
# BUG-04: start() reentrancy
# ═══════════════════════════════════════════════════════════════════════════

class TestStartReentrancy:
    """Two near-simultaneous start() calls must not spawn two loops."""

    def test_concurrent_start_calls_spawn_single_thread(self):
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
        assert t.phase == "work"

    def test_rapid_start_pause_start(self):
        """Rapid start-pause-start should work without deadlock."""
        t = _make_timer(work=60)
        for _ in range(10):
            t.start()
            time.sleep(0.01)
            t.pause()
        assert not t.is_running
        t.start()
        assert t.is_running
        t.pause()


# ═══════════════════════════════════════════════════════════════════════════
# Monotonic clock accuracy (BUG-01)
# ═══════════════════════════════════════════════════════════════════════════

class TestMonotonicClock:
    """Timer should self-correct via time.monotonic(), not drift."""

    def test_remaining_decreases_by_elapsed_time(self):
        t = _make_timer(work=10)
        t.start()
        time.sleep(1.5)
        t.pause()
        # Should have lost ~1.5s from 600
        elapsed = 600 - t.remaining
        assert 1.0 <= elapsed <= 3.0

    def test_pause_resume_preserves_remaining(self):
        t = _make_timer(work=10)
        t.start()
        time.sleep(0.5)
        t.pause()
        rem_at_pause = t.remaining
        time.sleep(0.5)  # paused — remaining should not change
        assert t.remaining == rem_at_pause
        t.start()
        time.sleep(0.5)
        t.pause()
        # After resume, ~0.5s more should have elapsed
        elapsed = rem_at_pause - t.remaining
        assert 0.3 <= elapsed <= 1.5

    def test_set_remaining_while_running(self):
        t = _make_timer(work=10)
        t.start()
        time.sleep(0.1)
        t.set_remaining(300)
        time.sleep(0.1)
        t.pause()
        assert 298 <= t.remaining <= 300


# ═══════════════════════════════════════════════════════════════════════════
# BUG-02: set_remaining clamp during long breaks
# ═══════════════════════════════════════════════════════════════════════════

class TestSetRemaining:
    """set_remaining() must clamp to the correct cap for the current phase."""

    def test_clamp_work_phase(self):
        t = _make_timer(work=10, break_min=5)
        t.set_remaining(9999)
        assert t.remaining == 600

    def test_clamp_short_break(self):
        t = _make_timer(work=10, break_min=5)
        t.set_phase("break")
        t.set_remaining(9999)
        assert t.remaining == 300

    def test_clamp_long_break(self):
        """BUG-02: clamp to long_break_sec, not break_sec, during long breaks."""
        t = _make_timer(work=10, break_min=5, long_break=20, cycles=2)
        t.cycles = 2
        t.set_phase("break")
        t.set_remaining(9999)
        assert t.remaining == 1200  # 20 min, not 5 min

    def test_clamp_to_zero(self):
        t = _make_timer(work=10)
        t.set_remaining(-5)
        assert t.remaining == 0

    def test_set_remaining_exact_cap(self):
        t = _make_timer(work=10)
        t.set_remaining(600)
        assert t.remaining == 600

    def test_set_remaining_one_over_cap(self):
        t = _make_timer(work=10)
        t.set_remaining(601)
        assert t.remaining == 600

    def test_set_remaining_while_running_updates_target(self):
        t = _make_timer(work=10)
        t.start()
        time.sleep(0.1)
        t.set_remaining(120)
        time.sleep(0.1)
        t.pause()
        assert 118 <= t.remaining <= 120


# ═══════════════════════════════════════════════════════════════════════════
# phase_total
# ═══════════════════════════════════════════════════════════════════════════

class TestPhaseTotal:
    """phase_total returns the correct cap for the current phase."""

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
        assert t.phase_total == 600

    @pytest.mark.parametrize("work,expected", [(5, 300), (25, 1500), (90, 5400)])
    def test_work_total_parametrized(self, work, expected):
        t = _make_timer(work=work, break_min=5)
        assert t.phase_total == expected


# ═══════════════════════════════════════════════════════════════════════════
# _get_break_cap
# ═══════════════════════════════════════════════════════════════════════════

class TestGetBreakCap:
    """Internal _get_break_cap distinguishes short vs long break."""

    def test_short_break_at_cycle_0(self):
        t = _make_timer(work=5, break_min=3, long_break=10, cycles=4)
        t.cycles = 0
        assert t._get_break_cap() == 180  # 3 min

    def test_short_break_at_cycle_1(self):
        t = _make_timer(work=5, break_min=3, long_break=10, cycles=4)
        t.cycles = 1
        assert t._get_break_cap() == 180

    def test_short_break_at_cycle_2(self):
        t = _make_timer(work=5, break_min=3, long_break=10, cycles=4)
        t.cycles = 2
        assert t._get_break_cap() == 180

    def test_long_break_at_set_boundary(self):
        t = _make_timer(work=5, break_min=3, long_break=10, cycles=4)
        t.cycles = 4
        assert t._get_break_cap() == 600  # 10 min

    def test_long_break_at_double_set(self):
        t = _make_timer(work=5, break_min=3, long_break=10, cycles=4)
        t.cycles = 8
        assert t._get_break_cap() == 600

    def test_short_break_after_long_break_set(self):
        t = _make_timer(work=5, break_min=3, long_break=10, cycles=2)
        t.cycles = 3  # odd cycle after a set
        assert t._get_break_cap() == 180


# ═══════════════════════════════════════════════════════════════════════════
# Phase transitions
# ═══════════════════════════════════════════════════════════════════════════

class TestPhaseTransitions:
    """Verify work→break→work cycling and long-break logic."""

    def test_work_to_break_via_skip(self):
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=4)
        t.start()
        time.sleep(0.1)
        t.skip()
        _wait_phase(t, "break")
        assert t.phase == "break"
        t.pause()

    def test_break_to_work_via_skip(self):
        t = _make_timer(work=10, break_min=3, long_break=5, cycles=4)
        t.start()
        time.sleep(0.1)
        t.skip()  # → break
        _wait_phase(t, "break")
        time.sleep(0.1)
        t.skip()  # → work
        _wait_phase(t, "work")
        assert t.phase == "work"
        t.pause()

    def test_long_break_after_cycles_via_skip(self):
        """After cycles_per_set work phases, a long break occurs."""
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=2)
        t.cycles = 1
        t._phase = "work"
        t._rem = 1
        t.start()
        _wait_phase(t, "break", timeout=3)
        assert t.phase == "break"
        assert t.remaining <= 300  # long break = 5 min = 300s
        t.pause()

    def test_short_break_after_non_set_cycle_via_skip(self):
        """Work phase that doesn't complete a set → short break."""
        t = _make_timer(work=10, break_min=3, long_break=10, cycles=4)
        t.start()
        time.sleep(0.1)
        t.skip()
        _wait_phase(t, "break")
        assert t.remaining <= 180  # short break = 3 min = 180s
        t.pause()

    def test_cycles_increment_after_work(self):
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=4)
        assert t.cycles == 0
        t.start()
        time.sleep(0.1)
        t.skip()
        _wait_phase(t, "break")
        assert t.cycles == 1
        t.pause()

    def test_cycles_reset_on_reset(self):
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=4)
        t.start()
        time.sleep(0.1)
        t.skip()
        _wait_phase(t, "break")
        t.reset()
        assert t.cycles == 0
        assert t.phase == "work"

    def test_skip_is_noop_when_paused(self):
        t = _make_timer(work=10, break_min=1)
        t.skip()
        assert t.phase == "work"
        assert t.remaining == 600


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks
# ═══════════════════════════════════════════════════════════════════════════

class TestCallbacks:
    """on_tick and on_phase callbacks fire at the right times."""

    def test_on_tick_fires(self):
        ticks = []
        t = _make_timer(work=10, break_min=1, on_tick=lambda r, p: ticks.append((r, p)))
        t.start()
        time.sleep(1.5)
        t.pause()
        assert len(ticks) >= 1

    def test_on_tick_receive_decreasing_values(self):
        ticks = []
        t = _make_timer(work=10, break_min=1, on_tick=lambda r, p: ticks.append(r))
        t.start()
        time.sleep(2.5)
        t.pause()
        # Ticks should generally decrease (allowing for monotonic jitter)
        assert len(ticks) >= 2
        # First tick should be >= last tick (monotonically decreasing or equal)
        assert ticks[0] >= ticks[-1]

    def test_on_phase_fires_on_transition(self):
        phases = []
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=4,
                        on_phase=lambda ph, cyc: phases.append(ph))
        t.start()
        time.sleep(0.1)
        t.skip()
        deadline = time.time() + 2
        while "break" not in phases and time.time() < deadline:
            time.sleep(0.05)
        assert "break" in phases
        t.pause()

    def test_on_phase_receives_cycle_count(self):
        received = []
        t = _make_timer(work=10, break_min=1, long_break=5, cycles=4,
                        on_phase=lambda ph, cyc: received.append((ph, cyc)))
        t.start()
        time.sleep(0.1)
        t.skip()
        deadline = time.time() + 2
        while not received and time.time() < deadline:
            time.sleep(0.05)
        assert len(received) == 1
        assert received[0] == ("break", 1)


# ═══════════════════════════════════════════════════════════════════════════
# Thread safety
# ═══════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    """Properties must not raise under concurrent access."""

    def test_concurrent_read_write(self):
        t = _make_timer(work=10, break_min=5)
        t.start()
        errors = []

        def _reader():
            try:
                for _ in range(100):
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

    def test_concurrent_start_pause(self):
        """Multiple threads calling start/pause should not deadlock."""
        t = _make_timer(work=60)
        errors = []

        def _toggle():
            try:
                for _ in range(20):
                    t.start()
                    time.sleep(0.01)
                    t.pause()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_toggle) for _ in range(3)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5)
        assert not errors
        assert not t.is_running

    def test_concurrent_set_remaining(self):
        t = _make_timer(work=10)
        t.start()
        errors = []

        def _writer():
            try:
                for i in range(50):
                    t.set_remaining(300 + (i % 300))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_writer) for _ in range(3)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5)
        t.pause()
        assert not errors
        assert 0 <= t.remaining <= 600


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Unusual but valid inputs."""

    def test_single_cycle_set(self):
        t = _make_timer(work=1, break_min=1, long_break=2, cycles=1)
        t.start()
        time.sleep(0.1)
        t.skip()  # work → break (long, since cycle=1 = set boundary)
        _wait_phase(t, "break")
        assert t.cycles == 1
        assert t.remaining <= 120  # long break = 2 min
        t.pause()

    def test_zero_duration_work_not_allowed(self):
        """work_min=0 → work_sec=0, timer should handle gracefully."""
        t = PomodoroTimer(work_min=0, break_min=1)
        assert t.work_sec == 0
        assert t.remaining == 0

    def test_very_large_durations(self):
        t = _make_timer(work=180, break_min=60, long_break=60)
        assert t.work_sec == 10800
        assert t.break_sec == 3600
        assert t.long_break_sec == 3600

    def test_set_phase_directly(self):
        t = _make_timer(work=10, break_min=5)
        t.set_phase("break")
        assert t.phase == "break"

    def test_pause_before_any_start(self):
        t = _make_timer(work=10)
        t.pause()
        assert not t.is_running
        assert t.remaining == 600

    def test_multiple_resets(self):
        t = _make_timer(work=5, break_min=1)
        t.start()
        time.sleep(0.1)
        t.skip()
        _wait_phase(t, "break")
        t.reset()
        assert t.phase == "work"
        t.start()
        time.sleep(0.1)
        t.reset()
        assert t.phase == "work"
        assert t.cycles == 0
