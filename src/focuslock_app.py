"""
FocusLock v2.0
by zadwen — github.com/zadwen/FocusLock

Premium focus & distraction-blocking app for Windows.
"""

# ── Silence CMD windows for all subprocesses immediately ─────────────────────
import subprocess as _subprocess
_NW = 0x08000000

class _PatchedPopen(_subprocess.Popen):
    def __init__(self, *a, **kw):
        kw.setdefault("creationflags", 0)
        kw["creationflags"] |= _NW
        kw.setdefault("stdout", _subprocess.DEVNULL)
        kw.setdefault("stderr", _subprocess.DEVNULL)
        super().__init__(*a, **kw)

_subprocess.Popen = _PatchedPopen
import subprocess  # noqa: E402  (patched version)

# ── Hide own console window ───────────────────────────────────────────────────
import ctypes as _ctypes
try:
    _ctypes.windll.user32.ShowWindow(
        _ctypes.windll.kernel32.GetConsoleWindow(), 0
    )
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Standard imports
# ─────────────────────────────────────────────────────────────────────────────
import sys, os, datetime, hashlib, threading, time, winreg
import tkinter as tk
from tkinter import simpledialog, messagebox
from pathlib import Path

# ── Add src/ to path so package imports work when running this file directly ─
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# ─────────────────────────────────────────────────────────────────────────────
# Package imports
# ─────────────────────────────────────────────────────────────────────────────
from focuslock.constants import APP_NAME, VERSION, PRESETS, THEMES
from focuslock.config import load_config, save_config, load_stats, save_stats
from focuslock.blocking.app_blocker import AppBlocker
from focuslock.blocking.website_blocker import block_sites, unblock_sites
from focuslock.core.timer import PomodoroTimer
from focuslock.platform.notifications import notify
from focuslock.platform.startup import set_startup, startup_is_on
from focuslock.ui.widgets import (
    Theme, CircularTimer, ScrollableFrame, BarChart,
    label, button, entry, toggle_button, stat_card, blocklist_item_card,
)
from focuslock.ui.dialogs import AppPickerDialog, SitePickerDialog

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar nav item
# ─────────────────────────────────────────────────────────────────────────────
class NavItem(tk.Frame):
    def __init__(self, parent, theme, icon, text, command, **kwargs):
        self.theme = theme
        c = theme.c
        super().__init__(parent, bg=c["sidebar"], cursor="hand2", **kwargs)
        self._active = False
        self._cmd = command

        self._icon_lbl = tk.Label(
            self, text=icon, font=("Segoe UI", 15),
            bg=c["sidebar"], fg=c["subtext"],
            width=3,
        )
        self._icon_lbl.pack(side="left", padx=(12, 4), pady=14)

        self._text_lbl = tk.Label(
            self, text=text, font=("Segoe UI", 10),
            bg=c["sidebar"], fg=c["subtext"], anchor="w",
        )
        self._text_lbl.pack(side="left", fill="x", expand=True)

        # Active indicator bar
        self._bar = tk.Frame(self, bg=c["sidebar"], width=3)
        self._bar.pack(side="right", fill="y")

        for w in (self, self._icon_lbl, self._text_lbl):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def _on_click(self, _e):
        self._cmd()

    def _on_enter(self, _e):
        if not self._active:
            c = self.theme.c
            self.configure(bg=c["card_hover"])
            self._icon_lbl.configure(bg=c["card_hover"])
            self._text_lbl.configure(bg=c["card_hover"])

    def _on_leave(self, _e):
        if not self._active:
            c = self.theme.c
            self.configure(bg=c["sidebar"])
            self._icon_lbl.configure(bg=c["sidebar"])
            self._text_lbl.configure(bg=c["sidebar"])

    def set_active(self, active: bool):
        self._active = active
        c = self.theme.c
        if active:
            bg = c["card"]
            fg = c["accent"]
            bar_bg = c["accent"]
        else:
            bg = c["sidebar"]
            fg = c["subtext"]
            bar_bg = c["sidebar"]
        self.configure(bg=bg)
        self._icon_lbl.configure(bg=bg, fg=fg)
        self._text_lbl.configure(bg=bg, fg=fg, font=("Segoe UI Semibold" if active else "Segoe UI", 10))
        self._bar.configure(bg=bar_bg)


