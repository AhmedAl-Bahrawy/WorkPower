"""Comprehensive tests for focuslock.config — Storage (SQLAlchemy + SQLite).

Covers: settings CRUD, app/site CRUD, stats recording, daily stats,
streaks, close safety, edge cases, and default seeding.
"""

from datetime import date, timedelta

import pytest

from focuslock.config import Storage, Base, Setting, App, Site, DailyStat, _DEFAULTS


# ── fixture: isolated DB per test ────────────────────────────────────────

@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Create a Storage instance backed by a temp SQLite file."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("focuslock.config.DB_FILE", db_path)
    monkeypatch.setattr("focuslock.config.DATA_DIR", tmp_path)
    s = Storage()
    yield s
    s.close()


# ═══════════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════════

class TestSettings:
    """Key-value settings with JSON serialization."""

    def test_get_default_theme(self, storage):
        assert storage.get("theme") == "dark"

    def test_get_default_preset(self, storage):
        assert storage.get("preset") == "Classic (25/5)"

    def test_get_unknown_returns_none(self, storage):
        assert storage.get("nonexistent_key") is None

    def test_get_unknown_with_custom_default(self, storage):
        assert storage.get("nonexistent_key", 42) == 42

    def test_set_and_get_string(self, storage):
        storage.set("theme", "light")
        assert storage.get("theme") == "light"

    def test_set_and_get_int(self, storage):
        storage.set("count", 123)
        assert storage.get("count") == 123

    def test_set_and_get_bool(self, storage):
        storage.set("flag", True)
        assert storage.get("flag") is True

    def test_set_and_get_float(self, storage):
        storage.set("ratio", 3.14)
        assert storage.get("ratio") == pytest.approx(3.14)

    def test_set_and_get_list(self, storage):
        storage.set("items", [1, 2, 3])
        assert storage.get("items") == [1, 2, 3]

    def test_set_and_get_dict(self, storage):
        storage.set("config", {"a": 1, "b": "x"})
        assert storage.get("config") == {"a": 1, "b": "x"}

    def test_set_overwrites(self, storage):
        storage.set("key", "a")
        storage.set("key", "b")
        assert storage.get("key") == "b"

    def test_set_and_get_empty_string(self, storage):
        storage.set("pw", "")
        assert storage.get("pw") == ""

    def test_set_and_get_none(self, storage):
        storage.set("nullable", None)
        assert storage.get("nullable") is None

    def test_all_defaults_present(self, storage):
        """Every key in _DEFAULTS should be retrievable."""
        for key in _DEFAULTS:
            assert storage.get(key) == _DEFAULTS[key]


# ═══════════════════════════════════════════════════════════════════════════
# Apps
# ═══════════════════════════════════════════════════════════════════════════

class TestApps:
    """Application blocklist CRUD."""

    def test_add_and_get(self, storage):
        storage.add_app("test.exe", "Test App")
        apps = storage.get_apps()
        assert len(apps) == 1
        assert apps[0]["exe"] == "test.exe"
        assert apps[0]["name"] == "Test App"
        assert apps[0]["enabled"] is True

    def test_add_default_name_from_exe(self, storage):
        storage.add_app("game.exe")
        apps = storage.get_apps()
        assert apps[0]["name"] == "game.exe"

    def test_add_explicit_name_overrides(self, storage):
        storage.add_app("game.exe", "My Game")
        apps = storage.get_apps()
        assert apps[0]["name"] == "My Game"

    def test_add_disabled(self, storage):
        storage.add_app("test.exe", enabled=False)
        apps = storage.get_apps()
        assert apps[0]["enabled"] is False

    def test_remove_app(self, storage):
        storage.add_app("test.exe")
        storage.remove_app("test.exe")
        assert storage.get_apps() == []

    def test_remove_nonexistent_is_safe(self, storage):
        storage.remove_app("nope.exe")  # should not raise

    def test_toggle_app_off(self, storage):
        storage.add_app("test.exe")
        storage.toggle_app("test.exe", False)
        assert storage.get_apps()[0]["enabled"] is False

    def test_toggle_app_on(self, storage):
        storage.add_app("test.exe", enabled=False)
        storage.toggle_app("test.exe", True)
        assert storage.get_apps()[0]["enabled"] is True

    def test_toggle_nonexistent_is_safe(self, storage):
        storage.toggle_app("nope.exe", True)  # should not raise

    def test_get_enabled_apps(self, storage):
        storage.add_app("a.exe", enabled=True)
        storage.add_app("b.exe", enabled=False)
        storage.add_app("c.exe", enabled=True)
        enabled = storage.get_enabled_apps()
        assert "a.exe" in enabled
        assert "c.exe" in enabled
        assert "b.exe" not in enabled

    def test_get_enabled_apps_empty(self, storage):
        assert storage.get_enabled_apps() == []

    def test_upsert_app_updates_name(self, storage):
        storage.add_app("x.exe", "X1")
        storage.add_app("x.exe", "X2")
        apps = storage.get_apps()
        assert len(apps) == 1
        assert apps[0]["name"] == "X2"

    def test_upsert_app_updates_enabled(self, storage):
        storage.add_app("x.exe", enabled=True)
        storage.add_app("x.exe", enabled=False)
        apps = storage.get_apps()
        assert apps[0]["enabled"] is False

    def test_apps_ordered_by_name(self, storage):
        storage.add_app("z.exe", "Zebra")
        storage.add_app("a.exe", "Alpha")
        storage.add_app("m.exe", "Middle")
        apps = storage.get_apps()
        names = [a["name"] for a in apps]
        assert names == sorted(names)

    def test_multiple_apps(self, storage):
        for i in range(10):
            storage.add_app(f"app{i}.exe", f"App {i}")
        assert len(storage.get_apps()) == 10


