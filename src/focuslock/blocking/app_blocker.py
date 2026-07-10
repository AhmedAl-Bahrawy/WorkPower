"""Force-kill blocked processes during focus sessions."""

import subprocess
import threading
import time


class AppBlocker:
    def __init__(self, blocklist):
        self.blocklist = {b.lower() for b in blocklist}
        self._on = False
        self._lock = threading.Lock()

    def update_blocklist(self, blocklist):
        with self._lock:
            self.blocklist = {b.lower() for b in blocklist}

    def start(self):
        self._on = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._on = False

    def _loop(self):
        while self._on:
            self._kill()
            time.sleep(2)

    def _kill(self):
        with self._lock:
            targets = set(self.blocklist)
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
                if parts[0].lower() in targets:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", parts[1]],
                        capture_output=True,
                    )
        except Exception:
            pass
