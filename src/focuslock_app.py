"""PySide6 Application Entry Point for FocusLock."""

import datetime
import logging
import logging.handlers
import os
import sys
import time
import threading
import winsound

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QSystemTrayIcon, QMenu,
    QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDialog, QPushButton, QFormLayout, QSpinBox, QScrollArea, QFrame,
    QTabWidget,
)

from focuslock.platform import subprocess_patch  # noqa: F401
from focuslock.config import Storage
from focuslock.constants import APP_NAME, VERSION, PRESETS, THEMES
from focuslock.core import PomodoroTimer, hash_password, verify_password
from focuslock.blocking import AppBlocker, block_sites, unblock_sites
from focuslock.platform.startup import set_startup, startup_is_on
from focuslock.platform.notifications import notify
from focuslock.ui.widgets import (
    Theme, CircularTimer, BarChart, ToggleButton,
    button, label, divider, make_card, ScrollableFrame,
    stat_card, BlocklistItemCard,
)
from focuslock.ui.dialogs import AppPickerDialog, SitePickerDialog


# ─────────────────────────────────────────────────────────────────────────────
# Password dialog
# ─────────────────────────────────────────────────────────────────────────────
class PasswordDialog(QDialog):
    def __init__(self, parent, theme, title="Enter Password", prompt="Password:"):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle(title)
        self.setFixedSize(400, 200)
        self._ok = False

        c = theme.c
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg']}; color: {c['text']}; }}
            QLineEdit {{ background-color: {c['input']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 6px;
                padding: 8px 12px; font-size: 14px; }}
            QLineEdit:focus {{ border: 1px solid {c['accent']}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        layout.addWidget(label(prompt, "text", theme))

        pw_row = QHBoxLayout()
        pw_row.setSpacing(8)
        self.pw_input = QLineEdit()
        self.pw_input.setEchoMode(QLineEdit.Password)
        self.pw_input.setPlaceholderText("Enter password...")
        self.pw_input.returnPressed.connect(self._submit)
        pw_row.addWidget(self.pw_input)

        self.toggle_btn = button("\U0001F441", variant="ghost", theme=theme)
        self.toggle_btn.setFixedWidth(36)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._toggle_visibility)
        pw_row.addWidget(self.toggle_btn)
        layout.addLayout(pw_row)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet(f"color: {c['danger']}; font-size: 12px;")
        self.error_lbl.hide()
        layout.addWidget(self.error_lbl)

        row = QHBoxLayout()
        row.addStretch()
        cancel = button("Cancel", self.reject, variant="ghost", theme=theme)
        row.addWidget(cancel)
        ok = button("OK", self._submit, variant="primary", theme=theme)
        row.addWidget(ok)
        layout.addLayout(row)

    def _toggle_visibility(self, checked):
        mode = QLineEdit.Normal if checked else QLineEdit.Password
        self.pw_input.setEchoMode(mode)

    def show_error(self, text):
        self.error_lbl.setText(text)
        self.error_lbl.show()

    def _submit(self):
        self._ok = True
        self.accept()

    def password(self):
        return self.pw_input.text()

    def was_confirmed(self):
        return self._ok


class SetPasswordDialog(QDialog):
    """Dialog to set or change a password (session or parent)."""
    def __init__(self, parent, theme, current_hash="", is_parent=False, skip_current=False):
        super().__init__(parent)
        self.theme = theme
        self.is_parent = is_parent
        self._current_hash = current_hash
        self._verified_current = skip_current
        label_prefix = "Parent " if is_parent else ""
        self.setWindowTitle(f"Set {label_prefix}Password")
        self.setMinimumSize(440, 320)
        self._new_hash = ""

        c = theme.c
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c['bg']}; color: {c['text']}; }}
            QLineEdit {{ background-color: {c['input']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 6px;
                padding: 8px 12px; font-size: 14px; }}
            QLineEdit:focus {{ border: 1px solid {c['accent']}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        self.has_current = bool(current_hash) and not skip_current
        if self.has_current:
            layout.addWidget(label("Current password:", "text", theme))
            cur_row = QHBoxLayout()
            cur_row.setSpacing(8)
            self.current_input = QLineEdit()
            self.current_input.setEchoMode(QLineEdit.Password)
            self.current_input.setPlaceholderText("Enter current password...")
            cur_row.addWidget(self.current_input)
            self.cur_toggle = button("\U0001F441", variant="ghost", theme=theme)
            self.cur_toggle.setFixedWidth(36)
            self.cur_toggle.setCheckable(True)
            self.cur_toggle.toggled.connect(
                lambda checked: self.current_input.setEchoMode(
                    QLineEdit.Normal if checked else QLineEdit.Password
                )
            )
            cur_row.addWidget(self.cur_toggle)
            layout.addLayout(cur_row)
        else:
            self.current_input = None

        layout.addSpacing(4)
        layout.addWidget(label("New password:", "text", theme))
        new_row = QHBoxLayout()
        new_row.setSpacing(8)
        self.new_input = QLineEdit()
        self.new_input.setEchoMode(QLineEdit.Password)
        self.new_input.setPlaceholderText("Enter new password...")
        new_row.addWidget(self.new_input)
        self.new_toggle = button("\U0001F441", variant="ghost", theme=theme)
        self.new_toggle.setFixedWidth(36)
        self.new_toggle.setCheckable(True)
        self.new_toggle.toggled.connect(
            lambda checked: self.new_input.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        new_row.addWidget(self.new_toggle)
        layout.addLayout(new_row)

        layout.addWidget(label("Confirm password:", "text", theme))
        conf_row = QHBoxLayout()
        conf_row.setSpacing(8)
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText("Re-enter new password...")
        self.confirm_input.returnPressed.connect(self._submit)
        conf_row.addWidget(self.confirm_input)
        self.conf_toggle = button("\U0001F441", variant="ghost", theme=theme)
        self.conf_toggle.setFixedWidth(36)
        self.conf_toggle.setCheckable(True)
        self.conf_toggle.toggled.connect(
            lambda checked: self.confirm_input.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        conf_row.addWidget(self.conf_toggle)
        layout.addLayout(conf_row)

        min_len = 8 if is_parent else 4
        hint = f"Min {min_len} characters"
        hint_lbl = label(hint, "subtext", theme)
        hint_lbl.setStyleSheet(f"color: {c['muted']}; font-size: 11px;")
        layout.addWidget(hint_lbl)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet(f"color: {c['danger']}; font-size: 12px;")
        self.error_lbl.hide()
        layout.addWidget(self.error_lbl)

        layout.addStretch()

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Cancel", self.reject, variant="ghost", theme=theme))
        row.addWidget(button("Save", self._submit, variant="primary", theme=theme))
        layout.addLayout(row)

    def show_error(self, text):
        self.error_lbl.setText(text)
        self.error_lbl.show()

    def _submit(self):
        self.error_lbl.hide()

        current_pw = ""
        if self.has_current:
            current_pw = self.current_input.text()
            if not current_pw:
                self.show_error("Enter your current password.")
                return
            ok, _ = verify_password(current_pw, self._current_hash)
            if not ok:
                self.show_error("Current password is incorrect.")
                return

        new = self.new_input.text()
        confirm = self.confirm_input.text()

        if not new:
            self.show_error("Password cannot be empty.")
            return
        min_len = 8 if self.is_parent else 4
        if len(new) < min_len:
            self.show_error(f"Password must be at least {min_len} characters.")
            return
        if self.has_current and new == current_pw:
            self.show_error("New password must differ from current.")
            return
        if new != confirm:
            self.show_error("Passwords do not match.")
            return

        self._new_hash = hash_password(new)
        self.accept()

    def new_hash(self):
        return self._new_hash


# ─────────────────────────────────────────────────────────────────────────────
# Website blocker wrapper (hosts-file I/O runs on a background thread)
# ─────────────────────────────────────────────────────────────────────────────
import threading as _threading


class WebsiteBlocker:
    def __init__(self):
        self._active: list[str] = []
        self._is_blocking = False
        self.last_error = None
        self._lock = _threading.Lock()

    def _apply(self):
        """Run the appropriate hosts-file operation on a daemon thread.

        When ``_is_blocking`` is True, always calls ``block_sites()`` (even
        if ``_active`` was populated by a prior ``sync()`` call).
        When ``_is_blocking`` is False, calls ``unblock_sites()`` only if
        there were previously blocked entries to clean up.
        """
        def _worker():
            with self._lock:
                if self._is_blocking:
                    ok = block_sites(self._active)
                    self.last_error = None if ok else "permission"
                elif self._active:
                    ok = unblock_sites()
                    self.last_error = None if ok else "permission"
        t = _threading.Thread(target=_worker, daemon=True)
        t.start()

    def sync(self, sites):
        """Update the active sites list.  Re-applies immediately if blocking."""
        self._active = list(sites)
        if self._is_blocking:
            self._apply()

    def start(self):
        """Enable blocking and apply to the hosts file."""
        self._is_blocking = True
        self._apply()

    def stop(self):
        """Disable blocking and remove entries from the hosts file."""
        self._is_blocking = False
        self._apply()

    def clear_error(self):
        self.last_error = None


# ─────────────────────────────────────────────────────────────────────────────
# Timer signals bridge
# ─────────────────────────────────────────────────────────────────────────────
class TimerSignals(QObject):
    tick = Signal(int, str)
    phase = Signal(str, int)


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────
class FocusLockApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = Storage()

        theme_name = self.storage.get("theme", "dark").lower()
        self.theme = Theme(theme_name, THEMES[theme_name])
        self.preset = self.storage.get("preset", "Classic")
        self.timer_sig = TimerSignals()

        # Cached session name (avoids DB query every tick)
        self._cached_session_name = self.storage.get("session_name", "")

        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.setMinimumSize(900, 650)
        self.theme.apply_to_app(self)

        # Blockers
        self.app_blocker = AppBlocker()
        self.app_blocker.set_enabled_apps(self.storage.get_enabled_apps())
        self.site_blocker = WebsiteBlocker()
        self.site_blocker.sync(self.storage.get_enabled_sites())

        # Actual-time tracking
        self._work_start_time = None
        self._actual_work_minutes = 0

        # Suppress spinbox signals during programmatic updates
        self._spin_lock = False

        # Password throttling state (BUG-12)
        self._pw_fail_count = 0
        self._pw_last_fail = 0.0

        # Timer
        self._init_timer_from_preset()

        # UI
        self._build_ui()
        self._setup_tray()

        # Signals
        self.timer_sig.tick.connect(self._on_tick_ui)
        self.timer_sig.phase.connect(self._on_phase_ui)

        self._on_tick_ui(self.timer.remaining, self.timer.phase)
        self.update_stats_ui()
        self.show()

        # Install event filter to block Alt+F4 when strict mode is active
        QApplication.instance().installEventFilter(self)

    # ───────────────────────────────────────────────────────────────────────
    # Timer
    # ───────────────────────────────────────────────────────────────────────
    def _get_preset_config(self, name=None):
        """Return the preset dict for *name* (or self.preset)."""
        return PRESETS.get(name or self.preset, PRESETS["Classic"])

    def _init_timer_from_preset(self, name=None):
        pc = self._get_preset_config(name)
        if hasattr(self, "timer") and self.timer:
            self.timer.pause()
        self.timer = PomodoroTimer(
            pc["work"], pc["break"],
            on_tick=lambda r, ph: self.timer_sig.tick.emit(r, ph),
            on_phase=lambda ph, cyc: self.timer_sig.phase.emit(ph, cyc),
            long_break_min=pc.get("long_break", 0),
            cycles_per_set=pc.get("cycles", 4),
        )

    def _play_sound(self):
        """Play a short system beep to alert the user."""
        try:
            winsound.Beep(800, 300)
        except Exception:
            pass

    # ───────────────────────────────────────────────────────────────────────
    # Password helpers
    # ───────────────────────────────────────────────────────────────────────
    def _password_hash(self):
        return self.storage.get("password_hash", "")

    def _parent_password_hash(self):
        return self.storage.get("parent_password_hash", "")

    def _require_password(self, title="Password Required", prompt="Enter password to continue:"):
        """Show password dialog.  Returns True if verified, False if cancelled."""
        ph = self._password_hash()
        if not ph:
            return True  # no password set – allow everything

        # BUG-12: throttle repeated failed attempts
        if self._pw_fail_count > 0:
            delay = min(2 ** self._pw_fail_count, 30)
            elapsed = time.time() - self._pw_last_fail
            if elapsed < delay:
                remaining = int(delay - elapsed)
                QMessageBox.information(
                    self, "Please wait",
                    f"Too many failed attempts. Please wait {remaining} second(s)."
                )
                return False

        dlg = PasswordDialog(self, self.theme, title, prompt)
        dlg.exec()
        if not dlg.was_confirmed():
            return False
        ok, new_hash = verify_password(dlg.password(), ph)
        if ok:
            self._pw_fail_count = 0
            if new_hash:
                self.storage.set("password_hash", new_hash)
        else:
            self._pw_fail_count += 1
            self._pw_last_fail = time.time()
        return ok

    def _require_parent_password(self, title="Parent Password Required"):
        ph = self._parent_password_hash()
        if not ph:
            return True

        # BUG-12: throttle repeated failed attempts (shared counter with session password)
        if self._pw_fail_count > 0:
            delay = min(2 ** self._pw_fail_count, 30)
            elapsed = time.time() - self._pw_last_fail
            if elapsed < delay:
                remaining = int(delay - elapsed)
                QMessageBox.information(
                    self, "Please wait",
                    f"Too many failed attempts. Please wait {remaining} second(s)."
                )
                return False

        dlg = PasswordDialog(self, self.theme, title, "Enter parent password:")
        dlg.exec()
        if not dlg.was_confirmed():
            return False
        ok, new_hash = verify_password(dlg.password(), ph)
        if ok:
            self._pw_fail_count = 0
            if new_hash:
                self.storage.set("parent_password_hash", new_hash)
        else:
            self._pw_fail_count += 1
            self._pw_last_fail = time.time()
        return ok

    # ───────────────────────────────────────────────────────────────────────
    # UI construction
    # ───────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(16, 24, 16, 24)
        sb.setSpacing(12)

        title_lbl = label(APP_NAME, "title", self.theme)
        title_lbl.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {self.theme.c['text']};"
        )
        sb.addWidget(title_lbl)
        sb.addSpacing(24)

        self.nav_btns = {}
        for page in ("Session", "Applications", "Websites", "Stats", "Settings"):
            btn = button(
                page,
                lambda checked=False, p=page: self._switch_page(p),
                variant="ghost", theme=self.theme,
            )
            btn.setStyleSheet(
                btn.styleSheet()
                + " text-align: left; font-size: 15px; padding: 12px 16px;"
            )
            self.nav_btns[page] = btn
            sb.addWidget(btn)

        sb.addStretch()

        theme_btn = button(
            f"Theme: {self.theme.name.capitalize()}",
            self._toggle_theme,
            variant="secondary", theme=self.theme,
        )
        sb.addWidget(theme_btn)

        main_layout.addWidget(self.sidebar)

        # ── Stacked pages ──
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        self.pages = {
            "Session": self._build_session_page(),
            "Applications": self._build_apps_page(),
            "Websites": self._build_sites_page(),
            "Stats": self._build_stats_page(),
            "Settings": self._build_settings_page(),
        }
        for pg in self.pages.values():
            self.stack.addWidget(pg)

        self._switch_page("Session")

    def _switch_page(self, page_name):
        c = self.theme.c
        for name, btn in self.nav_btns.items():
            if name == page_name:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {c['card']}; color: {c['accent']}; "
                    f"border: none; border-radius: 8px; padding: 12px 16px; "
                    f"font-weight: bold; text-align: left; font-size: 15px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {c['subtext']}; "
                    f"border: none; border-radius: 8px; padding: 12px 16px; "
                    f"font-weight: bold; text-align: left; font-size: 15px; }}\n"
                    f"QPushButton:hover {{ background-color: {c['card']}; color: {c['text']}; }}"
                )
        self.stack.setCurrentWidget(self.pages[page_name])

    # ───────────────────────────────────────────────────────────────────────
    # Session page
    # ───────────────────────────────────────────────────────────────────────
    def _build_session_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)

        # ═══════════════════════════════════════════════════════════════════
        # LEFT: Timer display
        # ═══════════════════════════════════════════════════════════════════
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setAlignment(Qt.AlignCenter)

        # Session name display (cached)
        self.session_name_lbl = label(
            self._cached_session_name, "subtext", self.theme,
        )
        self.session_name_lbl.setStyleSheet(
            f"font-size: 13px; color: {self.theme.c['subtext']}; font-style: italic;"
        )
        self.session_name_lbl.setAlignment(Qt.AlignCenter)
        left_l.addWidget(self.session_name_lbl)

        self.phase_lbl = label("FOCUS TIME", "accent", self.theme)
        self.phase_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {self.theme.c['accent']}; "
            "letter-spacing: 2px;"
        )
        self.phase_lbl.setAlignment(Qt.AlignCenter)
        left_l.addWidget(self.phase_lbl)

        self.circular_timer = CircularTimer(self.theme, size=300)
        left_l.addWidget(self.circular_timer, alignment=Qt.AlignCenter)

        self.time_lbl = label("00:00", "title", self.theme)
        self.time_lbl.setStyleSheet(
            f"font-size: 48px; font-family: 'Segoe UI Semibold'; "
            f"color: {self.theme.c['text']};"
        )
        self.time_lbl.setAlignment(Qt.AlignCenter)
        left_l.addWidget(self.time_lbl, alignment=Qt.AlignCenter)

        # Cycle counter
        self.cycle_lbl = label("", "subtext", self.theme)
        self.cycle_lbl.setStyleSheet(
            f"font-size: 13px; color: {self.theme.c['subtext']};"
        )
        self.cycle_lbl.setAlignment(Qt.AlignCenter)
        left_l.addWidget(self.cycle_lbl)
        self._update_cycle_label()

        left_l.addSpacing(16)

        # Controls: Skip | Start | Reset
        controls = QHBoxLayout()
        controls.addStretch()

        self.skip_btn = button(
            "\u23ED", self._skip_timer, variant="ghost", theme=self.theme
        )
        self.skip_btn.setFixedSize(48, 48)
        self.skip_btn.setStyleSheet(
            self.skip_btn.styleSheet() + " font-size: 20px; border-radius: 24px;"
        )
        controls.addWidget(self.skip_btn)

        self.start_btn = button(
            "Start Session", self._toggle_timer, variant="primary", theme=self.theme
        )
        self.start_btn.setMinimumWidth(160)
        controls.addWidget(self.start_btn)

        self.reset_btn = button(
            "Reset", self._reset_timer, variant="secondary", theme=self.theme
        )
        controls.addWidget(self.reset_btn)

        controls.addStretch()
        left_l.addLayout(controls)

        layout.addWidget(left, 1)

        # ═══════════════════════════════════════════════════════════════════
        # RIGHT: Preset cards + Custom durations
        # ═══════════════════════════════════════════════════════════════════
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        right_inner = QWidget()
        right_inner.setStyleSheet("background: transparent;")
        right_l = QVBoxLayout(right_inner)
        right_l.setContentsMargins(0, 0, 8, 0)
        right_l.setSpacing(12)

        # ── Preset cards ──
        right_l.addWidget(label("Presets", "heading", self.theme))
        right_l.addSpacing(8)

        self.preset_cards = {}
        for name, pc in PRESETS.items():
            card = make_card(self.theme)
            card.setCursor(Qt.PointingHandCursor)
            card_l = QVBoxLayout(card)
            card_l.setContentsMargins(16, 14, 16, 14)
            card_l.setSpacing(4)

            card_name = label(name, "text", self.theme)
            card_name.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {self.theme.c['text']};"
            )
            card_l.addWidget(card_name)

            card_info = label(
                f"{pc['work']}m focus \u2022 {pc['break']}m break \u2022 {pc.get('long_break', 15)}m long \u2022 {pc.get('cycles', 4)} cycles",
                "subtext", self.theme,
            )
            card_info.setStyleSheet(f"font-size: 12px; color: {self.theme.c['subtext']};")
            card_l.addWidget(card_info)

            card.mousePressEvent = lambda ev, n=name: self._set_preset(n)
            self.preset_cards[name] = card
            right_l.addWidget(card)

        right_l.addSpacing(16)

        # ── Custom durations ──
        right_l.addWidget(label("Adjust Durations", "heading", self.theme))
        right_l.addSpacing(8)

        custom_card = make_card(self.theme)
        cc_l = QVBoxLayout(custom_card)
        cc_l.setContentsMargins(16, 16, 16, 16)
        cc_l.setSpacing(12)

        pc = self._get_preset_config()

        # Work minutes
        work_row = QHBoxLayout()
        work_row.addWidget(label("Work (min)", "text", self.theme))
        work_row.addStretch()
        self.work_spin = QSpinBox()
        self.work_spin.setRange(1, 180)
        self.work_spin.setValue(pc["work"])
        self.work_spin.valueChanged.connect(self._on_spin_changed)
        self.work_spin.setStyleSheet(self._spin_style())
        work_row.addWidget(self.work_spin)
        cc_l.addLayout(work_row)

        # Break minutes
        break_row = QHBoxLayout()
        break_row.addWidget(label("Break (min)", "text", self.theme))
        break_row.addStretch()
        self.break_spin = QSpinBox()
        self.break_spin.setRange(1, 60)
        self.break_spin.setValue(pc["break"])
        self.break_spin.valueChanged.connect(self._on_spin_changed)
        self.break_spin.setStyleSheet(self._spin_style())
        break_row.addWidget(self.break_spin)
        cc_l.addLayout(break_row)

        # Long break minutes
        lb_row = QHBoxLayout()
        lb_row.addWidget(label("Long Break (min)", "text", self.theme))
        lb_row.addStretch()
        self.long_break_spin = QSpinBox()
        self.long_break_spin.setRange(0, 60)
        self.long_break_spin.setValue(pc.get("long_break", 15))
        self.long_break_spin.valueChanged.connect(self._on_spin_changed)
        self.long_break_spin.setStyleSheet(self._spin_style())
        lb_row.addWidget(self.long_break_spin)
        cc_l.addLayout(lb_row)

        # Cycles per set
        cyc_row = QHBoxLayout()
        cyc_row.addWidget(label("Cycles", "text", self.theme))
        cyc_row.addStretch()
        self.cycles_spin = QSpinBox()
        self.cycles_spin.setRange(1, 12)
        self.cycles_spin.setValue(pc.get("cycles", 4))
        self.cycles_spin.valueChanged.connect(self._on_spin_changed)
        self.cycles_spin.setStyleSheet(self._spin_style())
        cyc_row.addWidget(self.cycles_spin)
        cc_l.addLayout(cyc_row)

        # Apply button
        apply_row = QHBoxLayout()
        apply_row.addStretch()
        self.apply_btn = button(
            "Apply Custom", self._apply_custom, variant="primary", theme=self.theme
        )
        self.apply_btn.setMinimumWidth(120)
        apply_row.addWidget(self.apply_btn)
        cc_l.addLayout(apply_row)

        right_l.addWidget(custom_card)
        right_l.addStretch()

        right_scroll.setWidget(right_inner)
        layout.addWidget(right_scroll, 1)

        self._update_preset_cards()
        return page

    def _spin_style(self):
        c = self.theme.c
        return (
            f"QSpinBox {{ background-color: {c['input']}; color: {c['text']}; "
            f"border: 1px solid {c['border']}; border-radius: 6px; "
            f"padding: 6px 10px; font-size: 14px; min-width: 60px; }}"
            f"QSpinBox:focus {{ border: 1px solid {c['accent']}; }}"
        )

    def _update_preset_cards(self):
        """Highlight the active preset card."""
        c = self.theme.c
        for name, card in self.preset_cards.items():
            if name == self.preset:
                card.setStyleSheet(
                    f"QFrame {{ background-color: {c['accent']}; "
                    f"border: 2px solid {c['accent']}; border-radius: 12px; }}"
                )
                # Re-style child labels for contrast
                for i in range(card.layout().count()):
                    w = card.layout().itemAt(i).widget()
                    if w and isinstance(w, QLabel):
                        w.setStyleSheet(
                            f"font-size: 14px; font-weight: bold; color: white;"
                            if w.text() == name else
                            f"font-size: 12px; color: rgba(255,255,255,0.8);"
                        )
            else:
                card.setStyleSheet("")  # revert to make_card default
                for i in range(card.layout().count()):
                    w = card.layout().itemAt(i).widget()
                    if w and isinstance(w, QLabel):
                        w.setStyleSheet(
                            f"font-size: 14px; font-weight: bold; color: {c['text']};"
                            if w.text() == name else
                            f"font-size: 12px; color: {c['subtext']};"
                        )

    # ───────────────────────────────────────────────────────────────────────
    # Preset & custom duration logic
    # ───────────────────────────────────────────────────────────────────────
    def _set_preset(self, name):
        """Click a preset card -> load its values, update spinboxes, rebuild timer."""
        self.preset = name
        self.storage.set("preset", name)
        pc = self._get_preset_config(name)

        # Sync spinboxes (suppress signals to avoid double rebuild)
        self._spin_lock = True
        self.work_spin.setValue(pc["work"])
        self.break_spin.setValue(pc["break"])
        self.long_break_spin.setValue(pc.get("long_break", 15))
        self.cycles_spin.setValue(pc.get("cycles", 4))
        self._spin_lock = False

        self._recreate_timer(pc)
        self._update_preset_cards()

    def _on_spin_changed(self):
        """Any spinbox changed -> switch to Custom preset and rebuild."""
        if self._spin_lock:
            return
        self.preset = "Custom"
        self.storage.set("preset", "Custom")
        self._update_preset_cards()
        self._apply_custom()

    def _apply_custom(self):
        """Read spinbox values and rebuild the timer."""
        work = self.work_spin.value()
        brk = self.break_spin.value()
        lb = self.long_break_spin.value()
        cyc = self.cycles_spin.value()
        pc = {"work": work, "break": brk, "long_break": lb, "cycles": cyc}
        self._recreate_timer(pc)

    def _recreate_timer(self, pc):
        """Rebuild timer with new config, preserving running state and remaining."""
        was_running = self.timer.is_running
        ph = self.timer.phase
        cycles = self.timer.cycles

        # When not running, reset remaining to the new full phase duration.
        # When running, clamp remaining to the new total.
        new_phase_sec = pc["work"] * 60 if ph == "work" else pc["break"] * 60
        if was_running:
            remaining = min(self.timer.remaining, new_phase_sec)
        else:
            remaining = new_phase_sec

        if was_running:
            self.timer.pause()

        self.timer = PomodoroTimer(
            pc["work"], pc["break"],
            on_tick=lambda r, ph: self.timer_sig.tick.emit(r, ph),
            on_phase=lambda ph, cyc: self.timer_sig.phase.emit(ph, cyc),
            long_break_min=pc.get("long_break", 0),
            cycles_per_set=pc.get("cycles", 4),
        )
        self.timer.set_remaining(remaining)
        self.timer.set_phase(ph)
        self.timer.cycles = cycles
        self._update_cycle_label()

        if was_running:
            self.timer.start()

        self._on_tick_ui(self.timer.remaining, self.timer.phase)

    def _update_cycle_label(self):
        total = self.timer.cycles_per_set
        cur = self.timer.cycles
        if hasattr(self, "cycle_lbl"):
            self.cycle_lbl.setText(f"Pomodoro {cur} of {total}")

    def _set_controls_enabled(self, enabled):
        """Lock/unlock preset cards and spinboxes while a session is active."""
        if hasattr(self, "preset_cards"):
            for card in self.preset_cards.values():
                card.setEnabled(enabled)
        for attr in ("work_spin", "break_spin", "long_break_spin", "cycles_spin"):
            if hasattr(self, attr):
                getattr(self, attr).setEnabled(enabled)

    # ───────────────────────────────────────────────────────────────────────
    # Applications page
    # ───────────────────────────────────────────────────────────────────────
    def _build_apps_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)

        header = QHBoxLayout()
        header.addWidget(label("Blocked Applications", "title", self.theme))
        header.addStretch()
        self.app_count_lbl = label("0 apps blocked", "subtext", self.theme)
        header.addWidget(self.app_count_lbl)
        add_btn = button(
            "+ Add App", self._open_app_picker, variant="primary", theme=self.theme
        )
        header.addWidget(add_btn)
        layout.addLayout(header)
        layout.addSpacing(16)

        self.app_scroll = ScrollableFrame(self.theme)
        layout.addWidget(self.app_scroll)
        self._rebuild_app_cards()
        return page

    # ───────────────────────────────────────────────────────────────────────
    # Websites page
    # ───────────────────────────────────────────────────────────────────────
    def _build_sites_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)

        header = QHBoxLayout()
        header.addWidget(label("Blocked Websites", "title", self.theme))
        header.addStretch()
        self.site_count_lbl = label("0 sites blocked", "subtext", self.theme)
        header.addWidget(self.site_count_lbl)
        add_btn = button(
            "+ Add Website", self._open_site_picker, variant="primary", theme=self.theme
        )
        header.addWidget(add_btn)
        layout.addLayout(header)
        layout.addSpacing(16)

        self.site_scroll = ScrollableFrame(self.theme)
        layout.addWidget(self.site_scroll)
        self._rebuild_site_cards()
        return page

    # ───────────────────────────────────────────────────────────────────────
    # Stats page
    # ───────────────────────────────────────────────────────────────────────
    def _build_stats_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)

        layout.addWidget(label("Statistics", "title", self.theme))
        layout.addSpacing(20)

        grid = QHBoxLayout()
        self.stat_sessions = stat_card(self.theme, "\U0001F345", "Total Sessions", "0")
        self.stat_hours = stat_card(
            self.theme, "\u231B", "Focus Time", "0h 0m",
            color=self.theme.c["timer_work"],
        )
        self.stat_streak = stat_card(
            self.theme, "\U0001F525", "Current Streak", "0 days",
            color=self.theme.c["warn"],
        )
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

    # ───────────────────────────────────────────────────────────────────────
    # Settings page
    # ───────────────────────────────────────────────────────────────────────
    def _build_settings_page(self):
        c = self.theme.c

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(40, 40, 40, 40)
        page_layout.setSpacing(16)

        page_layout.addWidget(label("Settings", "title", self.theme))

        # Tab widget
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {c['border']};
                border-radius: 8px;
                background: {c['card']};
            }}
            QTabBar::tab {{
                background: {c['bg']};
                color: {c['muted']};
                border: 1px solid {c['border']};
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 10px 20px;
                margin-right: 2px;
                font-size: 13px;
            }}
            QTabBar::tab:selected {{
                background: {c['card']};
                color: {c['accent']};
                font-weight: bold;
            }}
            QTabBar::tab:hover {{
                color: {c['text']};
            }}
        """)

        # Helper: toggle row inside a layout
        def _toggle_row(parent, text, storage_key, default=True, callback=None):
            row = QHBoxLayout()
            row.addWidget(label(text, "text", self.theme))
            row.addStretch()
            tgl = ToggleButton(self.theme, initial_state=self.storage.get(storage_key, default))
            if callback:
                tgl.toggled.connect(callback)
            else:
                tgl.toggled.connect(lambda s, k=storage_key: self.storage.set(k, s))
            row.addWidget(tgl)
            parent.addLayout(row)
            parent.addWidget(divider(self.theme))
            return tgl

        # ── Tab 1: General ──────────────────────────────────────────────
        tab_general = QWidget()
        gen_layout = QVBoxLayout(tab_general)
        gen_layout.setContentsMargins(24, 24, 24, 24)
        gen_layout.setSpacing(0)

        gen_layout.addWidget(label("General", "heading", self.theme))
        gen_layout.addSpacing(16)

        self.startup_tgl = _toggle_row(
            gen_layout, "Start with Windows", "startup",
            default=startup_is_on(), callback=self._toggle_startup,
        )
        self.tray_tgl = _toggle_row(gen_layout, "Minimize to tray on close", "minimize_to_tray")
        self.auto_start_tgl = _toggle_row(gen_layout, "Auto-start next phase", "auto_start")

        gen_layout.addStretch()
        tabs.addTab(tab_general, "General")

        # ── Tab 2: Session ──────────────────────────────────────────────
        tab_session = QWidget()
        sess_layout = QVBoxLayout(tab_session)
        sess_layout.setContentsMargins(24, 24, 24, 24)
        sess_layout.setSpacing(0)

        sess_layout.addWidget(label("Focus Session", "heading", self.theme))
        sess_layout.addSpacing(16)

        self.block_sites_tgl = _toggle_row(
            sess_layout, "Block websites during focus", "block_websites",
        )

        sess_layout.addWidget(label("Session Name", "subtext", self.theme))
        sess_layout.addSpacing(6)
        self.session_name_input = QLineEdit()
        self.session_name_input.setPlaceholderText("Name your focus session...")
        self.session_name_input.setText(self._cached_session_name)
        self.session_name_input.textChanged.connect(self._on_session_name_changed)
        sess_layout.addWidget(self.session_name_input)

        sess_layout.addStretch()
        tabs.addTab(tab_session, "Session")

        # ── Tab 3: Notifications ────────────────────────────────────────
        tab_notif = QWidget()
        notif_layout = QVBoxLayout(tab_notif)
        notif_layout.setContentsMargins(24, 24, 24, 24)
        notif_layout.setSpacing(0)

        notif_layout.addWidget(label("Notifications", "heading", self.theme))
        notif_layout.addSpacing(16)

        self.notify_tgl = _toggle_row(notif_layout, "Notify on break", "notify_break")
        self.sound_tgl = _toggle_row(notif_layout, "Sound alert on phase change", "sound_alerts")

        notif_layout.addStretch()
        tabs.addTab(tab_notif, "Notifications")

        # ── Tab 4: Security ─────────────────────────────────────────────
        tab_sec = QWidget()
        sec_layout = QVBoxLayout(tab_sec)
        sec_layout.setContentsMargins(24, 24, 24, 24)
        sec_layout.setSpacing(0)

        sec_layout.addWidget(label("Security", "heading", self.theme))
        sec_layout.addSpacing(16)

        # Lock session
        lock_row = QHBoxLayout()
        lock_row.addWidget(label("Lock session (password to pause/stop)", "text", self.theme))
        lock_row.addStretch()
        self.lock_session_tgl = ToggleButton(
            self.theme, initial_state=bool(self.storage.get("password_hash", "")),
        )
        self.lock_session_tgl.toggled.connect(self._on_lock_session_toggle)
        lock_row.addWidget(self.lock_session_tgl)
        sec_layout.addLayout(lock_row)
        sec_layout.addWidget(divider(self.theme))

        # Strict mode
        self.strict_mode_tgl = _toggle_row(
            sec_layout, "Strict mode (password to quit)", "strict_mode", default=False,
        )

        # Session password
        sec_layout.addWidget(label("Session Password", "subtext", self.theme))
        sec_layout.addSpacing(6)
        spw_row = QHBoxLayout()
        self.pw_status_lbl = label(self._pw_status_text(), "text", self.theme)
        spw_row.addWidget(self.pw_status_lbl)
        spw_row.addStretch()
        set_pw_btn = button("Set Password", self._set_password, variant="secondary", theme=self.theme)
        spw_row.addWidget(set_pw_btn)
        sec_layout.addLayout(spw_row)
        sec_layout.addWidget(divider(self.theme))

        # Parent password
        sec_layout.addWidget(label("Parent Password", "subtext", self.theme))
        sec_layout.addSpacing(6)
        ppw_row = QHBoxLayout()
        self.parent_pw_status_lbl = label(self._parent_pw_status_text(), "text", self.theme)
        ppw_row.addWidget(self.parent_pw_status_lbl)
        ppw_row.addStretch()
        set_parent_btn = button("Set Parent Password", self._set_parent_password, variant="secondary", theme=self.theme)
        ppw_row.addWidget(set_parent_btn)
        sec_layout.addLayout(ppw_row)
        sec_layout.addWidget(divider(self.theme))

        # Clear
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        clear_pw_btn = button("Clear All Passwords", self._clear_passwords, variant="danger", theme=self.theme)
        clear_row.addWidget(clear_pw_btn)
        sec_layout.addLayout(clear_row)

        sec_layout.addStretch()
        tabs.addTab(tab_sec, "Security")

        page_layout.addWidget(tabs)
        return page

    def _pw_status_text(self):
        return "Set" if self.storage.get("password_hash", "") else "Not set"

    def _parent_pw_status_text(self):
        return "Set" if self.storage.get("parent_password_hash", "") else "Not set"

    # ───────────────────────────────────────────────────────────────────────
    # Session name (cached)
    # ───────────────────────────────────────────────────────────────────────
    def _on_session_name_changed(self, text):
        self._cached_session_name = text
        self.storage.set("session_name", text)
        if hasattr(self, "session_name_lbl"):
            self.session_name_lbl.setText(text)

    # ───────────────────────────────────────────────────────────────────────
    # Timer actions
    # ───────────────────────────────────────────────────────────────────────
    def _toggle_timer(self):
        if self.timer.is_running:
            # Pause – requires password if locked
            if not self._require_password("Unlock to Pause", "Enter password to pause the session:"):
                return
            self.timer.pause()
            self._track_work_time(pause=True)
            self.app_blocker.stop()
            if self.storage.get("block_websites", True):
                self.site_blocker.stop()
            self.start_btn.setText("Resume Session")
            self.circular_timer.set_running(False)
            self._set_controls_enabled(True)
        else:
            self.timer.start()
            self._track_work_time(start=True)
            if self.timer.phase == "work":
                self.app_blocker.start()
                if self.storage.get("block_websites", True):
                    self.site_blocker.start()
                    if self.site_blocker.last_error == "permission":
                        notify(
                            APP_NAME,
                            "Website blocking failed: run as Administrator to enable.",
                            self.tray if hasattr(self, "tray") else None,
                        )
            self.start_btn.setText(
                "Pause Session" if self.timer.phase == "work" else "Pause Break"
            )
            self.circular_timer.set_running(True)
            self._set_controls_enabled(False)

    def _skip_timer(self):
        if self.timer.is_running:
            if not self._require_password("Unlock to Skip", "Enter password to skip phase:"):
                return
            self.timer.skip()

    def _reset_timer(self):
        # Reset requires parent password if session is locked and timer is active
        if self.timer.is_running or self.timer.remaining != self.timer.work_sec:
            if not self._require_parent_password("Unlock to Reset"):
                return
        self.timer.reset()
        self._track_work_time(reset=True)
        self.app_blocker.stop()
        if self.storage.get("block_websites", True):
            self.site_blocker.stop()
        self.start_btn.setText("Start Session")
        self.circular_timer.set_running(False)
        self._set_controls_enabled(True)
        self.phase_lbl.setText("FOCUS TIME")
        self.phase_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {self.theme.c['accent']}; "
            "letter-spacing: 2px;"
        )
        self._update_cycle_label()
        self._on_tick_ui(self.timer.remaining, self.timer.phase)

    def _on_tick_ui(self, rem, phase):
        mins, secs = divmod(rem, 60)
        self.time_lbl.setText(f"{mins:02d}:{secs:02d}")

        total = self.timer.phase_total
        self.circular_timer.set_value(rem, total, phase)

        # Update session name display (cached, no DB query)
        if hasattr(self, "session_name_lbl"):
            self.session_name_lbl.setText(self._cached_session_name)

        # Tray tooltip with session name (cached)
        if hasattr(self, "tray") and self.tray:
            sn = self._cached_session_name
            name_part = f" - {sn}" if sn else ""
            self.tray.setToolTip(f"{APP_NAME}{name_part} - {mins:02d}:{secs:02d} ({phase})")

    def _on_phase_ui(self, phase, cycles):
        sn = self._cached_session_name
        name_part = f" ({sn})" if sn else ""

        # Sound alert
        if self.storage.get("sound_alerts", True):
            self._play_sound()

        if self.storage.get("notify_break", True):
            msg = f"Phase complete! Time for {'break' if phase == 'break' else 'focus'}."
            notify(f"{APP_NAME}{name_part}", msg, self.tray if hasattr(self, "tray") else None)

        p_text = "FOCUS TIME" if phase == "work" else "BREAK TIME"
        color = self.theme.c["accent"] if phase == "work" else self.theme.c["success"]
        self.phase_lbl.setText(p_text)
        self.phase_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {color}; letter-spacing: 2px;"
        )

        self._update_cycle_label()

        if phase == "break":
            self.app_blocker.stop()
            if self.storage.get("block_websites", True):
                self.site_blocker.stop()
            self._record_session()
        else:
            self.app_blocker.start()
            if self.storage.get("block_websites", True):
                self.site_blocker.start()
                if self.site_blocker.last_error == "permission":
                    notify(
                        APP_NAME,
                        "Website blocking failed: run as Administrator to enable.",
                        self.tray if hasattr(self, "tray") else None,
                    )

        # Immediately sync the time display and circular timer to the new phase
        self._on_tick_ui(self.timer.remaining, phase)

        # Auto-start toggle
        if self.storage.get("auto_start", True):
            self.start_btn.setText(
                "Pause Session" if phase == "work" else "Pause Break"
            )
            self.circular_timer.set_running(True)
            self._set_controls_enabled(False)
            if phase == "work":
                self._track_work_time(start=True)
        else:
            self.timer.pause()
            self.start_btn.setText("Resume Session")
            self.circular_timer.set_running(False)
            self._set_controls_enabled(True)
            if phase == "work":
                self._track_work_time(start=True)

    # ───────────────────────────────────────────────────────────────────────
    # Actual work time tracking
    # ───────────────────────────────────────────────────────────────────────
    def _track_work_time(self, start=False, pause=False, reset=False):
        if start and self.timer.phase == "work":
            self._work_start_time = time.time()
        elif pause and self._work_start_time is not None:
            elapsed = time.time() - self._work_start_time
            self._actual_work_minutes += elapsed / 60.0
            self._work_start_time = None
        elif reset:
            self._work_start_time = None
            self._actual_work_minutes = 0

    # ───────────────────────────────────────────────────────────────────────
    # Theme
    # ───────────────────────────────────────────────────────────────────────
    def _toggle_theme(self):
        new_name = "light" if self.theme.name == "dark" else "dark"
        self.storage.set("theme", new_name)

        was_running = self.timer.is_running
        rem = self.timer.remaining
        ph = self.timer.phase
        cycles = self.timer.cycles

        if was_running:
            self.timer.pause()
        self.app_blocker.stop()
        self.site_blocker.stop()

        self.theme = Theme(new_name, THEMES[new_name])
        self.theme.apply_to_app(self)

        # BUG-16: suppress spinbox signal storms while rebuilding UI + timer
        self._spin_lock = True
        self._build_ui()

        self._init_timer_from_preset()
        self.timer.set_remaining(rem)
        self.timer.set_phase(ph)
        self.timer.cycles = cycles
        self._update_cycle_label()
        self._on_tick_ui(rem, ph)
        self._spin_lock = False

        if was_running:
            self.timer.start()
            self.circular_timer.set_running(True)
            if ph == "work":
                self.app_blocker.start()
                if self.storage.get("block_websites", True):
                    self.site_blocker.start()
                self._track_work_time(start=True)

        self.update_stats_ui()

    def _toggle_startup(self, state):
        set_startup(state)

    # ───────────────────────────────────────────────────────────────────────
    # Password management
    # ───────────────────────────────────────────────────────────────────────
    def _on_lock_session_toggle(self, state):
        if state:
            if not self._password_hash():
                # No password set — open dialog to create one (skip current field)
                dlg = SetPasswordDialog(self, self.theme, skip_current=True)
                if dlg.exec() == QDialog.Accepted and dlg.new_hash():
                    self.storage.set("password_hash", dlg.new_hash())
                else:
                    # User cancelled — revert toggle
                    self.lock_session_tgl.setChecked(False, animate=False)
            # Password already exists — toggle is on, nothing to do
        else:
            # Turning off — requires parent password
            if not self._require_parent_password("Disable Session Lock"):
                self.lock_session_tgl.setChecked(True, animate=False)

    def _set_password(self):
        ph = self._password_hash()
        if ph:
            # Password exists — show current password field
            dlg = SetPasswordDialog(self, self.theme, current_hash=ph)
        else:
            # No password yet — skip current field
            dlg = SetPasswordDialog(self, self.theme, skip_current=True)
        if dlg.exec() == QDialog.Accepted and dlg.new_hash():
            self.storage.set("password_hash", dlg.new_hash())
            self.lock_session_tgl.setChecked(True, animate=False)
            if hasattr(self, "pw_status_lbl"):
                self.pw_status_lbl.setText(self._pw_status_text())

    def _set_parent_password(self):
        pph = self._parent_password_hash()
        if pph:
            # Parent password exists — verify current first, then change
            if not self._require_parent_password("Change Parent Password"):
                return
            dlg = SetPasswordDialog(self, self.theme, current_hash=pph, is_parent=True)
        else:
            # No parent password yet — create directly
            dlg = SetPasswordDialog(self, self.theme, is_parent=True, skip_current=True)
        if dlg.exec() == QDialog.Accepted and dlg.new_hash():
            self.storage.set("parent_password_hash", dlg.new_hash())
            if hasattr(self, "parent_pw_status_lbl"):
                self.parent_pw_status_lbl.setText(self._parent_pw_status_text())

    def _clear_passwords(self):
        if not self._require_parent_password("Clear Passwords"):
            return
        self.storage.set("password_hash", "")
        self.storage.set("parent_password_hash", "")
        self.lock_session_tgl.setChecked(False, animate=False)
        if hasattr(self, "pw_status_lbl"):
            self.pw_status_lbl.setText(self._pw_status_text())
        if hasattr(self, "parent_pw_status_lbl"):
            self.parent_pw_status_lbl.setText(self._parent_pw_status_text())

    # ───────────────────────────────────────────────────────────────────────
    # Blocklist – Applications
    # ───────────────────────────────────────────────────────────────────────
    def _open_app_picker(self):
        dlg = AppPickerDialog(self, self.theme, self._add_app)
        dlg.exec()

    def _add_app(self, name, exe):
        self.storage.add_app(exe, name, True)
        self.app_blocker.set_enabled_apps(self.storage.get_enabled_apps())
        self._rebuild_app_cards()

    def _remove_app(self, exe):
        self.storage.remove_app(exe)
        self.app_blocker.set_enabled_apps(self.storage.get_enabled_apps())
        self._rebuild_app_cards()

    def _toggle_app(self, exe, state):
        self.storage.toggle_app(exe, state)
        self.app_blocker.set_enabled_apps(self.storage.get_enabled_apps())

    def _rebuild_app_cards(self):
        layout = self.app_scroll.inner_layout
        for i in reversed(range(layout.count())):
            w = layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        apps = self.storage.get_apps()
        count = 0
        for app in apps:
            card = BlocklistItemCard(
                self.theme, app["name"], app["exe"], "app",
                app["enabled"], self._remove_app, self._toggle_app,
            )
            layout.addWidget(card)
            count += 1
        self.app_count_lbl.setText(f"{count} apps blocked")

    # ───────────────────────────────────────────────────────────────────────
    # Blocklist – Websites
    # ───────────────────────────────────────────────────────────────────────
    def _open_site_picker(self):
        dlg = SitePickerDialog(self, self.theme, self._add_site)
        dlg.exec()

    def _add_site(self, name, domain):
        self.storage.add_site(domain, name, True)
        self.site_blocker.sync(self.storage.get_enabled_sites())
        self._rebuild_site_cards()

    def _remove_site(self, domain):
        self.storage.remove_site(domain)
        self.site_blocker.sync(self.storage.get_enabled_sites())
        self._rebuild_site_cards()

    def _toggle_site(self, domain, state):
        self.storage.toggle_site(domain, state)
        self.site_blocker.sync(self.storage.get_enabled_sites())

    def _rebuild_site_cards(self):
        layout = self.site_scroll.inner_layout
        for i in reversed(range(layout.count())):
            w = layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        sites = self.storage.get_sites()
        count = 0
        for site in sites:
            card = BlocklistItemCard(
                self.theme, site["name"], site["domain"], "site",
                site["enabled"], self._remove_site, self._toggle_site,
            )
            layout.addWidget(card)
            count += 1
        self.site_count_lbl.setText(f"{count} sites blocked")

    # ───────────────────────────────────────────────────────────────────────
    # Stats
    # ───────────────────────────────────────────────────────────────────────
    def _record_session(self):
        if self._actual_work_minutes > 0:
            work_min = max(1, round(self._actual_work_minutes))
        else:
            work_min = self.timer.work_sec // 60
        self.storage.record_session(work_min)
        self._actual_work_minutes = 0
        self._work_start_time = None
        self.update_stats_ui()

    def update_stats_ui(self):
        total_sessions, total_mins = self.storage.get_total_stats()
        current_streak, _ = self.storage.get_streak()

        self.stat_sessions.val_label.setText(str(total_sessions))
        hours, mins = divmod(total_mins, 60)
        self.stat_hours.val_label.setText(f"{hours}h {mins}m")
        self.stat_streak.val_label.setText(f"{current_streak} days")

        today = datetime.date.today()
        labels = []
        data = []
        daily = self.storage.get_daily_stats(days=7)
        for i in range(6, -1, -1):
            d = today - datetime.timedelta(days=i)
            labels.append(d.strftime("%a"))
            data.append(daily.get(d.isoformat(), {}).get("minutes", 0))
        self.chart.set_data(data, labels)

    # ───────────────────────────────────────────────────────────────────────
    # System tray
    # ───────────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        from PySide6.QtWidgets import QStyle
        self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))

        self.tray_menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.showNormal)
        self.tray_menu.addAction(show_action)

        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self._tray_quit)
        self.tray_menu.addAction(quit_action)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def eventFilter(self, obj, event):
        """Block Alt+F4 (CloseEvent with Alt modifier) when strict mode is active."""
        if event.type() == event.Type.Close:
            if self._is_strict_locked():
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        if self._is_strict_locked():
            event.ignore()
            return
        if self.storage.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            notify(APP_NAME, "App minimized to system tray.", self.tray)
        else:
            self._quit()
            event.accept()

    def _quit(self):
        if self._is_strict_locked():
            return
        if self.timer.is_running:
            self.timer.pause()
        self.app_blocker.stop()
        self.site_blocker.stop()
        self.storage.close()
        QApplication.quit()

    def _is_strict_locked(self):
        """Return True if strict mode is active and session is locked + running."""
        if not self.storage.get("strict_mode", False):
            return False
        if not self._password_hash():
            return False
        if not self.timer.is_running:
            return False
        return True

    def _tray_quit(self):
        """Tray Exit action — respects strict mode."""
        if self._is_strict_locked():
            if not self._require_parent_password("Unlock to Quit"):
                return
        self._quit()


if __name__ == "__main__":
    # Request Administrator privileges (needed for hosts-file website blocking)
    from focuslock.platform.elevate import is_admin, request_elevation
    if not is_admin():
        if request_elevation():
            sys.exit(0)
        # If elevation denied, continue without admin (website blocking won't work)

    # Configure rotating log file
    log_dir = os.getenv("APPDATA", ".") + "/FocusLock"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "focuslock.log")
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.WARNING)

    app = QApplication(sys.argv)
    window = FocusLockApp()
    sys.exit(app.exec())