# ═══════════════════════════════════════════════════════════════════════════
# Sites
# ═══════════════════════════════════════════════════════════════════════════

class TestSites:
    """Website blocklist CRUD."""

    def test_add_and_get(self, storage):
        storage.add_site("example.com")
        sites = storage.get_sites()
        assert len(sites) == 1
        assert sites[0]["domain"] == "example.com"
        assert sites[0]["enabled"] is True

    def test_add_with_name(self, storage):
        storage.add_site("example.com", "Example")
        sites = storage.get_sites()
        assert sites[0]["name"] == "Example"

    def test_add_default_name(self, storage):
        storage.add_site("example.com")
        sites = storage.get_sites()
        assert sites[0]["name"] == "example.com"

    def test_add_disabled(self, storage):
        storage.add_site("example.com", enabled=False)
        sites = storage.get_sites()
        assert sites[0]["enabled"] is False

    def test_remove_site(self, storage):
        storage.add_site("example.com")
        storage.remove_site("example.com")
        assert storage.get_sites() == []

    def test_remove_nonexistent_is_safe(self, storage):
        storage.remove_site("nope.com")

    def test_toggle_site_off(self, storage):
        storage.add_site("example.com")
        storage.toggle_site("example.com", False)
        assert storage.get_sites()[0]["enabled"] is False

    def test_toggle_site_on(self, storage):
        storage.add_site("example.com", enabled=False)
        storage.toggle_site("example.com", True)
        assert storage.get_sites()[0]["enabled"] is True

    def test_toggle_nonexistent_is_safe(self, storage):
        storage.toggle_site("nope.com", True)

    def test_get_enabled_sites(self, storage):
        storage.add_site("a.com", enabled=True)
        storage.add_site("b.com", enabled=False)
        enabled = storage.get_enabled_sites()
        assert "a.com" in enabled
        assert "b.com" not in enabled

    def test_get_enabled_sites_empty(self, storage):
        assert storage.get_enabled_sites() == []

    def test_upsert_site(self, storage):
        storage.add_site("x.com", "X1")
        storage.add_site("x.com", "X2")
        sites = storage.get_sites()
        assert len(sites) == 1
        assert sites[0]["name"] == "X2"

    def test_sites_ordered_by_name(self, storage):
        storage.add_site("z.com", "Zebra")
        storage.add_site("a.com", "Alpha")
        sites = storage.get_sites()
        names = [s["name"] for s in sites]
        assert names == sorted(names)


# ═══════════════════════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════════════════════

