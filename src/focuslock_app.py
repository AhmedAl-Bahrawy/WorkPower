"""PySide6 Application Entry Point for FocusLock."""

import sys
import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QStackedWidget, QSystemTrayIcon, QMenu, QMessageBox)
from PySide6.QtCore import Qt, QObject, Signal, Slot, QTimer
from PySide6.QtGui import QIcon, QAction

from focuslock.config import load_config, save_config, load_stats, save_stats
from focuslock.constants import APP_NAME, VERSION, PRESETS, THEMES
from focuslock.core import PomodoroTimer
from focuslock.blocking import AppBlocker, block_sites, unblock_sites
from focuslock.platform.startup import set_startup, startup_is_on
from focuslock.platform.notifications import notify
from focuslock.ui.widgets import (Theme, CircularTimer, BarChart, ToggleButton, 
                                  button, label, divider, make_card, ScrollableFrame, stat_card, BlocklistItemCard)
from focuslock.ui.dialogs import AppPickerDialog, SitePickerDialog

class Config:
    def __init__(self):
        self._cfg = load_config()
        self._stats = load_stats()
        
    def get(self, key, default=None):
        if key == "stats":
            return self._stats.get("sessions_by_date", {})
        if key == "app_meta":
            return self._cfg.get("blocklist_meta", {})
        if key == "site_meta":
            return self._cfg.get("website_blocklist_meta", {})
        if key == "sites":
            return self._cfg.get("website_blocklist", [])
        return self._cfg.get(key, default)
        
    def set(self, key, value):
        if key == "stats":
            self._stats["sessions_by_date"] = value
            save_stats(self._stats)
        elif key == "app_meta":
            self._cfg["blocklist_meta"] = value
            save_config(self._cfg)
        elif key == "site_meta":
            self._cfg["website_blocklist_meta"] = value
            save_config(self._cfg)
        elif key == "sites":
            self._cfg["website_blocklist"] = value
            save_config(self._cfg)
        else:
            self._cfg[key] = value
            save_config(self._cfg)


class WebsiteBlocker:
    def __init__(self):
        self.sites = []
    
    def sync(self, sites):
        self.sites = sites
        
    def start(self):
        if self.sites:
            block_sites(self.sites)
            
    def stop(self):
        unblock_sites(self.sites)


class TimerSignals(QObject):
    """Signals to safely route timer thread callbacks to the Qt main thread."""
    tick = Signal(int, str)
    phase = Signal(str, int)

class FocusLockApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self.theme = Theme(self.cfg.get("theme", "dark"), THEMES[self.cfg.get("theme", "dark")])
        self.preset = self.cfg.get("preset", "Classic (25/5)")
        self.timer_sig = TimerSignals()
        
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.setMinimumSize(900, 650)
        self.theme.apply_to_app(self)
        
        # Init blockers
        self.app_blocker = AppBlocker(self.cfg.get("blocklist", []))
        
        self.site_blocker = WebsiteBlocker()
        self.site_blocker.sync(self.cfg.get("sites", []))
        
        # Init Timer
        self._init_timer_from_preset()
        
        # UI Setup
        self._build_ui()
        self._setup_tray()
        
        # Signals connect
        self.timer_sig.tick.connect(self._on_tick_ui)
        self.timer_sig.phase.connect(self._on_phase_ui)
        
        self.update_stats_ui()
        self.show()

    def _init_timer_from_preset(self):
        p = PRESETS.get(self.preset, PRESETS["Classic (25/5)"])
        # Stop existing timer if running
        if hasattr(self, 'timer') and self.timer:
            self.timer.pause()
            
        self.timer = PomodoroTimer(
            p[0], p[1],
            on_tick=lambda r, ph: self.timer_sig.tick.emit(r, ph),
            on_phase=lambda ph, cyc: self.timer_sig.phase.emit(ph, cyc)
        )
        
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(12)
        
        title_lbl = label(APP_NAME, "title", self.theme)
        title_lbl.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {self.theme.c['text']};")
        sidebar_layout.addWidget(title_lbl)
        sidebar_layout.addSpacing(24)
        
        self.nav_btns = {}
        pages = ["Session", "Applications", "Websites", "Stats", "Settings"]
        for p in pages:
            btn = button(p, lambda checked=False, page=p: self._switch_page(page), variant="ghost", theme=self.theme)
            btn.setStyleSheet(btn.styleSheet() + f" text-align: left; font-size: 15px; padding: 12px 16px;")
            self.nav_btns[p] = btn
            sidebar_layout.addWidget(btn)
            
        sidebar_layout.addStretch()
        
        # Theme toggle at bottom of sidebar
        theme_btn = button(f"Theme: {self.theme.name}", self._toggle_theme, variant="secondary", theme=self.theme)
        sidebar_layout.addWidget(theme_btn)
        
        main_layout.addWidget(self.sidebar)
        
        # Stacked Widget for pages
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)
        
        self.pages = {
            "Session": self._build_session_page(),
            "Applications": self._build_apps_page(),
            "Websites": self._build_sites_page(),
            "Stats": self._build_stats_page(),
            "Settings": self._build_settings_page()
        }
        
        for p in self.pages.values():
            self.stack.addWidget(p)
            
        self._switch_page("Session")
        
    def _switch_page(self, page_name):
        c = self.theme.c
        for name, btn in self.nav_btns.items():
            if name == page_name:
                btn.setStyleSheet(f"""
                    QPushButton {{ background-color: {c['card']}; color: {c['accent']}; border: none; border-radius: 8px; padding: 12px 16px; font-weight: bold; text-align: left; font-size: 15px; }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {c['subtext']}; border: none; border-radius: 8px; padding: 12px 16px; font-weight: bold; text-align: left; font-size: 15px; }}
                    QPushButton:hover {{ background-color: {c['card']}; color: {c['text']}; }}
                """)
        self.stack.setCurrentWidget(self.pages[page_name])

    # ─────────────────────────────────────────────────────────────────────────
    # Pages
    # ─────────────────────────────────────────────────────────────────────────
    def _build_session_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Left side: Timer
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setAlignment(Qt.AlignCenter)
        
        self.phase_lbl = label("FOCUS TIME", "accent", self.theme)
        self.phase_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {self.theme.c['accent']}; letter-spacing: 2px;")
        self.phase_lbl.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.phase_lbl)
        
        self.circular_timer = CircularTimer(self.theme, size=300)
        left_layout.addWidget(self.circular_timer, alignment=Qt.AlignCenter)
        
        self.time_lbl = label("00:00", "title", self.theme)
        self.time_lbl.setStyleSheet(f"font-size: 48px; font-family: 'Segoe UI Semibold'; color: {self.theme.c['text']};")
        self.time_lbl.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.time_lbl, alignment=Qt.AlignCenter)
        left_layout.addSpacing(24)
        
        controls = QHBoxLayout()
        self.start_btn = button("Start Session", self._toggle_timer, variant="primary", theme=self.theme)
        self.start_btn.setMinimumWidth(160)
        self.reset_btn = button("Reset", self._reset_timer, variant="secondary", theme=self.theme)
        controls.addStretch()
        controls.addWidget(self.start_btn)
        controls.addWidget(self.reset_btn)
        controls.addStretch()
        left_layout.addLayout(controls)
        
        layout.addWidget(left, 1)
        
        # Right side: Presets
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setAlignment(Qt.AlignTop)
        
        right_layout.addWidget(label("Presets", "heading", self.theme))
        right_layout.addSpacing(16)
        
        self.preset_btns = []
        for name, p in PRESETS.items():
            btn = button(f"{name}\n{p[0]}m focus • {p[1]}m break", 
                         lambda checked=False, n=name: self._set_preset(n), 
                         variant="secondary", theme=self.theme)
            btn.setStyleSheet(btn.styleSheet() + " text-align: left; padding: 16px;")
            right_layout.addWidget(btn)
            self.preset_btns.append((name, btn))
            
        self._update_preset_btns()
        layout.addWidget(right, 1)
        
        # Initial Timer Update
        self._on_tick_ui(self.timer.remaining, self.timer.phase)
        
        return page

    def _build_apps_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        header = QHBoxLayout()
        header.addWidget(label("Blocked Applications", "title", self.theme))
        header.addStretch()
        
        self.app_count_lbl = label("0 apps blocked", "subtext", self.theme)
        header.addWidget(self.app_count_lbl)
        
        add_btn = button("+ Add App", self._open_app_picker, variant="primary", theme=self.theme)
        header.addWidget(add_btn)
        layout.addLayout(header)
        layout.addSpacing(16)
        
        self.app_scroll = ScrollableFrame(self.theme)
        layout.addWidget(self.app_scroll)
        
        self._rebuild_app_cards()
        return page

    def _build_sites_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        header = QHBoxLayout()
        header.addWidget(label("Blocked Websites", "title", self.theme))
        header.addStretch()
        
        self.site_count_lbl = label("0 sites blocked", "subtext", self.theme)
        header.addWidget(self.site_count_lbl)
        
        add_btn = button("+ Add Website", self._open_site_picker, variant="primary", theme=self.theme)
        header.addWidget(add_btn)
        layout.addLayout(header)
        layout.addSpacing(16)
        
        self.site_scroll = ScrollableFrame(self.theme)
        layout.addWidget(self.site_scroll)
        
        self._rebuild_site_cards()
        return page

    def _build_stats_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        layout.addWidget(label("Statistics", "title", self.theme))
        layout.addSpacing(20)
        
        grid = QHBoxLayout()
        self.stat_sessions = stat_card(self.theme, "🍅", "Total Sessions", "0")
        self.stat_hours = stat_card(self.theme, "⏳", "Focus Time", "0h 0m", color=self.theme.c["timer_work"])
        self.stat_streak = stat_card(self.theme, "🔥", "Current Streak", "0 days", color=self.theme.c["warn"])
        
        grid.addWidget(self.stat_sessions)
        grid.addWidget(self.stat_hours)
        grid.addWidget(self.stat_streak)
        layout.addLayout(grid)
        
        layout.addSpacing(40)
        layout.addWidget(label("Last 7 Days", "heading", self.theme))
        
        self.chart = BarChart(self.theme, height=200)
        layout.addWidget(self.chart)
        layout.addStretch()
        
        return page

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        
        layout.addWidget(label("Settings", "title", self.theme))
        layout.addSpacing(24)
        
        sys_frame = make_card(self.theme)
        sys_layout = QVBoxLayout(sys_frame)
        sys_layout.setContentsMargins(20, 20, 20, 20)
        
        row = QHBoxLayout()
        row.addWidget(label("Start with Windows", "text", self.theme))
        row.addStretch()
        self.startup_tgl = ToggleButton(self.theme, initial_state=startup_is_on())
        self.startup_tgl.toggled.connect(self._toggle_startup)
        row.addWidget(self.startup_tgl)
        
        sys_layout.addLayout(row)
        layout.addWidget(sys_frame)
        layout.addStretch()
        return page

    # ─────────────────────────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_timer(self):
        if self.timer._on:
            self.timer.pause()
            self.app_blocker.stop()
            self.site_blocker.stop()
            self.start_btn.setText("Resume Session")
        else:
            self.timer.start()
            self.app_blocker.start()
            self.site_blocker.start()
            self.start_btn.setText("Pause Session")
            
    def _reset_timer(self):
        self.timer.reset()
        self.app_blocker.stop()
        self.site_blocker.stop()
        self.start_btn.setText("Start Session")
        self._on_tick_ui(self.timer.remaining, self.timer.phase)

    def _on_tick_ui(self, rem, phase):
        mins, secs = divmod(rem, 60)
        self.time_lbl.setText(f"{mins:02d}:{secs:02d}")
        
        total = self.timer.work_sec if phase == "work" else self.timer.break_sec
        self.circular_timer.set_value(rem, total, phase)
        
        if hasattr(self, 'tray') and self.tray:
            self.tray.setToolTip(f"{APP_NAME} - {mins:02d}:{secs:02d} ({phase})")

    def _on_phase_ui(self, phase, cycles):
        notify(APP_NAME, f"Phase complete! Time for {phase}.")
        p_text = "FOCUS TIME" if phase == "work" else "BREAK TIME"
        color = self.theme.c["accent"] if phase == "work" else self.theme.c["success"]
        self.phase_lbl.setText(p_text)
        self.phase_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color}; letter-spacing: 2px;")
        
        if phase == "break":
            self.app_blocker.stop()
            self.site_blocker.stop()
            self._record_session()
        else:
            self.app_blocker.start()
            self.site_blocker.start()

    def _set_preset(self, name):
        self.preset = name
        self.cfg.set("preset", name)
        self._init_timer_from_preset()
        self._update_preset_btns()
        self._reset_timer()

    def _update_preset_btns(self):
        c = self.theme.c
        for name, btn in self.preset_btns:
            if name == self.preset:
                btn.setStyleSheet(f"QPushButton {{ background-color: {c['accent']}; color: white; border: none; border-radius: 8px; text-align: left; padding: 16px; font-weight: bold; }}")
            else:
                btn.setStyleSheet(f"QPushButton {{ background-color: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px; text-align: left; padding: 16px; font-weight: bold; }} QPushButton:hover {{ background-color: {c['card_hover']}; }}")

    def _toggle_theme(self):
        new_theme = "Light" if self.theme.name == "Dark" else "Dark"
        self.cfg.set("theme", new_theme)
        self.theme = Theme(new_theme, THEMES[new_theme])
        
        self.theme.apply_to_app(self)
        
        # We need to recreate the UI to fully apply the theme easily in this architecture
        # To avoid complexity in this rewrite, we will notify the user to restart
        QMessageBox.information(self, "Theme Changed", "Theme changed successfully. Please restart the app for it to take full effect.")

    def _toggle_startup(self, state):
        set_startup(state)

    # ─────────────────────────────────────────────────────────────────────────
    # Blocklists
    # ─────────────────────────────────────────────────────────────────────────
    def _open_app_picker(self):
        dlg = AppPickerDialog(self, self.theme, self._add_app)
        dlg.exec()

    def _add_app(self, name, exe):
        meta = self.cfg.get("app_meta", {})
        meta[exe] = {"name": name, "enabled": True}
        self.cfg.set("app_meta", meta)
        
        bl = self.cfg.get("blocklist", [])
        if exe not in bl:
            bl.append(exe)
            self.cfg.set("blocklist", bl)
            
        self.app_blocker.update_blocklist(bl)
        self._rebuild_app_cards()

    def _remove_app(self, exe):
        meta = self.cfg.get("app_meta", {})
        if exe in meta:
            del meta[exe]
            self.cfg.set("app_meta", meta)
            
        bl = self.cfg.get("blocklist", [])
        if exe in bl:
            bl.remove(exe)
            self.cfg.set("blocklist", bl)
            
        self.app_blocker.update_blocklist(bl)
        self._rebuild_app_cards()

    def _toggle_app(self, exe, state):
        meta = self.cfg.get("app_meta", {})
        if exe in meta:
            meta[exe]["enabled"] = state
            self.cfg.set("app_meta", meta)
            
        bl = self.cfg.get("blocklist", [])
        if state and exe not in bl:
            bl.append(exe)
        elif not state and exe in bl:
            bl.remove(exe)
            
        self.cfg.set("blocklist", bl)
        self.app_blocker.update_blocklist(bl)

    def _rebuild_app_cards(self):
        layout = self.app_scroll.inner_layout
        for i in reversed(range(layout.count())): 
            w = layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
                
        meta = self.cfg.get("app_meta", {})
        bl = self.cfg.get("blocklist", [])
        
        # Ensure blocklist items have meta
        for exe in bl:
            if exe not in meta:
                meta[exe] = {"name": exe, "enabled": True}
                
        count = 0
        for exe, data in meta.items():
            card = BlocklistItemCard(
                self.theme, data["name"], exe, "app", 
                data.get("enabled", True), 
                self._remove_app, self._toggle_app
            )
            layout.addWidget(card)
            count += 1
            
        self.app_count_lbl.setText(f"{count} apps blocked")

    def _open_site_picker(self):
        dlg = SitePickerDialog(self, self.theme, self._add_site)
        dlg.exec()

    def _add_site(self, name, domain):
        meta = self.cfg.get("site_meta", {})
        meta[domain] = {"name": name, "enabled": True}
        self.cfg.set("site_meta", meta)
        
        sites = self.cfg.get("sites", [])
        if domain not in sites:
            sites.append(domain)
            self.cfg.set("sites", sites)
            
        self.site_blocker.sync(sites)
        self._rebuild_site_cards()

    def _remove_site(self, domain):
        meta = self.cfg.get("site_meta", {})
        if domain in meta:
            del meta[domain]
            self.cfg.set("site_meta", meta)
            
        sites = self.cfg.get("sites", [])
        if domain in sites:
            sites.remove(domain)
            self.cfg.set("sites", sites)
            
        self.site_blocker.sync(sites)
        self._rebuild_site_cards()

    def _toggle_site(self, domain, state):
        meta = self.cfg.get("site_meta", {})
        if domain in meta:
            meta[domain]["enabled"] = state
            self.cfg.set("site_meta", meta)
            
        sites = self.cfg.get("sites", [])
        if state and domain not in sites:
            sites.append(domain)
        elif not state and domain in sites:
            sites.remove(domain)
            
        self.cfg.set("sites", sites)
        self.site_blocker.sync(sites)

    def _rebuild_site_cards(self):
        layout = self.site_scroll.inner_layout
        for i in reversed(range(layout.count())): 
            w = layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
                
        meta = self.cfg.get("site_meta", {})
        sites = self.cfg.get("sites", [])
        
        # Ensure blocklist items have meta
        for domain in sites:
            if domain not in meta:
                meta[domain] = {"name": domain, "enabled": True}
                
        count = 0
        for domain, data in meta.items():
            card = BlocklistItemCard(
                self.theme, data["name"], domain, "site", 
                data.get("enabled", True), 
                self._remove_site, self._toggle_site
            )
            layout.addWidget(card)
            count += 1
            
        self.site_count_lbl.setText(f"{count} sites blocked")

    # ─────────────────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────────────────
    def _record_session(self):
        stats = self.cfg.get("stats", {})
        today = datetime.date.today().isoformat()
        
        day_stats = stats.get(today, {"sessions": 0, "minutes": 0})
        day_stats["sessions"] += 1
        day_stats["minutes"] += self.timer.work_sec // 60
        stats[today] = day_stats
        
        self.cfg.set("stats", stats)
        self.update_stats_ui()

    def update_stats_ui(self):
        stats = self.cfg.get("stats", {})
        
        # Ensure we only process dicts (dates) in case of format differences
        valid_stats = {k: v for k, v in stats.items() if isinstance(v, dict) and "sessions" in v}
        
        total_sessions = sum(d.get("sessions", 0) for d in valid_stats.values())
        total_mins = sum(d.get("minutes", 0) for d in valid_stats.values())
        
        # Streak logic
        dates = sorted([datetime.date.fromisoformat(d) for d in valid_stats.keys() if '-' in d])
        streak = 0
        if dates:
            curr = datetime.date.today()
            if dates[-1] < curr - datetime.timedelta(days=1):
                streak = 0
            else:
                for d in reversed(dates):
                    if d == curr:
                        streak += 1
                        curr -= datetime.timedelta(days=1)
                    else:
                        break
                        
        self.stat_sessions.findChild(QLabel, "").setText(str(total_sessions)) # Hacky way since we didn't store refs
        
        hours, mins = divmod(total_mins, 60)
        self.stat_hours.layout().itemAt(1).widget().setText(f"{hours}h {mins}m")
        self.stat_sessions.layout().itemAt(1).widget().setText(f"{total_sessions}")
        self.stat_streak.layout().itemAt(1).widget().setText(f"{streak} days")
        
        # 7-day chart
        today = datetime.date.today()
        labels = []
        data = []
        for i in range(6, -1, -1):
            d = today - datetime.timedelta(days=i)
            labels.append(d.strftime("%a"))
            iso = d.isoformat()
            data.append(valid_stats.get(iso, {}).get("minutes", 0))
            
        self.chart.set_data(data, labels)

    # ─────────────────────────────────────────────────────────────────────────
    # System Tray & Exit
    # ─────────────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        
        # Create a blank transparent icon as placeholder if we don't have one
        from PySide6.QtWidgets import QStyle
        self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        
        self.tray_menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.showNormal)
        self.tray_menu.addAction(show_action)
        
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self._quit)
        self.tray_menu.addAction(quit_action)
        
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        # Minimize to tray
        event.ignore()
        self.hide()
        notify(APP_NAME, "App minimized to system tray.")

    def _quit(self):
        self.timer.pause()
        self.app_blocker.stop()
        self.site_blocker.stop()
        QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FocusLockApp()
    sys.exit(app.exec())
