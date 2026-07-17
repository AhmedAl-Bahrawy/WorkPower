"""Blocklist service — app/site CRUD + blocker synchronization."""


class BlocklistService:
    """Manages the blocked-app and blocked-site lists and syncs to OS-level blockers."""

    def __init__(self, storage, app_blocker, site_blocker):
        self._storage = storage
        self._app_blocker = app_blocker
        self._site_blocker = site_blocker

    # ── Applications ────────────────────────────────────────────────────
    def add_app(self, exe, name=None, enabled=True):
        self._storage.add_app(exe, name or exe, enabled)
        self._sync_apps()

    def remove_app(self, exe):
        self._storage.remove_app(exe)
        self._sync_apps()

    def toggle_app(self, exe, enabled):
        self._storage.toggle_app(exe, enabled)
        self._sync_apps()

    def get_apps(self):
        return self._storage.get_apps()

    def _sync_apps(self):
        self._app_blocker.set_enabled_apps(self._storage.get_enabled_apps())

    # ── Websites ────────────────────────────────────────────────────────
    def add_site(self, domain, name=None, enabled=True):
        self._storage.add_site(domain, name or domain, enabled)
        self._sync_sites()

    def remove_site(self, domain):
        self._storage.remove_site(domain)
        self._sync_sites()

    def toggle_site(self, domain, enabled):
        self._storage.toggle_site(domain, enabled)
        self._sync_sites()

    def get_sites(self):
        return self._storage.get_sites()

    def _sync_sites(self):
        self._site_blocker.sync(self._storage.get_enabled_sites())

    # ── Blocker lifecycle ───────────────────────────────────────────────
    def start_blockers(self, phase, block_websites=True):
        """Start the appropriate blockers for the given phase."""
        if phase == "work":
            self._app_blocker.start()
            if block_websites:
                self._site_blocker.start()

    def stop_blockers(self):
        """Stop all blockers."""
        self._app_blocker.stop()
        self._site_blocker.stop()

    def stop_app_blocker(self):
        self._app_blocker.stop()

    def stop_site_blocker(self):
        self._site_blocker.stop()

    def has_site_permission_error(self):
        return self._site_blocker.last_error == "permission"
