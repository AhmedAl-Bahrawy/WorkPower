"""Windows UAC elevation helper.

Detects if the process is running as Administrator and relaunches
with a UAC prompt if not. Only used on Windows.
"""

import sys
import logging

logger = logging.getLogger(__name__)


def is_admin():
    """Return True if the current process has Administrator privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def request_elevation():
    """Relaunch the current script as Administrator via UAC prompt.

    Returns True if the elevated process was launched (caller should sys.exit).
    Returns False if elevation failed or is not supported.
    """
    try:
        import ctypes
        script = sys.argv[0]
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
        if ret > 32:
            return True
        logger.warning("ShellExecuteW returned %s — elevation denied or failed", ret)
        return False
    except Exception as exc:
        logger.error("Elevation failed: %s", exc)
        return False