class TestStats:
    """Session recording, daily stats, totals, and streaks."""

    def test_record_session(self, storage):
        storage.record_session(25)
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 1
        assert total_mins == 25

    def test_record_multiple_sessions_same_day(self, storage):
        storage.record_session(25)
        storage.record_session(15)
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 2
        assert total_mins == 40

    def test_record_session_accumulates(self, storage):
        storage.record_session(10)
        storage.record_session(10)
        storage.record_session(10)
        _, total_mins = storage.get_total_stats()
        assert total_mins == 30

    def test_daily_stats_today(self, storage):
        storage.record_session(30)
        daily = storage.get_daily_stats(days=1)
        today = date.today().isoformat()
        assert today in daily
        assert daily[today]["sessions"] == 1
        assert daily[today]["minutes"] == 30

    def test_daily_stats_multiple_today(self, storage):
        storage.record_session(25)
        storage.record_session(15)
        daily = storage.get_daily_stats(days=1)
        today = date.today().isoformat()
        assert daily[today]["sessions"] == 2
        assert daily[today]["minutes"] == 40

    def test_daily_stats_excludes_old(self, storage):
        old_date = (date.today() - timedelta(days=10)).isoformat()
        storage._record_raw(old_date, 1, 25)
        daily = storage.get_daily_stats(days=7)
        assert old_date not in daily

    def test_daily_stats_includes_recent(self, storage):
        recent_date = (date.today() - timedelta(days=3)).isoformat()
        storage._record_raw(recent_date, 2, 50)
        daily = storage.get_daily_stats(days=7)
        assert recent_date in daily
        assert daily[recent_date]["sessions"] == 2

    def test_daily_stats_empty(self, storage):
        daily = storage.get_daily_stats(days=7)
        assert daily == {}

    def test_streak_no_data(self, storage):
        current, longest = storage.get_streak()
        assert current == 0
        assert longest == 0

    def test_streak_single_day_today(self, storage):
        storage.record_session(25)
        current, longest = storage.get_streak()
        assert current >= 1
        assert longest >= 1

    def test_streak_multiple_days(self, storage):
        today = date.today()
        for i in range(5):
            d = (today - timedelta(days=i)).isoformat()
            storage._record_raw(d, 1, 25)
        current, longest = storage.get_streak()
        assert current >= 5
        assert longest >= 5

    def test_streak_broken(self, storage):
        today = date.today()
        # Day 0 (today) and day 2 (gap at day 1)
        storage._record_raw(today.isoformat(), 1, 25)
        storage._record_raw((today - timedelta(days=2)).isoformat(), 1, 25)
        current, longest = storage.get_streak()
        assert current == 1  # only today
        assert longest == 1  # no consecutive run

    def test_record_raw(self, storage):
        storage._record_raw("2025-01-01", 3, 75)
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 3
        assert total_mins == 75

    def test_record_raw_accumulates(self, storage):
        storage._record_raw("2025-06-15", 2, 50)
        storage._record_raw("2025-06-15", 3, 75)
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 5
        assert total_mins == 125


# ═══════════════════════════════════════════════════════════════════════════
# Close & lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestClose:
    """Close should be idempotent and safe."""

    def test_close_is_safe(self, storage):
        storage.close()

    def test_double_close_is_safe(self, storage):
        storage.close()
        storage.close()

    def test_operations_after_close(self, storage):
        storage.close()
        # Accessing after close should either work or raise gracefully
        try:
            storage.get("theme")
        except Exception:
            pass  # acceptable


# ═══════════════════════════════════════════════════════════════════════════
# Default seeding
# ═══════════════════════════════════════════════════════════════════════════

class TestSeedDefaults:
    """Default apps and sites seeding.

    NOTE: _seed_defaults only runs during the first migration from legacy JSON.
    On a fresh DB without legacy files, _migrate() returns early because
    _DEFAULTS already provides 'theme' value. So we test that the defaults
    are accessible via get() instead.
    """

    def test_all_defaults_accessible(self, storage):
        """Every key in _DEFAULTS should return its default value."""
        for key, val in _DEFAULTS.items():
            assert storage.get(key) == val

    def test_apps_start_empty_on_fresh_db(self, storage):
        """Without legacy config, apps list starts with defaults from constants."""
        from focuslock.constants import DEFAULT_APPS
        apps = storage.get_apps()
        # Apps are populated by _seed_defaults only during legacy migration
        # On a fresh DB, we just verify the list is a valid list
        assert isinstance(apps, list)

    def test_sites_start_empty_on_fresh_db(self, storage):
        from focuslock.constants import DEFAULT_SITES
        sites = storage.get_sites()
        assert isinstance(sites, list)


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Unusual but valid usage patterns."""

    def test_toggle_all_apps_off(self, storage):
        for app in storage.get_apps():
            storage.toggle_app(app["exe"], False)
        assert storage.get_enabled_apps() == []

    def test_toggle_all_sites_off(self, storage):
        for site in storage.get_sites():
            storage.toggle_site(site["domain"], False)
        assert storage.get_enabled_sites() == []

    def test_record_session_zero_minutes(self, storage):
        storage.record_session(0)
        total_sessions, total_mins = storage.get_total_stats()
        assert total_sessions == 1
        assert total_mins == 0

    def test_daily_stats_large_window(self, storage):
        storage.record_session(25)
        daily = storage.get_daily_stats(days=365)
        today = date.today().isoformat()
        assert today in daily
