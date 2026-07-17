"""Force-kill blocked processes during focus sessions."""

import subprocess
import threading
import time
import logging

logger = logging.getLogger(__name__)

# Processes that must never be killed — Windows-critical or self-referential.
CRITICAL_PROCESSES = frozenset({
    "explorer.exe",
    "dwm.exe",
    "csrss.exe",
    "winlogon.exe",
    "svchost.exe",
    "lsass.exe",
    "services.exe",
    "smss.exe",
    "wininit.exe",
    "taskmgr.exe",
    "conhost.exe",
    "sihost.exe",
    "fontdrvhost.exe",
    "textinputhost.exe",
    "shellhost.exe",
    "runtimebroker.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "gameinputsvc.exe",
    "system",
    "idle",
    "python.exe",
    "pythonw.exe",
    "focuslock.exe",
})


class AppBlocker:
    """Monitors running processes and kills any that are in the enabled set.

    Only one monitoring thread runs at a time – calling ``start()`` while
    already running is a safe no-op.
    """

    def __init__(self):
        self._enabled = set()
        self._running = False
        self._lock = threading.Lock()

    @staticmethod
    def is_safe_to_block(exe_name):
        """Return True if *exe_name* is not in the critical-process denylist."""
        return exe_name.lower() not in CRITICAL_PROCESSES

    def set_enabled_apps(self, apps):
        """Replace the set of exe names that should be killed.

        Silently filters out any critical processes from the list.
        """
        filtered = []
        for a in apps:
            if self.is_safe_to_block(a):
                filtered.append(a)
            else:
                logger.warning("Blocked critical process '%s' from blocklist", a)
        with self._lock:
            self._enabled = {a.lower() for a in filtered}

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            self._kill()
            time.sleep(2)

    def _kill(self):
        with self._lock:
            targets = set(self._enabled)
        if not targets:
            return
        try:
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                parts = line.strip().strip('"').split('","')
                if len(parts) < 2:
                    continue
                exe = parts[0].lower()
                if exe in targets and self.is_safe_to_block(parts[0]):
                    subprocess.run(
                        ["taskkill", "/F", "/PID", parts[1]],
                        capture_output=True,
                    )
        except Exception as exc:
            logger.debug("AppBlocker tasklist error: %s", exc)
