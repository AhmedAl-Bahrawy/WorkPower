"""Running process discovery for the app picker."""

import json
import subprocess
from pathlib import Path


def _normalize_exe(name):
    name = (name or "").strip()
    if not name:
        return ""
    if not name.lower().endswith(".exe"):
        name += ".exe"
    return name.lower()


def _friendly_name(exe_name, path=""):
    stem = Path(exe_name).stem.replace("-", " ").replace("_", " ")
    if path:
        parent = Path(path).parent.name
        if parent.lower() not in ("bin", "app", "programs", "system32"):
            return f"{stem} ({parent})"
    return stem.title()


def list_running_processes():
    """Return unique running processes sorted by display name."""
    processes = {}

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process | Where-Object { $_.ProcessName } "
                "| Select-Object Id, ProcessName, Path "
                "| ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                exe = _normalize_exe(item.get("ProcessName", ""))
                if not exe or exe in ("python.exe", "pythonw.exe", "focuslock.exe"):
                    continue
                path = item.get("Path") or ""
                display = _friendly_name(exe, path)
                if exe not in processes:
                    processes[exe] = {
                        "exe": exe,
                        "display": display,
                        "pid": item.get("Id"),
                        "path": path,
                    }
    except Exception:
        pass

    if not processes:
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
                exe = _normalize_exe(parts[0])
                if not exe or exe in ("python.exe", "pythonw.exe"):
                    continue
                if exe not in processes:
                    processes[exe] = {
                        "exe": exe,
                        "display": _friendly_name(exe),
                        "pid": parts[1].strip('"'),
                        "path": "",
                    }
        except Exception:
            pass

    return sorted(processes.values(), key=lambda p: p["display"].lower())


def exe_from_path(path):
    """Extract normalized exe name from a file path."""
    if not path:
        return "", ""
    p = Path(path)
    exe = _normalize_exe(p.name)
    display = _friendly_name(exe, str(p))
    return exe, display