# ─────────────────────────────────────────────────────────────────────────────
# Main Application
# ─────────────────────────────────────────────────────────────────────────────
class FocusLockApp(tk.Tk):

    # ── Init ──────────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        self.cfg   = load_config()
        self.stats = load_stats()

        theme_name = self.cfg.get("theme", "dark")
        self._theme = Theme(theme_name, THEMES[theme_name])

        self._blocker        = None
        self._timer          = None
        self._session_start  = None
        self._locked         = False
        self._paused         = False
        self._mini_win       = None
        self._cur_tab        = None

        # blocklist metadata: exe/domain -> {"name": ..., "enabled": True}
        if not isinstance(self.cfg.get("blocklist_meta"), dict):
            self.cfg["blocklist_meta"] = {}
        if not isinstance(self.cfg.get("site_meta"), dict):
            self.cfg["site_meta"] = {}

        self.title(f"FocusLock  v{VERSION}")
        self.geometry("980x680")
        self.minsize(860, 600)
        self.configure(bg=self._theme.c["bg"])
        self._theme.style_progressbar()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────────────────────────────────────
    # UI Layout
    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        C = self._theme.c

        # ── Root grid: sidebar | content ──────────────────────────────────
        self.columnconfigure(0, weight=0, minsize=210)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ── Sidebar ───────────────────────────────────────────────────────
        sidebar = tk.Frame(self, bg=C["sidebar"], width=210)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.pack_propagate(False)
        sidebar.grid_propagate(False)

        # Logo
        logo_frame = tk.Frame(sidebar, bg=C["sidebar"])
        logo_frame.pack(fill="x", pady=(22, 4))
        tk.Label(
            logo_frame, text="🔒", font=("Segoe UI", 20),
            bg=C["sidebar"], fg=C["accent"],
        ).pack(side="left", padx=(18, 8))
        tk.Label(
            logo_frame, text="FocusLock",
            font=("Segoe UI Semibold", 14), bg=C["sidebar"], fg=C["text"],
        ).pack(side="left")

        tk.Label(
            sidebar, text=f"v{VERSION}",
            font=("Segoe UI", 8), bg=C["sidebar"], fg=C["muted"],
        ).pack(anchor="w", padx=52, pady=(0, 16))

        # Separator
        tk.Frame(sidebar, bg=C["border"], height=1).pack(fill="x", padx=12, pady=(0, 12))

        # Nav items
        self._nav_items = {}
        self._pages     = {}
        nav_defs = [
            ("session",   "⏱",  "Session"),
            ("blocklist", "🚫", "App Blocker"),
            ("websites",  "🌐", "Website Blocker"),
            ("stats",     "📊", "Stats"),
            ("settings",  "⚙️",  "Settings"),
        ]
        for key, icon, text in nav_defs:
            item = NavItem(sidebar, self._theme, icon, text,
                           command=lambda k=key: self._switch_tab(k))
            item.pack(fill="x", padx=4, pady=1)
            self._nav_items[key] = item

        # Bottom: theme toggle
        tk.Frame(sidebar, bg=C["border"], height=1).pack(fill="x", padx=12, side="bottom", pady=(0, 8))
        theme_btn = tk.Button(
            sidebar,
            text="☀  Light mode" if self._theme.name == "dark" else "🌙  Dark mode",
            command=self._toggle_theme,
            bg=C["sidebar"], fg=C["muted"],
            relief="flat", bd=0, font=("Segoe UI", 9),
            cursor="hand2", anchor="w", padx=18, pady=10,
        )
        theme_btn.pack(side="bottom", fill="x")

        # ── Content area ──────────────────────────────────────────────────
        content_wrap = tk.Frame(self, bg=C["bg"])
        content_wrap.grid(row=0, column=1, sticky="nsew")
        content_wrap.columnconfigure(0, weight=1)
        content_wrap.rowconfigure(0, weight=1)

        self._content = tk.Frame(content_wrap, bg=C["bg"])
        self._content.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._content.columnconfigure(0, weight=1)
        self._content.rowconfigure(0, weight=1)

        # Build all pages
        self._build_session()
        self._build_blocklist()
        self._build_websites()
        self._build_stats()
        self._build_settings()

        self._switch_tab("session")

    def _switch_tab(self, key):
        for k, p in self._pages.items():
            p.grid_remove()
        for k, item in self._nav_items.items():
            item.set_active(k == key)
        self._pages[key].grid(row=0, column=0, sticky="nsew")
        self._cur_tab = key

    def _page_frame(self, key):
        f = tk.Frame(self._content, bg=self._theme.c["bg"])
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self._pages[key] = f
        return f

    # ─────────────────────────────────────────────────────────────────────────
    # Page header helper
    # ─────────────────────────────────────────────────────────────────────────
    def _page_header(self, parent, title, subtitle=""):
        C = self._theme.c
        hdr = tk.Frame(parent, bg=C["surface"] if "surface" in C else C["card"])
        hdr.pack(fill="x")
        inner = tk.Frame(hdr, bg=hdr.cget("bg"))
        inner.pack(fill="x", padx=28, pady=18)
        tk.Label(
            inner, text=title,
            font=("Segoe UI Semibold", 16), bg=hdr.cget("bg"), fg=C["text"],
        ).pack(anchor="w")
        if subtitle:
            tk.Label(
                inner, text=subtitle,
                font=("Segoe UI", 9), bg=hdr.cget("bg"), fg=C["subtext"],
            ).pack(anchor="w", pady=(3, 0))
        tk.Frame(parent, bg=C["border"], height=1).pack(fill="x")
        return hdr

    # ─────────────────────────────────────────────────────────────────────────
    # ── SESSION TAB ──────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    def _build_session(self):
        C = self._theme.c
        f = self._page_frame("session")

        # Page header
        self._page_header(
            f,
            "⏱  Focus Session",
            "Start a Pomodoro session to lock out distractions.",
        )

        # Scrollable body
        body = ScrollableFrame(f, self._theme)
        body.pack(fill="both", expand=True)
        inner = body.inner
        inner.configure(bg=C["bg"])
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)

        # ── Left column: timer ────────────────────────────────────────────
        left = tk.Frame(inner, bg=C["bg"])
        left.grid(row=0, column=0, sticky="n", padx=(28, 14), pady=24)

        # Session name
        sname_frame = tk.Frame(left, bg=C["bg"])
        sname_frame.pack(fill="x", pady=(0, 20))
        tk.Label(
            sname_frame, text="Session name  (optional)",
            font=("Segoe UI", 9), bg=C["bg"], fg=C["subtext"],
        ).pack(anchor="w", pady=(0, 5))
        self._sname = tk.StringVar(value=self.cfg.get("session_name", ""))
        ef, _ = entry(sname_frame, self._theme, textvariable=self._sname,
                      placeholder="e.g. Chapter 5 — Calculus", width=32)
        ef.pack(fill="x")

        # Phase label
        self._phase_lbl = tk.Label(
            left, text="FOCUS TIME",
            font=("Segoe UI Semibold", 11), bg=C["bg"], fg=C["accent"],
        )
        self._phase_lbl.pack()

        # Circular timer
        timer_wrap = tk.Frame(left, bg=C["bg"])
        timer_wrap.pack(pady=12)
        self._circ = CircularTimer(timer_wrap, self._theme, size=230)
        self._circ.pack()

        # Time label overlaid on canvas
        work, brk = PRESETS.get(self.cfg.get("last_preset", "Classic (25/5)"), (25, 5))
        self._timer_text = tk.Label(
            timer_wrap,
            text=f"{work:02d}:00",
            font=("Courier New", 38, "bold"),
            bg=C["timer_bg"], fg=C["text"],
        )
        self._timer_text.place(relx=0.5, rely=0.5, anchor="center")

        # Cycle label
        self._cycle_lbl = tk.Label(
            left, text="No cycles yet",
            font=("Segoe UI", 9), bg=C["bg"], fg=C["muted"],
        )
        self._cycle_lbl.pack()

        # Control buttons
        ctrl = tk.Frame(left, bg=C["bg"])
        ctrl.pack(pady=16)

        self._start_btn = button(
            ctrl, self._theme, "🔒   START SESSION",
            command=self._toggle_session, variant="primary",
            font=("Segoe UI Semibold", 11), padx=20, pady=10,
        )
        self._start_btn.pack(side="left")

        self._pause_btn = button(
            ctrl, self._theme, "⏸  Pause",
            command=self._pause_resume, variant="secondary",
            font=("Segoe UI", 10), padx=14, pady=10,
            state="disabled",
        )
        self._pause_btn.pack(side="left", padx=(8, 0))

        button(
            ctrl, self._theme, "↺  Reset",
            command=self._reset_timer, variant="secondary",
            font=("Segoe UI", 10), padx=14, pady=10,
        ).pack(side="left", padx=(8, 0))

        # Status
        self._status = tk.Label(
            left, text="Ready — pick a preset and start your session.",
            font=("Segoe UI", 9), bg=C["bg"], fg=C["subtext"],
            wraplength=320, justify="center",
        )
        self._status.pack(pady=(0, 8))

        # ── Right column: presets + options ───────────────────────────────
        right = tk.Frame(inner, bg=C["bg"])
        right.grid(row=0, column=1, sticky="n", padx=(14, 28), pady=24)

        # Presets
        tk.Label(
            right, text="Preset",
            font=("Segoe UI Semibold", 11), bg=C["bg"], fg=C["text"],
        ).pack(anchor="w", pady=(0, 10))

        self._preset_var = tk.StringVar(value=self.cfg.get("last_preset", "Classic (25/5)"))
        self._preset_btns = {}
        for preset_name, (w_min, b_min) in PRESETS.items():
            pb = tk.Frame(right, bg=C["card"])
            pb.pack(fill="x", pady=4)

            rb_var = self._preset_var
            _is_sel = (preset_name == self._preset_var.get())

            btn_frame = tk.Frame(pb, bg=C["accent"] if _is_sel else C["card"], width=4)
            btn_frame.pack(side="left", fill="y")

            info = tk.Frame(pb, bg=C["card"])
            info.pack(side="left", fill="x", expand=True, padx=12, pady=10)
            tk.Label(
                info, text=preset_name,
                font=("Segoe UI Semibold", 10), bg=C["card"],
                fg=C["text"] if _is_sel else C["subtext"],
            ).pack(anchor="w")
            tk.Label(
                info, text=f"{w_min} min focus  ·  {b_min} min break",
                font=("Segoe UI", 8), bg=C["card"], fg=C["muted"],
            ).pack(anchor="w")

            def _make_sel(name, frame, bar_frame, info_frame):
                def _select():
                    if self._locked:
                        return
                    self._preset_var.set(name)
                    self._apply_preset()
                    # Update visual state of all preset cards
                    for n, (f_card, f_bar, f_info) in self._preset_btns.items():
                        is_now = (n == name)
                        f_bar.configure(bg=C["accent"] if is_now else C["card"])
                        for child in f_info.winfo_children():
                            try:
                                current_font = child.cget("font")
                                if "Semibold" in str(current_font):
                                    child.configure(fg=C["text"] if is_now else C["subtext"])
                            except Exception:
                                pass
                return _select

            sel_cmd = _make_sel(preset_name, pb, btn_frame, info)
            for w in (pb, btn_frame, info):
                w.bind("<Button-1>", lambda _e, cmd=sel_cmd: cmd())
                w.configure(cursor="hand2")
            for child in info.winfo_children():
                child.bind("<Button-1>", lambda _e, cmd=sel_cmd: cmd())
                child.configure(cursor="hand2")

            self._preset_btns[preset_name] = (pb, btn_frame, info)

        # ── Custom duration ───────────────────────────────────────────────
        tk.Frame(right, bg=C["border"], height=1).pack(fill="x", pady=14)
        tk.Label(
            right, text="Custom duration",
            font=("Segoe UI Semibold", 11), bg=C["bg"], fg=C["text"],
        ).pack(anchor="w", pady=(0, 8))

        custom_row = tk.Frame(right, bg=C["bg"])
        custom_row.pack(fill="x")

        def _mini_entry(parent, label_text, var):
            col = tk.Frame(parent, bg=C["bg"])
            tk.Label(col, text=label_text, font=("Segoe UI", 8), bg=C["bg"], fg=C["subtext"]).pack(anchor="w")
            ef, ew = entry(col, self._theme, textvariable=var, width=6)
            ef.pack(anchor="w")
            return col

        self._custom_work = tk.StringVar(value="25")
        self._custom_break = tk.StringVar(value="5")

        _mini_entry(custom_row, "Work (min)", self._custom_work).pack(side="left")
        tk.Label(custom_row, text=":", font=("Segoe UI", 18, "bold"),
                 bg=C["bg"], fg=C["muted"]).pack(side="left", padx=8, pady=(14, 0))
        _mini_entry(custom_row, "Break (min)", self._custom_break).pack(side="left")

        button(
            right, self._theme, "Apply Custom",
            command=self._apply_custom, variant="secondary",
            font=("Segoe UI", 9), padx=10, pady=6,
        ).pack(anchor="w", pady=(10, 0))

        # ── Website blocker toggle ────────────────────────────────────────
        tk.Frame(right, bg=C["border"], height=1).pack(fill="x", pady=14)

        self._web_var = tk.BooleanVar(value=self.cfg.get("block_websites", False))
        web_row = tk.Frame(right, bg=C["card"])
        web_row.pack(fill="x", pady=2)
        tk.Label(
            web_row, text="🌐  Block websites during session",
            font=("Segoe UI", 10), bg=C["card"], fg=C["text"],
        ).pack(side="left", padx=12, pady=12)
        toggle_button(web_row, self._theme, self._web_var,
                      command=self._save_cfg).pack(side="right", padx=12, pady=12)

        self._notif_var2 = tk.BooleanVar(value=self.cfg.get("notify_break", True))
        notif_row = tk.Frame(right, bg=C["card"])
        notif_row.pack(fill="x", pady=2)
        tk.Label(
            notif_row, text="🔔  Break notifications",
            font=("Segoe UI", 10), bg=C["card"], fg=C["text"],
        ).pack(side="left", padx=12, pady=12)
        toggle_button(notif_row, self._theme, self._notif_var2,
                      command=self._save_cfg).pack(side="right", padx=12, pady=12)

    # ─────────────────────────────────────────────────────────────────────────
    # ── BLOCKLIST TAB ────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    def _build_blocklist(self):
        C = self._theme.c
        f = self._page_frame("blocklist")

        self._page_header(
            f,
            "🚫  App Blocker",
            "These apps are force-killed every 2 seconds while a session is active.",
        )

        # Toolbar
        toolbar = tk.Frame(f, bg=C["bg"])
        toolbar.pack(fill="x", padx=24, pady=14)

        button(
            toolbar, self._theme, "＋  Add Application",
            command=self._open_app_picker, variant="primary",
            font=("Segoe UI Semibold", 10), padx=16, pady=8,
        ).pack(side="left")

        button(
            toolbar, self._theme, "↺  Reset to defaults",
            command=self._reset_app_defaults, variant="secondary",
            font=("Segoe UI", 9), padx=12, pady=8,
        ).pack(side="right")

        # Count label
        self._app_count_lbl = tk.Label(
            toolbar, text="", font=("Segoe UI", 9),
            bg=C["bg"], fg=C["subtext"],
        )
        self._app_count_lbl.pack(side="left", padx=12)

        # Search bar
        search_bar = tk.Frame(f, bg=C["bg"])
        search_bar.pack(fill="x", padx=24, pady=(0, 10))
        self._app_cards = {}
        self._app_names = {}
        self._app_search = tk.StringVar()
        self._app_search.trace_add("write", lambda *_: self._filter_app_cards())
        sf, _ = entry(search_bar, self._theme, textvariable=self._app_search,
                      placeholder="Search apps…", width=40)
        sf.pack(side="left")

        # Card list
        self._app_scroll = ScrollableFrame(f, self._theme)
        self._app_scroll.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        self._app_cards = {}  # identifier -> card widget
        self._app_names = {}  # identifier -> display name
        self._rebuild_app_cards()

    def _rebuild_app_cards(self):
        """Re-render all app blocklist cards from config."""
        for w in self._app_scroll.inner.winfo_children():
            w.destroy()
        self._app_cards.clear()
        self._app_names.clear()

        meta = self.cfg.get("blocklist_meta", {})
        for exe in self.cfg.get("blocklist", []):
            exe_lower = exe.lower()
            m = meta.get(exe_lower, {})
            name = m.get("name") or exe_lower.replace(".exe", "").title()
            enabled = m.get("enabled", True)
            self._add_app_card(exe_lower, name, enabled)
        self._update_app_count()

    def _add_app_card(self, exe, name, enabled=True):
        card = blocklist_item_card(
            self._app_scroll.inner, self._theme,
            name=name, identifier=exe, item_type="app",
            enabled=enabled,
            on_remove=self._remove_app,
            on_toggle=self._toggle_app_enabled,
        )
        card.pack(fill="x", pady=1)
        self._app_cards[exe] = card
        self._app_names[exe] = name
        self._update_app_count()

    def _filter_app_cards(self):
        if not hasattr(self, "_app_cards"):
            return
        query = self._app_search.get().strip().lower()
        if query in ("search apps…", ""):
            query = ""
        for exe, card in list(self._app_cards.items()):
            name = self._app_names.get(exe, exe)
            visible = (not query) or (query in exe) or (query in name.lower())
            if visible:
                card.pack(fill="x", pady=1)
            else:
                card.pack_forget()

    def _update_app_count(self):
        n = len(self.cfg.get("blocklist", []))
        self._app_count_lbl.configure(text=f"{n} app{'s' if n != 1 else ''} blocked")

    def _open_app_picker(self):
        AppPickerDialog(
            self, self._theme,
            existing=self.cfg.get("blocklist", []),
            on_add=self._on_app_added,
        )

    def _on_app_added(self, exe, display, source):
        exe = exe.lower()
        if exe not in self.cfg["blocklist"]:
            self.cfg["blocklist"].append(exe)
        if not isinstance(self.cfg.get("blocklist_meta"), dict):
            self.cfg["blocklist_meta"] = {}
        self.cfg["blocklist_meta"][exe] = {"name": display, "enabled": True}
        save_config(self.cfg)
        self._add_app_card(exe, display, True)
        self._app_scroll.scroll_to_bottom()

    def _remove_app(self, exe):
        if exe in self.cfg["blocklist"]:
            self.cfg["blocklist"].remove(exe)
        self.cfg.get("blocklist_meta", {}).pop(exe, None)
        self._app_cards.pop(exe, None)
        self._app_names.pop(exe, None)
        save_config(self.cfg)
        self._update_app_count()

    def _toggle_app_enabled(self, exe, enabled):
        if not isinstance(self.cfg.get("blocklist_meta"), dict):
            self.cfg["blocklist_meta"] = {}
        m = self.cfg["blocklist_meta"].setdefault(exe, {})
        m["enabled"] = enabled
        save_config(self.cfg)

    def _reset_app_defaults(self):
        from focuslock.constants import DEFAULT_APPS
        if messagebox.askyesno(
            "Reset to defaults",
            "Replace your app blocklist with the default apps?\nThis cannot be undone.",
            parent=self,
        ):
            self.cfg["blocklist"] = DEFAULT_APPS[:]
            self.cfg["blocklist_meta"] = {}
            save_config(self.cfg)
            self._rebuild_app_cards()

    # ─────────────────────────────────────────────────────────────────────────
    # ── WEBSITES TAB ─────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    def _build_websites(self):
        C = self._theme.c
        f = self._page_frame("websites")

        self._page_header(
            f,
            "🌐  Website Blocker",
            "Blocks domains via the hosts file — requires Administrator privileges.",
        )

        # Admin warning banner
        warn = tk.Frame(f, bg=C["warn"])
        warn.pack(fill="x", padx=24, pady=(12, 0))
        tk.Label(
            warn,
            text="  ⚠   Requires  Run as Administrator  to edit the hosts file.",
            font=("Segoe UI", 9, "bold"),
            bg=C["warn"], fg="#1a1208", pady=8, padx=8,
        ).pack(anchor="w")

        # Toolbar
        toolbar = tk.Frame(f, bg=C["bg"])
        toolbar.pack(fill="x", padx=24, pady=14)

        button(
            toolbar, self._theme, "＋  Add Website",
            command=self._open_site_picker, variant="primary",
            font=("Segoe UI Semibold", 10), padx=16, pady=8,
        ).pack(side="left")

        button(
            toolbar, self._theme, "↺  Reset to defaults",
            command=self._reset_site_defaults, variant="secondary",
            font=("Segoe UI", 9), padx=12, pady=8,
        ).pack(side="right")

        self._site_count_lbl = tk.Label(
            toolbar, text="", font=("Segoe UI", 9),
            bg=C["bg"], fg=C["subtext"],
        )
        self._site_count_lbl.pack(side="left", padx=12)

        # Search
        search_bar = tk.Frame(f, bg=C["bg"])
        search_bar.pack(fill="x", padx=24, pady=(0, 10))
        self._site_cards = {}
        self._site_search = tk.StringVar()
        self._site_search.trace_add("write", lambda *_: self._filter_site_cards())
        sf, _ = entry(search_bar, self._theme, textvariable=self._site_search,
                      placeholder="Search websites…", width=40)
        sf.pack(side="left")

        # Card list
        self._site_scroll = ScrollableFrame(f, self._theme)
        self._site_scroll.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        self._site_cards = {}
        self._rebuild_site_cards()

    def _rebuild_site_cards(self):
        for w in self._site_scroll.inner.winfo_children():
            w.destroy()
        self._site_cards.clear()

        meta = self.cfg.get("site_meta", {})
        for domain in self.cfg.get("website_blocklist", []):
            m = meta.get(domain, {})
            enabled = m.get("enabled", True)
            self._add_site_card(domain, enabled)
        self._update_site_count()

    def _add_site_card(self, domain, enabled=True):
        card = blocklist_item_card(
            self._site_scroll.inner, self._theme,
            name=domain, identifier=domain, item_type="site",
            enabled=enabled,
            on_remove=self._remove_site,
            on_toggle=self._toggle_site_enabled,
        )
        card.pack(fill="x", pady=1)
        self._site_cards[domain] = card
        self._update_site_count()

    def _filter_site_cards(self):
        if not hasattr(self, "_site_cards"):
            return
        query = self._site_search.get().strip().lower()
        if query in ("search websites…", ""):
            query = ""
        for domain, card in list(self._site_cards.items()):
            visible = (not query) or (query in domain)
            if visible:
                card.pack(fill="x", pady=1)
            else:
                card.pack_forget()

    def _update_site_count(self):
        n = len(self.cfg.get("website_blocklist", []))
        self._site_count_lbl.configure(text=f"{n} site{'s' if n != 1 else ''} blocked")

    def _open_site_picker(self):
        SitePickerDialog(
            self, self._theme,
            existing=self.cfg.get("website_blocklist", []),
            on_add=self._on_site_added,
        )

    def _on_site_added(self, domain):
        if domain not in self.cfg["website_blocklist"]:
            self.cfg["website_blocklist"].append(domain)
        if not isinstance(self.cfg.get("site_meta"), dict):
            self.cfg["site_meta"] = {}
        self.cfg["site_meta"][domain] = {"enabled": True}
        save_config(self.cfg)
        self._add_site_card(domain, True)
        self._site_scroll.scroll_to_bottom()

    def _remove_site(self, domain):
        bl = self.cfg.get("website_blocklist", [])
        if domain in bl:
            bl.remove(domain)
        self.cfg.get("site_meta", {}).pop(domain, None)
        self._site_cards.pop(domain, None)
        save_config(self.cfg)
        self._update_site_count()

    def _toggle_site_enabled(self, domain, enabled):
        if not isinstance(self.cfg.get("site_meta"), dict):
            self.cfg["site_meta"] = {}
        self.cfg["site_meta"].setdefault(domain, {})["enabled"] = enabled
        save_config(self.cfg)

    def _reset_site_defaults(self):
        from focuslock.constants import DEFAULT_SITES
        if messagebox.askyesno(
            "Reset to defaults",
            "Replace your website blocklist with the defaults?",
            parent=self,
        ):
            self.cfg["website_blocklist"] = DEFAULT_SITES[:]
            self.cfg["site_meta"] = {}
            save_config(self.cfg)
            self._rebuild_site_cards()

    # ─────────────────────────────────────────────────────────────────────────
    # ── STATS TAB ────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    def _build_stats(self):
        C = self._theme.c
        f = self._page_frame("stats")

        self._page_header(
            f,
            "📊  Study Stats",
            "Your focus session history and streaks.",
        )

        body = ScrollableFrame(f, self._theme)
        body.pack(fill="both", expand=True)
        inner = body.inner
        inner.configure(bg=C["bg"])
        inner.columnconfigure(0, weight=1)
        inner.columnconfigure(1, weight=1)

        s = self.stats
        h, m = s["total_minutes"] // 60, s["total_minutes"] % 60

        # Stat cards (2×2 grid)
        cards_data = [
            ("📅", "Total Sessions",  str(s["total_sessions"]),   C["accent"],   0, 0),
            ("⏱",  "Total Focus Time", f"{h}h {m}m",             C["success"],  0, 1),
            ("🔥", "Current Streak",   f"{s['current_streak']} days", C["warn"], 1, 0),
            ("🏆", "Longest Streak",   f"{s['longest_streak']} days", C["accent2"], 1, 1),
        ]
        for icon, title, value, color, row, col in cards_data:
            card = stat_card(inner, self._theme, icon, title, value, color)
            card.grid(row=row, column=col, sticky="ew", padx=10, pady=6)

        # 7-day bar chart
        tk.Frame(inner, bg=C["border"], height=1).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=16,
        )
        tk.Label(
            inner, text="Last 7 days",
            font=("Segoe UI Semibold", 11), bg=C["bg"], fg=C["text"],
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))

        # Build 7-day data
        sessions_by_date = s.get("sessions_by_date", {})
        today = datetime.date.today()
        days = [(today - datetime.timedelta(days=i)) for i in range(6, -1, -1)]
        day_values = [sessions_by_date.get(d.isoformat(), 0) for d in days]
        day_labels = [d.strftime("%a") for d in days]

        chart_frame = tk.Frame(inner, bg=C["card"])
        chart_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))
        chart = BarChart(chart_frame, self._theme, day_values, day_labels, height=120)
        chart.pack(fill="x", padx=12, pady=10)

        # Last session
        if s.get("last_session_date"):
            tk.Label(
                inner,
                text=f"Last session:  {s['last_session_date']}",
                font=("Segoe UI", 9), bg=C["bg"], fg=C["subtext"],
            ).grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 4))

        # Reset button
        button(
            inner, self._theme, "🗑  Reset all stats",
            command=self._reset_stats, variant="danger",
            font=("Segoe UI", 9), padx=12, pady=6,
        ).grid(row=6, column=1, sticky="e", padx=14, pady=12)

    # ─────────────────────────────────────────────────────────────────────────
    # ── SETTINGS TAB ─────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    def _build_settings(self):
        C = self._theme.c
        f = self._page_frame("settings")

        self._page_header(
            f,
            "⚙️  Settings",
            "Customize FocusLock to fit your workflow.",
        )

        body = ScrollableFrame(f, self._theme)
        body.pack(fill="both", expand=True)
        inner = body.inner
        inner.configure(bg=C["bg"])

        def section(title):
            tk.Label(
                inner, text=title,
                font=("Segoe UI Semibold", 10), bg=C["bg"], fg=C["muted"],
            ).pack(anchor="w", padx=28, pady=(20, 6))

        def setting_row(icon_text, description=None):
            row = tk.Frame(inner, bg=C["card"])
            row.pack(fill="x", padx=24, pady=2)
            left = tk.Frame(row, bg=C["card"])
            left.pack(side="left", fill="x", expand=True, padx=12, pady=12)
            tk.Label(
                left, text=icon_text,
                font=("Segoe UI", 10), bg=C["card"], fg=C["text"],
            ).pack(anchor="w")
            if description:
                tk.Label(
                    left, text=description,
                    font=("Segoe UI", 8), bg=C["card"], fg=C["subtext"],
                ).pack(anchor="w", pady=(2, 0))
            return row

        # ── System ───────────────────────────────────────────────────────
        section("SYSTEM")

        self._startup_var = tk.BooleanVar(value=startup_is_on())
        r = setting_row("🚀  Launch with Windows",
                        "Start FocusLock automatically at login.")
        toggle_button(r, self._theme, self._startup_var,
                      command=self._do_startup).pack(side="right", padx=12, pady=12)

        self._tray_var = tk.BooleanVar(value=self.cfg.get("minimize_to_tray", True))
        r = setting_row("🗕  Minimize to tray on close",
                        "Shows a floating restore bar instead of quitting.")
        toggle_button(r, self._theme, self._tray_var,
                      command=self._save_cfg).pack(side="right", padx=12, pady=12)

        # ── Session ───────────────────────────────────────────────────────
        section("SESSION")

        self._notif_var = tk.BooleanVar(value=self.cfg.get("notify_break", True))
        r = setting_row("🔔  Break notifications",
                        "Get a Windows notification when a phase ends.")
        toggle_button(r, self._theme, self._notif_var,
                      command=self._save_cfg).pack(side="right", padx=12, pady=12)

        # ── Security ──────────────────────────────────────────────────────
        section("SECURITY")

        # Session password
        r = setting_row("🔑  Session stop password",
                        "Require a password to stop an active session.")
        has_pw = bool(self.cfg.get("password_hash"))
        self._pw_status = tk.Label(
            r, text="✓ Set" if has_pw else "Not set",
            font=("Segoe UI", 9), bg=C["card"],
            fg=C["success"] if has_pw else C["subtext"],
        )
        self._pw_status.pack(side="right", padx=6)
        button(
            r, self._theme,
            "Change" if has_pw else "Set",
            command=lambda: self._change_pw("password_hash"),
            variant="secondary", font=("Segoe UI", 9), padx=10, pady=5,
        ).pack(side="right", padx=6)

        # Parent password
        r = setting_row("👨‍👧  Parent / override password",
                        "Overrides the session password — share with a trusted person.")
        has_ppw = bool(self.cfg.get("parent_password_hash"))
        self._ppw_status = tk.Label(
            r, text="✓ Set" if has_ppw else "Not set",
            font=("Segoe UI", 9), bg=C["card"],
            fg=C["success"] if has_ppw else C["subtext"],
        )
        self._ppw_status.pack(side="right", padx=6)
        button(
            r, self._theme,
            "Change" if has_ppw else "Set",
            command=lambda: self._change_pw("parent_password_hash"),
            variant="secondary", font=("Segoe UI", 9), padx=10, pady=5,
        ).pack(side="right", padx=6)

        # ── About ─────────────────────────────────────────────────────────
        section("ABOUT")
        about = tk.Frame(inner, bg=C["card"])
        about.pack(fill="x", padx=24, pady=2)
        tk.Label(
            about,
            text=f"FocusLock  v{VERSION}   ·   by zadwen   ·   github.com/zadwen/FocusLock",
            font=("Segoe UI", 9), bg=C["card"], fg=C["subtext"],
        ).pack(padx=12, pady=14)

    # ─────────────────────────────────────────────────────────────────────────
    # ── Session logic ────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    def _toggle_session(self):
        if not self._locked:
            self._start_session()
        else:
            self._stop_session()

    def _start_session(self):
        C = self._theme.c
        preset_key = self._preset_var.get()
        work, brk = PRESETS.get(preset_key, (25, 5))

        self.cfg["last_preset"] = preset_key
        self.cfg["session_name"] = self._sname.get()
        save_config(self.cfg)

        self._timer = PomodoroTimer(
            work, brk,
            on_tick=self._on_tick,
            on_phase=self._on_phase,
        )
        self._circ.set_value(work * 60, work * 60, "work")

        # Only block enabled apps
        enabled_apps = [
            exe for exe in self.cfg.get("blocklist", [])
            if self.cfg.get("blocklist_meta", {}).get(exe, {}).get("enabled", True)
        ]
        self._blocker = AppBlocker(enabled_apps)
        self._blocker.start()

        # Website blocking
        if self._web_var.get():
            enabled_sites = [
                d for d in self.cfg.get("website_blocklist", [])
                if self.cfg.get("site_meta", {}).get(d, {}).get("enabled", True)
            ]
            if not block_sites(enabled_sites):
                messagebox.showwarning(
                    "Administrator required",
                    "Website blocking requires running FocusLock as Administrator.\n"
                    "Right-click the app → Run as Administrator.",
                    parent=self,
                )

        self._timer.start()
        self._locked = True
        self._paused = False
        self._session_start = datetime.datetime.now()

        self._start_btn.configure(
            text="🔓   STOP SESSION", bg=C["accent2"],
            activebackground="#cc3355",
        )
        self._pause_btn.configure(state="normal")
        self._status.configure(
            text="🔒  Session active — stay focused!",
            fg=C["success"],
        )
        self._phase_lbl.configure(text="FOCUS TIME", fg=C["accent"])

    def _stop_session(self):
        # Password check
        if self.cfg.get("password_hash") or self.cfg.get("parent_password_hash"):
            pw = simpledialog.askstring(
                "🔑  Unlock Session",
                "Enter password to stop:",
                show="*", parent=self,
            )
            if not pw:
                return
            h = hash_pw(pw)
            if h != self.cfg.get("password_hash") and h != self.cfg.get("parent_password_hash"):
                messagebox.showerror("Wrong password", "Incorrect password. Stay focused! 💪", parent=self)
                return

        C = self._theme.c
        if self._timer:
            self._timer.pause()
        if self._blocker:
            self._blocker.stop()
        unblock_sites()

        self._locked = False
        self._paused = False
        self._start_btn.configure(
            text="🔒   START SESSION", bg=C["accent"],
            activebackground=C["accent_hover"],
        )
        self._pause_btn.configure(state="disabled", text="⏸  Pause")
        self._status.configure(
            text="Session ended — great work! 🎉",
            fg=C["success"],
        )
        self._record_session()

    def _pause_resume(self):
        if not self._locked or not self._timer:
            return
        if not self._paused:
            self._timer.pause()
            if self._blocker:
                self._blocker.stop()
            self._paused = True
            self._pause_btn.configure(text="▶  Resume")
            self._status.configure(text="⏸  Paused.", fg=self._theme.c["warn"])
        else:
            self._timer.start()
            enabled_apps = [
                exe for exe in self.cfg.get("blocklist", [])
                if self.cfg.get("blocklist_meta", {}).get(exe, {}).get("enabled", True)
            ]
            self._blocker = AppBlocker(enabled_apps)
            self._blocker.start()
            self._paused = False
            self._pause_btn.configure(text="⏸  Pause")
            self._status.configure(text="🔒  Back to focus.", fg=self._theme.c["success"])

    def _reset_timer(self):
        if self._locked:
            messagebox.showinfo("Active", "Stop the session first.", parent=self)
            return
        preset_key = self._preset_var.get()
        work, _ = PRESETS.get(preset_key, (25, 5))
        if self._timer:
            self._timer.reset()
        self._timer_text.configure(text=f"{work:02d}:00")
        self._phase_lbl.configure(text="FOCUS TIME", fg=self._theme.c["accent"])
        self._cycle_lbl.configure(text="No cycles yet")
        self._circ.set_value(work * 60, work * 60, "work")

    def _apply_preset(self):
        if self._locked:
            return
        preset_key = self._preset_var.get()
        work, brk = PRESETS.get(preset_key, (25, 5))
        self.cfg["pomodoro_work"] = work
        self.cfg["pomodoro_break"] = brk
        self.cfg["last_preset"] = preset_key
        save_config(self.cfg)
        self._timer_text.configure(text=f"{work:02d}:00")
        self._circ.set_value(work * 60, work * 60, "work")

    def _apply_custom(self):
        if self._locked:
            messagebox.showinfo("Active", "Stop the session first.", parent=self)
            return
        try:
            w = int(self._custom_work.get())
            b = int(self._custom_break.get())
            assert 1 <= w <= 240 and 1 <= b <= 60
        except (ValueError, AssertionError):
            messagebox.showerror(
                "Invalid",
                "Work: 1–240 min  |  Break: 1–60 min",
                parent=self,
            )
            return
        self.cfg["pomodoro_work"] = w
        self.cfg["pomodoro_break"] = b
        save_config(self.cfg)
        self._timer_text.configure(text=f"{w:02d}:00")
        self._circ.set_value(w * 60, w * 60, "work")
        self._status.configure(
            text=f"Custom: {w} min focus / {b} min break.",
            fg=self._theme.c["subtext"],
        )

    # ── Timer callbacks ───────────────────────────────────────────────────────
    def _on_tick(self, remaining, phase):
        self.after(0, self._draw_tick, remaining, phase)

    def _draw_tick(self, remaining, phase):
        m, s = divmod(remaining, 60)
        self._timer_text.configure(text=f"{m:02d}:{s:02d}")
        total = (self.cfg["pomodoro_work"] if phase == "work" else self.cfg["pomodoro_break"]) * 60
        self._circ.set_value(remaining, total, phase)

    def _on_phase(self, phase, cycles):
        self.after(0, self._draw_phase, phase, cycles)

    def _draw_phase(self, phase, cycles):
        C = self._theme.c
        if phase == "work":
            self._phase_lbl.configure(text="FOCUS TIME", fg=C["accent"])
            if self.cfg.get("notify_break"):
                notify("FocusLock", "Break over — back to work! 💪")
        else:
            self._phase_lbl.configure(text="☕  BREAK TIME", fg=C["success"])
            if self.cfg.get("notify_break"):
                notify("FocusLock", f"Nice work! Take a break. ({cycles} cycles done)")
        self._cycle_lbl.configure(
            text=f"{cycles} cycle{'s' if cycles != 1 else ''} complete"
        )
        self.bell()

    # ── Stats recording ───────────────────────────────────────────────────────
    def _record_session(self):
        if not self._session_start:
            return
        mins = max(1, (datetime.datetime.now() - self._session_start).seconds // 60)
        today = datetime.date.today().isoformat()
        self.stats["total_sessions"] += 1
        self.stats["total_minutes"] += mins
        self.stats["sessions_by_date"][today] = (
            self.stats["sessions_by_date"].get(today, 0) + 1
        )
        last = self.stats.get("last_session_date", "")
        if last:
            try:
                diff = (datetime.date.today() - datetime.date.fromisoformat(last)).days
                if diff == 1:
                    self.stats["current_streak"] += 1
                elif diff > 1:
                    self.stats["current_streak"] = 1
            except Exception:
                self.stats["current_streak"] = 1
        else:
            self.stats["current_streak"] = 1
        self.stats["longest_streak"] = max(
            self.stats["longest_streak"], self.stats["current_streak"]
        )
        self.stats["last_session_date"] = today
        save_stats(self.stats)
        self._session_start = None

    def _reset_stats(self):
        from focuslock.config import default_stats
        if messagebox.askyesno(
            "Reset stats",
            "Clear all study stats? This cannot be undone.",
            parent=self,
        ):
            self.stats = default_stats()
            save_stats(self.stats)
            messagebox.showinfo("Done", "Stats have been reset.", parent=self)

    # ── Settings helpers ──────────────────────────────────────────────────────
    def _do_startup(self):
        if not set_startup(self._startup_var.get()):
            messagebox.showwarning(
                "Error",
                "Couldn't update startup. Try running as Administrator.",
                parent=self,
            )
        self._save_cfg()

    def _save_cfg(self):
        self.cfg["block_websites"]   = self._web_var.get()
        self.cfg["notify_break"]     = self._notif_var.get()
        self.cfg["minimize_to_tray"] = self._tray_var.get()
        save_config(self.cfg)

    def _change_pw(self, key):
        pw = simpledialog.askstring(
            "Set password",
            "New password  (leave blank to remove):",
            show="*", parent=self,
        )
        if pw is None:
            return
        self.cfg[key] = hash_pw(pw) if pw else ""
        save_config(self.cfg)
        messagebox.showinfo(
            "Saved",
            "Password updated!" if pw else "Password removed.",
            parent=self,
        )

    def _toggle_theme(self):
        self.cfg["theme"] = "light" if self._theme.name == "dark" else "dark"
        save_config(self.cfg)
        messagebox.showinfo(
            "Theme changed",
            "Restart FocusLock to apply the new theme.",
            parent=self,
        )

    # ── Window management ─────────────────────────────────────────────────────
    def _on_close(self):
        if self._locked:
            messagebox.showwarning(
                "Session active",
                "Stop the session before closing FocusLock.",
                parent=self,
            )
            return
        if self._tray_var.get():
            self._minimize_to_tray()
        else:
            self._quit()

    def _minimize_to_tray(self):
        self.withdraw()
        if self._mini_win and self._mini_win.winfo_exists():
            return

        C = self._theme.c
        w = tk.Toplevel(self)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.92)
        w.configure(bg=C["accent"])

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w.geometry(f"200x40+{sw - 216}+{sh - 72}")

        def restore():
            self._mini_win = None
            w.destroy()
            self.deiconify()
            self.lift()
            self.focus_force()

        def quit_app():
            self._mini_win = None
            w.destroy()
            self._quit()

        tk.Button(
            w, text="🔒  FocusLock", command=restore,
            bg=C["accent"], fg="white", relief="flat",
            font=("Segoe UI Semibold", 9), cursor="hand2", bd=0,
        ).pack(side="left", padx=12, pady=6)
        tk.Button(
            w, text="✕", command=quit_app,
            bg=C["accent"], fg="white", relief="flat",
            font=("Segoe UI", 11, "bold"), cursor="hand2", bd=0,
        ).pack(side="right", padx=8)

        self._mini_win = w

    def _quit(self):
        if self._blocker:
            self._blocker.stop()
        unblock_sites()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = FocusLockApp()
    app.mainloop()
