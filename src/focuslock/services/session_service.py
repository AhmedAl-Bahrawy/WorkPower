"""Session service — timer lifecycle, work-time tracking, session recording."""


class SessionService:
    """Orchestrates the Pomodoro timer and tracks actual work time."""

    def __init__(self, storage, timer):
        self._storage = storage
        self._timer = timer
        self._work_start_time = None
        self._actual_work_minutes = 0.0

    @property
    def timer(self):
        return self._timer

    def replace_timer(self, timer):
        """Swap in a new PomodoroTimer instance (after preset change)."""
        self._timer = timer

    # ── Work-time tracking ──────────────────────────────────────────────
    def track_start(self):
        """Mark the beginning of a work interval."""
        if self._timer.phase == "work":
            import time
            self._work_start_time = time.time()

    def track_pause(self):
        """Accumulate elapsed work time since last track_start."""
        if self._work_start_time is not None:
            import time
            elapsed = time.time() - self._work_start_time
            self._actual_work_minutes += elapsed / 60.0
            self._work_start_time = None

    def track_reset(self):
        """Clear all work-time tracking state."""
        self._work_start_time = None
        self._actual_work_minutes = 0.0

    @property
    def actual_work_minutes(self):
        return self._actual_work_minutes

    # ── Session recording ───────────────────────────────────────────────
    def record_session(self):
        """Record the completed work session to storage."""
        if self._actual_work_minutes > 0:
            work_min = max(1, round(self._actual_work_minutes))
        else:
            work_min = self._timer.work_sec // 60
        self._storage.record_session(work_min)
        self.track_reset()
