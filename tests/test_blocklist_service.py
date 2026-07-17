"""Tests for focuslock.services.blocklist_service — BlocklistService.

Covers: app/site CRUD with blocker sync, start/stop lifecycle,
permission error detection, and edge cases.
"""

import pytest

from focuslock.blocking.app_blocker import AppBlocker
from focuslock.config import Storage
from focuslock.services.blocklist_service import BlocklistService


# ── stubs ─────────────────────────────────────────────────────────────────

class FakeWebsiteBlocker:
    """Stub for the in-app WebsiteBlocker (avoids PySide6 import)."""

    def __init__(self):
        self.synced_sites = []
        self.start_called = 0
        self.stop_called = 0
        self.last_error = None

    def sync(self, sites):
        self.synced_sites = list(sites)

    def start(self):
        self.start_called += 1

    def stop(self):
        self.stop_called += 1


# ── fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def storage(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("focuslock.config.DB_FILE", db_path)
    monkeypatch.setattr("focuslock.config.DATA_DIR", tmp_path)
    s = Storage()
    yield s
    s.close()


@pytest.fixture
def app_blocker():
    return AppBlocker()


@pytest.fixture
def site_blocker():
    return FakeWebsiteBlocker()


@pytest.fixture
def svc(storage, app_blocker, site_blocker):
    return BlocklistService(storage, app_blocker, site_blocker)


# ═══════════════════════════════════════════════════════════════════════════
# Application CRUD
# ═══════════════════════════════════════════════════════════════════════════

class TestAppCRUD:

    def test_add_app(self, svc):
        svc.add_app("chrome.exe", "Chrome")
        apps = svc.get_apps()
        assert len(apps) == 1
        assert apps[0]["exe"] == "chrome.exe"
        assert apps[0]["name"] == "Chrome"

    def test_add_app_default_name(self, svc):
        svc.add_app("firefox.exe")
        apps = svc.get_apps()
        assert apps[0]["name"] == "firefox.exe"

    def test_remove_app(self, svc):
        svc.add_app("chrome.exe")
        svc.remove_app("chrome.exe")
        assert svc.get_apps() == []

    def test_remove_app_nonexistent(self, svc):
        svc.remove_app("nonexistent.exe")

    def test_toggle_app(self, svc):
        svc.add_app("chrome.exe", enabled=True)
        svc.toggle_app("chrome.exe", False)
        apps = svc.get_apps()
        assert apps[0]["enabled"] is False

    def test_get_apps_returns_list(self, svc):
        assert isinstance(svc.get_apps(), list)

    def test_add_multiple_apps(self, svc):
        svc.add_app("chrome.exe", "Chrome")
        svc.add_app("firefox.exe", "Firefox")
        svc.add_app("discord.exe", "Discord")
        assert len(svc.get_apps()) == 3


# ═══════════════════════════════════════════════════════════════════════════
# Website CRUD
# ═══════════════════════════════════════════════════════════════════════════

class TestSiteCRUD:

    def test_add_site(self, svc):
        svc.add_site("example.com", "Example")
        sites = svc.get_sites()
        assert len(sites) == 1
        assert sites[0]["domain"] == "example.com"

    def test_add_site_default_name(self, svc):
        svc.add_site("example.com")
        sites = svc.get_sites()
        assert sites[0]["name"] == "example.com"

    def test_remove_site(self, svc):
        svc.add_site("example.com")
        svc.remove_site("example.com")
        assert svc.get_sites() == []

    def test_remove_site_nonexistent(self, svc):
        svc.remove_site("nonexistent.com")

    def test_toggle_site(self, svc):
        svc.add_site("example.com", enabled=True)
        svc.toggle_site("example.com", False)
        sites = svc.get_sites()
        assert sites[0]["enabled"] is False

    def test_get_sites_returns_list(self, svc):
        assert isinstance(svc.get_sites(), list)


# ═══════════════════════════════════════════════════════════════════════════
# Blocker sync
# ═══════════════════════════════════════════════════════════════════════════

class TestBlockerSync:

    def test_add_app_syncs_blocker(self, svc, app_blocker):
        svc.add_app("chrome.exe", enabled=True)
        assert "chrome.exe" in app_blocker._enabled

    def test_remove_app_syncs_blocker(self, svc, app_blocker):
        svc.add_app("chrome.exe")
        svc.remove_app("chrome.exe")
        assert "chrome.exe" not in app_blocker._enabled

    def test_toggle_app_syncs_blocker(self, svc, app_blocker):
        svc.add_app("chrome.exe", enabled=True)
        svc.toggle_app("chrome.exe", False)
        assert "chrome.exe" not in app_blocker._enabled

    def test_add_site_syncs_blocker(self, svc, site_blocker):
        svc.add_site("example.com")
        assert "example.com" in site_blocker.synced_sites

    def test_remove_site_syncs_blocker(self, svc, site_blocker):
        svc.add_site("example.com")
        svc.remove_site("example.com")
        assert "example.com" not in site_blocker.synced_sites

    def test_disabled_app_not_synced_to_blocker(self, svc, app_blocker):
        svc.add_app("chrome.exe", enabled=False)
        assert "chrome.exe" not in app_blocker._enabled


# ═══════════════════════════════════════════════════════════════════════════
# Blocker lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestBlockerLifecycle:

    def test_start_work_starts_app_blocker(self, svc, app_blocker):
        svc.start_blockers("work")
        assert app_blocker._running is True

    def test_start_work_starts_site_blocker(self, svc, site_blocker):
        svc.start_blockers("work")
        assert site_blocker.start_called == 1

    def test_start_break_does_not_start_blockers(self, svc, app_blocker, site_blocker):
        svc.start_blockers("break")
        assert app_blocker._running is False
        assert site_blocker.start_called == 0

    def test_stop_stops_both_blockers(self, svc, app_blocker, site_blocker):
        svc.start_blockers("work")
        svc.stop_blockers()
        assert app_blocker._running is False
        assert site_blocker.stop_called == 1

    def test_start_with_block_websites_false(self, svc, site_blocker):
        svc.start_blockers("work", block_websites=False)
        assert site_blocker.start_called == 0

    def test_stop_app_blocker_only(self, svc, app_blocker):
        svc.start_blockers("work")
        svc.stop_app_blocker()
        assert app_blocker._running is False

    def test_stop_site_blocker_only(self, svc, site_blocker):
        svc.start_blockers("work")
        svc.stop_site_blocker()
        assert site_blocker.stop_called == 1

    def test_has_site_permission_error_false_by_default(self, svc, site_blocker):
        assert svc.has_site_permission_error() is False

    def test_has_site_permission_error_true(self, svc, site_blocker):
        site_blocker.last_error = "permission"
        assert svc.has_site_permission_error() is True
