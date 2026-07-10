"""Pomodoro timer with work/break phases."""

import threading
import time


class PomodoroTimer:
    def __init__(self, work_min, break_min, on_tick=None, on_phase=None):
        self.work_sec = work_min * 60
        self.break_sec = break_min * 60
        self.on_tick = on_tick
        self.on_phase = on_phase
        self._rem = self.work_sec
        self._phase = "work"
        self._on = False
        self.cycles = 0

    @property
    def phase(self):
        return self._phase

    @property
    def remaining(self):
        return self._rem

    def start(self):
        if self._on:
            return
        self._on = True
        threading.Thread(target=self._loop, daemon=True).start()

    def pause(self):
        self._on = False

    def reset(self):
        self._on = False
        self._phase = "work"
        self._rem = self.work_sec
        self.cycles = 0
        if self.on_tick:
            self.on_tick(self._rem, self._phase)

    def _loop(self):
        while self._on and self._rem > 0:
            time.sleep(1)
            if not self._on:
                return
            self._rem -= 1
            if self.on_tick:
                self.on_tick(self._rem, self._phase)
        if self._on and self._rem <= 0:
            self._switch()

    def _switch(self):
        if self._phase == "work":
            self.cycles += 1
            self._phase = "break"
            self._rem = self.break_sec
        else:
            self._phase = "work"
            self._rem = self.work_sec
        if self.on_phase:
            self.on_phase(self._phase, self.cycles)
        threading.Thread(target=self._loop, daemon=True).start()
