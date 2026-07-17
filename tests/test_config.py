"""Unit tests for focuslock.config — Storage (SQLAlchemy + SQLite)."""

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from focuslock.config import Storage, Base, Setting, App, Site, DailyStat, _DEFAULTS


# ── fixture: isolated in-memory DB ──────────────────────────────────────
@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Create a Storage instance backed by a temp SQLite file."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("focuslock.config.DB_FILE", db_path)
    monkeypatch.setattr("focuslock.config.DATA_DIR", tmp_path)
    s = Storage()
    yield s
    s.close()


# ── settings ────────────────────────────────────────────────────────────
class TestSettings:
    def test_get_default(self, storage):
        assert storage.get("theme") == "dark"

    def test_set_and_get(self, storage):
        storage.set("theme", "light")
        assert storage.get("theme") == "light"

    def test_get_unknown_returns_none(self, storage):
        assert storage.get("nonexistent_key") is None

    def test_get_unknown_with_default(self, storage):
        assert storage.get("nonexistent_key", 42) == 42

    def test_set_serializes_json(self, storage):
        storage.set("count", 123)
        assert storage.get("count") == 123

    def test_set_overwrites(self, storage):
        storage.set("key", "a")
        storage.set("key", "b")
        assert storage.get("key") == "b"


# ── apps ────────────────────────────────────────────────────────────────
class TestApps:
    def test_add_and_get(self, storage):
        storage.add_app("test.exe", "Test App")
        apps = storage.get_apps()
        assert len(apps) == 1
        assert apps[0]["exe"] == "test.exe"
        assert apps[0]["name"] == "Test App"
        assert apps[0]["enabled"] is True

    def test_add_default_name(self, storage):
        storage.add_app("game.exe")
        apps = storage.get_apps()
        assert apps[0]["name"] == "game.exe"

    def test_remove_app(self, storage):
        storage.add_app("test.exe")
        storage.remove_app("test.exe")
        assert storage.get_apps() == []

    def test_remove_nonexistent(self, storage):
        storage.remove_app("nope.exe")  # should not raise

    def test_toggle_app(self, storage):
        storage.add_app("test.exe")
        storage.toggle_app("test.exe", False)
        assert storage.get_apps()[0]["enabled"] is False

    def test_get_enabled_apps(self, storage):
        storage.add_app("a.exe", enabled=True)
        storage.add_app("b.exe", enabled=False)
        enabled = storage.get_enabled_apps()
        assert "a.exe" in enabled
        assert "b.exe" not in enabled

    def test_upsert_app(self, storage):
        storage.add_app("x.exe", "X1")
        storage.add_app("x.exe", "X2")
        apps = storage.get_apps()
        assert len(apps) == 1
        assert apps[0]["name"] == "X2"


# ── sites ───────────────────────────────────────────────────────────────
class TestSites:
    def test_add_and_get(self, storage):
        storage.add_site("example.com")
        sites = storage.get_sites()
        assert len(sites) == 1
        assert sites[0]["domain"] == "example.com"

    def test_remove_site(self, storage):
        storage.add_site("example.com")
        storage.remove_site("example.com")
        assert storage.get_sites() == []

    def test_toggle_site(self, storage):
        storage.add_site("example.com")
        storage.toggle_site("example.com", False)
        assert storage.get_sites()[0]["enabled"] is False

    def test_get_enabled_sites(self, storage):
        storage.add_site("a.com", enabled=True)
        storage.add_site("b.com", enabled=False)
        enabled = storage.get_enabled_sites()
        assert "a.com" in enabled
        assert "b.com" not in enabled


# ── stats ───────────────────────────────────────────────────────────────
class TestStats:
    def test_record_session(self, storage):
        storage.record_session(25)
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 1
        assert total_mins == 25

    def test_record_multiple_sessions(self, storage):
        storage.record_session(25)
        storage.record_session(15)
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 2
        assert total_mins == 40

    def test_daily_stats(self, storage):
        storage.record_session(30)
        daily = storage.get_daily_stats(days=1)
        today = date.today().isoformat()
        assert today in daily
        assert daily[today]["sessions"] == 1
        assert daily[today]["minutes"] == 30

    def test_daily_stats_excludes_old(self, storage):
        # Record via raw to backdate
        old_date = (date.today() - timedelta(days=10)).isoformat()
        storage._record_raw(old_date, 1, 25)
        daily = storage.get_daily_stats(days=7)
        assert old_date not in daily

    def test_streak_no_data(self, storage):
        current, longest = storage.get_streak()
        assert current == 0
        assert longest == 0

    def test_streak_single_day(self, storage):
        storage.record_session(25)
        current, longest = storage.get_streak()
        assert current >= 1
        assert longest >= 1

    def test_record_raw(self, storage):
        storage._record_raw("2025-01-01", 3, 75)
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 3
        assert total_mins == 75


# ── close ───────────────────────────────────────────────────────────────
class TestClose:
    def test_close_is_safe(self, storage):
        storage.close()
        # Should not raise
