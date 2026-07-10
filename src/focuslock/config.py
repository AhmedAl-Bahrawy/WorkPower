"""Configuration and statistics persistence."""

import json
import os
from pathlib import Path

from .constants import DEFAULT_APPS, DEFAULT_SITES

DATA_DIR = Path(os.getenv("APPDATA", ".")) / "FocusLock"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"
STATS_FILE = DATA_DIR / "stats.json"


def default_config():
    return {
        "blocklist": DEFAULT_APPS[:],
        "blocklist_meta": {},
        "website_blocklist": DEFAULT_SITES[:],
        "password_hash": "",
        "parent_password_hash": "",
        "block_websites": False,
        "pomodoro_work": 25,
        "pomodoro_break": 5,
        "theme": "dark",
        "run_on_startup": False,
        "minimize_to_tray": True,
        "notify_break": True,
        "session_name": "",
        "last_preset": "Classic (25/5)",
    }


def load_config():
    cfg = default_config()
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    if not isinstance(cfg.get("blocklist_meta"), dict):
        cfg["blocklist_meta"] = {}
    return cfg


def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def default_stats():
    return {
        "total_sessions": 0,
        "total_minutes": 0,
        "sessions_by_date": {},
        "current_streak": 0,
        "longest_streak": 0,
        "last_session_date": "",
    }


def load_stats():
    stats = default_stats()
    if STATS_FILE.exists():
        try:
            stats.update(json.loads(STATS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return stats


def save_stats(stats):
    STATS_FILE.write_text(json.dumps(stats, indent=2), encoding="utf-8")
