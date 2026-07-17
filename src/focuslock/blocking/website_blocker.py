"""Hosts-file based website blocking."""

import os
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

HOSTS = Path(r"C:\Windows\System32\drivers\etc\hosts")
FL_START = "# FocusLock-START"
FL_END = "# FocusLock-END"


def _strip(content):
    """Remove everything between FocusLock markers."""
    out, inside = [], False
    for line in content.splitlines():
        if FL_START in line:
            inside = True
            continue
        if FL_END in line:
            inside = False
            continue
        if not inside:
            out.append(line)
    return "\n".join(out)


def normalize_domain(value):
    value = (value or "").strip().lower()
    for prefix in ("https://", "http://", "www."):
        if value.startswith(prefix):
            value = value[len(prefix):]
    value = value.split("/")[0].split("?")[0].split("#")[0]
    return value.strip(".")


def is_valid_domain(domain):
    if not domain or " " in domain or len(domain) > 253:
        return False
    parts = domain.split(".")
    if len(parts) < 2:
        return False
    for part in parts:
        if not part or len(part) > 63:
            return False
        if not all(c.isalnum() or c == "-" for c in part):
            return False
        if part.startswith("-") or part.endswith("-"):
            return False
    return True


def _atomic_write(path, content):
    """Write *content* to *path* atomically via temp file + os.replace()."""
    dir_path = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def block_sites(domains):
    """Inject hosts-file entries for *domains* between FocusLock markers.

    Returns True on success, False on permission error.
    """
    clean = []
    for domain in domains:
        d = normalize_domain(domain)
        if d and d not in clean:
            clean.append(d)
    if not clean:
        return unblock_sites()
    try:
        content = _strip(HOSTS.read_text(encoding="utf-8"))
        entries = []
        for domain in clean:
            entries.append(f"127.0.0.1 {domain}")
            if not domain.startswith("www."):
                entries.append(f"127.0.0.1 www.{domain}")
        block = (
            f"\n{FL_START}\n"
            + "\n".join(entries)
            + f"\n{FL_END}\n"
        )
        _atomic_write(HOSTS, content + block)
        return True
    except PermissionError:
        logger.warning("Website block failed: insufficient permissions to write hosts file")
        return False
    except Exception as exc:
        logger.error("Unexpected error blocking sites: %s", exc)
        return False


def unblock_sites(_domains=None):
    """Remove all FocusLock entries from the hosts file.

    Returns True on success, False on failure.
    """
    try:
        content = _strip(HOSTS.read_text(encoding="utf-8"))
        _atomic_write(HOSTS, content)
        return True
    except PermissionError:
        logger.warning("Website unblock failed: insufficient permissions to write hosts file")
        return False
    except Exception as exc:
        logger.error("Unexpected error unblocking sites: %s", exc)
        return False
