"""
FocusLock v1.2.0
by zadwen — github.com/zadwen/FocusLock
"""

import sys, os, json, time, threading, hashlib, datetime, ctypes, winreg
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

# ── completely suppress CMD windows for ALL subprocesses ──────────────────────
# We patch subprocess at import time so nothing can ever flash a window
import subprocess as _subprocess

_ORIG_POPEN = _subprocess.Popen
_NW = 0x08000000  # CREATE_NO_WINDOW flag

class _PatchedPopen(_ORIG_POPEN):
    def __init__(self, *a, **kw):
        kw.setdefault("creationflags", 0)
        kw["creationflags"] |= _NW
        kw.setdefault("stdout", _subprocess.DEVNULL)
        kw.setdefault("stderr", _subprocess.DEVNULL)
        super().__init__(*a, **kw)

_subprocess.Popen = _PatchedPopen
import subprocess  # re-import so the rest of file uses patched version

# ── also hide own console window immediately ───────────────────────────────────
try:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
APP_NAME = "FocusLock"
VERSION  = "1.2.0"

DATA_DIR    = Path(os.getenv("APPDATA", ".")) / "FocusLock"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"
STATS_FILE  = DATA_DIR / "stats.json"

DEFAULT_APPS = [
    "steam.exe", "steamwebhelper.exe", "discord.exe",
    "EpicGamesLauncher.exe", "Battle.net.exe",
    "LeagueClient.exe", "TwitchUI.exe", "Spotify.exe",
]

DEFAULT_SITES = [
    "youtube.com", "twitter.com", "reddit.com",
    "twitch.tv", "instagram.com", "tiktok.com", "facebook.com",
]

PRESETS = {
    "Classic (25/5)":     (25, 5),
    "Long Focus (50/10)": (50, 10),
    "Short Burst (15/3)": (15, 3),
    "Deep Work (90/20)":  (90, 20),
}

# ─────────────────────────────────────────────────────────────────────────────
# Config / Stats
# ─────────────────────────────────────────────────────────────────────────────
def load_config():
    d = {
        "blocklist": DEFAULT_APPS[:],
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
    }
    if CONFIG_FILE.exists():
        try:
            d.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    return d

def save_config(c): CONFIG_FILE.write_text(json.dumps(c, indent=2))

def load_stats():
    d = {"total_sessions":0,"total_minutes":0,"sessions_by_date":{},
         "current_streak":0,"longest_streak":0,"last_session_date":""}
    if STATS_FILE.exists():
        try: d.update(json.loads(STATS_FILE.read_text()))
        except Exception: pass
    return d

def save_stats(s): STATS_FILE.write_text(json.dumps(s, indent=2))
def hash_pw(pw):   return hashlib.sha256(pw.encode()).hexdigest()

# ─────────────────────────────────────────────────────────────────────────────
# Windows startup registry
# ─────────────────────────────────────────────────────────────────────────────
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def set_startup(enable):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            path = sys.executable if getattr(sys,"frozen",False) else f'pythonw "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, path)
        else:
            try: winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError: pass
        winreg.CloseKey(k)
        return True
    except Exception as e:
        print("registry error:", e)
        return False

def startup_is_on():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(k, APP_NAME)
        winreg.CloseKey(k)
        return True
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# App Blocker  (no CMD window — patched Popen above handles it)
# ─────────────────────────────────────────────────────────────────────────────
class AppBlocker:
    def __init__(self, blocklist):
        self.blocklist = [b.lower() for b in blocklist]
        self._on = False

    def start(self):
        self._on = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self): self._on = False

    def _loop(self):
        while self._on:
            self._kill()
            time.sleep(2)

    def _kill(self):
        try:
            r = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                parts = line.strip().strip('"').split('","')
                if len(parts) < 2: continue
                if parts[0].lower() in self.blocklist:
                    subprocess.run(["taskkill", "/F", "/PID", parts[1]], capture_output=True)
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────
# Website Blocker
# ─────────────────────────────────────────────────────────────────────────────
HOSTS = Path(r"C:\Windows\System32\drivers\etc\hosts")
FL_START = "# FocusLock-START"
FL_END   = "# FocusLock-END"

def _strip(content):
    out, inside = [], False
    for ln in content.splitlines():
        if FL_START in ln: inside = True; continue
        if FL_END   in ln: inside = False; continue
        if not inside: out.append(ln)
    return "\n".join(out)

def block_sites(domains):
    try:
        c = _strip(HOSTS.read_text(encoding="utf-8"))
        block = f"\n{FL_START}\n" + "".join(f"127.0.0.1 {d}\n127.0.0.1 www.{d}\n" for d in domains) + f"{FL_END}\n"
        HOSTS.write_text(c + block, encoding="utf-8")
        return True
    except PermissionError: return False

def unblock_sites():
    try:
        HOSTS.write_text(_strip(HOSTS.read_text(encoding="utf-8")), encoding="utf-8")
    except Exception: pass

# ─────────────────────────────────────────────────────────────────────────────
# Pomodoro Timer
# ─────────────────────────────────────────────────────────────────────────────
class PomodoroTimer:
    def __init__(self, work_min, break_min, on_tick=None, on_phase=None):
        self.work_sec  = work_min * 60
        self.break_sec = break_min * 60
        self.on_tick   = on_tick
        self.on_phase  = on_phase
        self._rem   = self.work_sec
        self._phase = "work"
        self._on    = False
        self.cycles = 0

    @property
    def phase(self):     return self._phase
    @property
    def remaining(self): return self._rem

    def start(self):
        if self._on: return
        self._on = True
        threading.Thread(target=self._loop, daemon=True).start()

    def pause(self): self._on = False

    def reset(self):
        self._on = False
        self._phase = "work"
        self._rem   = self.work_sec
        self.cycles = 0
        if self.on_tick: self.on_tick(self._rem, self._phase)

    def _loop(self):
        while self._on and self._rem > 0:
            time.sleep(1)
            if not self._on: return
            self._rem -= 1
            if self.on_tick: self.on_tick(self._rem, self._phase)
        if self._on and self._rem <= 0:
            self._switch()

    def _switch(self):
        if self._phase == "work":
            self.cycles += 1; self._phase = "break"; self._rem = self.break_sec
        else:
            self._phase = "work"; self._rem = self.work_sec
        if self.on_phase: self.on_phase(self._phase, self.cycles)
        threading.Thread(target=self._loop, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# Windows notification (no CMD flash — uses patched Popen)
# ─────────────────────────────────────────────────────────────────────────────
def notify(title, msg):
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        "$n.Visible=$true;"
        f"$n.ShowBalloonTip(4000,'{title}','{msg}',[System.Windows.Forms.ToolTipIcon]::None);"
        "Start-Sleep -s 5;$n.Dispose()"
    )
    try:
        subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", script])
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────────────────────────────────────
DARK = {"bg":"#0f0f13","surface":"#1a1a24","card":"#22223a","accent":"#6c63ff",
        "accent2":"#ff6584","success":"#43e97b","warn":"#f9c74f",
        "text":"#e8e8f0","subtext":"#8888aa","border":"#2e2e4a"}

LIGHT = {"bg":"#f4f4fb","surface":"#ffffff","card":"#eaeaf6","accent":"#6c63ff",
         "accent2":"#ff6584","success":"#2cb67d","warn":"#e09f00",
         "text":"#1a1a2e","subtext":"#555577","border":"#d0d0e8"}

# ─────────────────────────────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────────────────────────────
class FocusLock(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg   = load_config()
        self.stats = load_stats()
        self.C     = DARK if self.cfg["theme"] == "dark" else LIGHT

        self._blocker      = None
        self._timer        = None
        self._session_start= None
        self._locked       = False
        self._paused       = False
        self._mini_win     = None   # the floating "restore" mini window

        self.title(f"FocusLock v{VERSION}")
        self.geometry("820x640")
        self.resizable(False, False)
        self.configure(bg=self.C["bg"])

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        C = self.C

        hdr = tk.Frame(self, bg=C["surface"], height=60)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="🔒 FocusLock", font=("Segoe UI",17,"bold"),
                 bg=C["surface"], fg=C["accent"]).pack(side="left", padx=20, pady=14)
        tk.Label(hdr, text=f"v{VERSION}", font=("Segoe UI",9),
                 bg=C["surface"], fg=C["subtext"]).pack(side="left", pady=14)
        tk.Button(hdr, text="☀" if self.cfg["theme"]=="dark" else "🌙",
                  command=self._toggle_theme, relief="flat",
                  bg=C["surface"], fg=C["subtext"], font=("Segoe UI",14),
                  cursor="hand2", bd=0).pack(side="right", padx=16)

        tab_bar = tk.Frame(self, bg=C["surface"])
        tab_bar.pack(fill="x")
        self._pages    = {}
        self._tab_btns = {}
        self._cur_tab  = "Session"

        for tab in ["Session","Blocklist","Websites","Stats","Settings"]:
            b = tk.Button(tab_bar, text=tab, relief="flat",
                          bg=C["surface"], fg=C["subtext"],
                          font=("Segoe UI",10), padx=16, pady=10,
                          command=lambda t=tab: self._switch_tab(t),
                          cursor="hand2", bd=0)
            b.pack(side="left")
            self._tab_btns[tab] = b

        self._content = tk.Frame(self, bg=C["bg"])
        self._content.pack(fill="both", expand=True, padx=20, pady=16)

        self._build_session()
        self._build_blocklist()
        self._build_websites()
        self._build_stats()
        self._build_settings()
        self._switch_tab("Session")

    def _switch_tab(self, name):
        C = self.C
        for n,p in self._pages.items(): p.pack_forget()
        for n,b in self._tab_btns.items():
            b.configure(fg=C["accent"] if n==name else C["subtext"],
                        font=("Segoe UI",10,"bold" if n==name else "normal"))
        self._pages[name].pack(fill="both", expand=True)
        self._cur_tab = name

    # ── toggle widget (replaces broken Checkbutton on Windows) ───────────────
    def _toggle(self, parent, var, callback):
        C = self.C
        def refresh():
            on = var.get()
            btn.configure(text=" ON " if on else " OFF",
                          bg=C["accent"] if on else C["border"],
                          fg="white" if on else C["subtext"])
        def click():
            var.set(not var.get()); refresh(); callback()
        btn = tk.Button(parent, text="", command=click, relief="flat",
                        font=("Segoe UI",8,"bold"), padx=8, pady=4,
                        cursor="hand2", bd=0, width=5)
        refresh()
        return btn

    # ── Session tab ───────────────────────────────────────────────────────────
    def _build_session(self):
        C = self.C
        f = tk.Frame(self._content, bg=C["bg"])
        self._pages["Session"] = f

        nr = tk.Frame(f, bg=C["bg"]); nr.pack(fill="x", pady=(0,8))
        tk.Label(nr, text="Session name (optional):", bg=C["bg"], fg=C["subtext"],
                 font=("Segoe UI",9)).pack(side="left")
        self._sname = tk.StringVar(value=self.cfg.get("session_name",""))
        tk.Entry(nr, textvariable=self._sname, bg=C["card"], fg=C["text"],
                 insertbackground=C["text"], relief="flat",
                 font=("Segoe UI",10), width=30).pack(side="left", padx=8)

        card = tk.Frame(f, bg=C["card"]); card.pack(fill="x", pady=(0,10))

        self._phase_lbl = tk.Label(card, text="FOCUS TIME", font=("Segoe UI",11,"bold"),
                                   bg=C["card"], fg=C["accent"])
        self._phase_lbl.pack(pady=(16,2))
        self._timer_lbl = tk.Label(card, text="25:00", font=("Courier New",54,"bold"),
                                   bg=C["card"], fg=C["text"])
        self._timer_lbl.pack()
        self._cycle_lbl = tk.Label(card, text="No cycles yet", font=("Segoe UI",9),
                                   bg=C["card"], fg=C["subtext"])
        self._cycle_lbl.pack(pady=(0,8))
        self._progress = ttk.Progressbar(card, length=420, mode="determinate")
        self._progress.pack(pady=(0,14))

        br = tk.Frame(card, bg=C["card"]); br.pack(pady=(0,16))
        self._start_btn = tk.Button(br, text="🔒  START SESSION",
                                    command=self._toggle_session,
                                    bg=C["accent"], fg="white",
                                    font=("Segoe UI",12,"bold"),
                                    relief="flat", padx=22, pady=9,
                                    cursor="hand2", bd=0)
        self._start_btn.pack(side="left", padx=4)
        self._pause_btn = tk.Button(br, text="⏸ Pause", command=self._pause_resume,
                                    bg=C["card"], fg=C["subtext"], font=("Segoe UI",10),
                                    relief="flat", padx=12, pady=9,
                                    cursor="hand2", bd=0, state="disabled")
        self._pause_btn.pack(side="left", padx=4)
        tk.Button(br, text="↺ Reset", command=self._reset_timer,
                  bg=C["card"], fg=C["subtext"], font=("Segoe UI",10),
                  relief="flat", padx=12, pady=9, cursor="hand2", bd=0).pack(side="left", padx=4)

        pr = tk.Frame(f, bg=C["bg"]); pr.pack(fill="x", pady=2)
        tk.Label(pr, text="Preset:", bg=C["bg"], fg=C["subtext"],
                 font=("Segoe UI",9)).pack(side="left")
        self._preset = tk.StringVar(value="Classic (25/5)")
        for lbl in PRESETS:
            tk.Radiobutton(pr, text=lbl, variable=self._preset, value=lbl,
                           command=self._apply_preset, bg=C["bg"], fg=C["text"],
                           selectcolor=C["card"], activebackground=C["bg"],
                           font=("Segoe UI",9), cursor="hand2").pack(side="left", padx=6)

        self._status = tk.Label(f, text="Ready. Pick a preset and start your session.",
                                bg=C["bg"], fg=C["subtext"], font=("Segoe UI",9))
        self._status.pack(pady=6)

    # ── Blocklist tab ─────────────────────────────────────────────────────────
    def _build_blocklist(self):
        C = self.C
        f = tk.Frame(self._content, bg=C["bg"])
        self._pages["Blocklist"] = f
        tk.Label(f, text="App Blocklist", font=("Segoe UI",13,"bold"),
                 bg=C["bg"], fg=C["text"]).pack(anchor="w", pady=(0,2))
        tk.Label(f, text="These processes are force-killed every 2 seconds during a session.",
                 bg=C["bg"], fg=C["subtext"], font=("Segoe UI",9)).pack(anchor="w", pady=(0,8))
        lf = tk.Frame(f, bg=C["card"]); lf.pack(fill="both", expand=True)
        sb = tk.Scrollbar(lf); sb.pack(side="right", fill="y")
        self._app_lb = tk.Listbox(lf, yscrollcommand=sb.set, bg=C["card"], fg=C["text"],
                                  selectbackground=C["accent"], font=("Consolas",10),
                                  relief="flat", bd=0, highlightthickness=0)
        self._app_lb.pack(fill="both", expand=True, padx=8, pady=8)
        sb.config(command=self._app_lb.yview)
        for a in self.cfg["blocklist"]: self._app_lb.insert(tk.END, a)
        br = tk.Frame(f, bg=C["bg"]); br.pack(fill="x", pady=6)
        tk.Button(br, text="+ Add App", command=self._add_app,
                  bg=C["accent"], fg="white", relief="flat",
                  font=("Segoe UI",9,"bold"), padx=12, pady=5,
                  cursor="hand2", bd=0).pack(side="left", padx=(0,6))
        tk.Button(br, text="✕ Remove", command=self._remove_app,
                  bg=C["card"], fg=C["accent2"], relief="flat",
                  font=("Segoe UI",9), padx=12, pady=5,
                  cursor="hand2", bd=0).pack(side="left")
        tk.Button(br, text="↺ Defaults", command=self._reset_app_defaults,
                  bg=C["card"], fg=C["subtext"], relief="flat",
                  font=("Segoe UI",9), padx=12, pady=5,
                  cursor="hand2", bd=0).pack(side="right")

    # ── Websites tab ──────────────────────────────────────────────────────────
    def _build_websites(self):
        C = self.C
        f = tk.Frame(self._content, bg=C["bg"])
        self._pages["Websites"] = f
        tk.Label(f, text="Website Blocker", font=("Segoe UI",13,"bold"),
                 bg=C["bg"], fg=C["text"]).pack(anchor="w", pady=(0,2))
        tk.Label(f, text="⚠  Requires Administrator — right-click → Run as Administrator.",
                 bg=C["bg"], fg=C["warn"], font=("Segoe UI",9)).pack(anchor="w", pady=(0,8))

        self._web_var = tk.BooleanVar(value=self.cfg.get("block_websites", False))
        wr = tk.Frame(f, bg=C["bg"]); wr.pack(anchor="w", pady=(0,8))
        tk.Label(wr, text="Block websites during sessions",
                 bg=C["bg"], fg=C["text"], font=("Segoe UI",10)).pack(side="left")
        self._toggle(wr, self._web_var, self._save_cfg).pack(side="left", padx=10)

        lf = tk.Frame(f, bg=C["card"]); lf.pack(fill="both", expand=True)
        sb = tk.Scrollbar(lf); sb.pack(side="right", fill="y")
        self._web_lb = tk.Listbox(lf, yscrollcommand=sb.set, bg=C["card"], fg=C["text"],
                                  selectbackground=C["accent"], font=("Consolas",10),
                                  relief="flat", bd=0, highlightthickness=0)
        self._web_lb.pack(fill="both", expand=True, padx=8, pady=8)
        sb.config(command=self._web_lb.yview)
        for s in self.cfg["website_blocklist"]: self._web_lb.insert(tk.END, s)
        br = tk.Frame(f, bg=C["bg"]); br.pack(fill="x", pady=6)
        tk.Button(br, text="+ Add Site", command=self._add_site,
                  bg=C["accent"], fg="white", relief="flat",
                  font=("Segoe UI",9,"bold"), padx=12, pady=5,
                  cursor="hand2", bd=0).pack(side="left", padx=(0,6))
        tk.Button(br, text="✕ Remove", command=self._remove_site,
                  bg=C["card"], fg=C["accent2"], relief="flat",
                  font=("Segoe UI",9), padx=12, pady=5,
                  cursor="hand2", bd=0).pack(side="left")

    # ── Stats tab ─────────────────────────────────────────────────────────────
    def _build_stats(self):
        C = self.C
        f = tk.Frame(self._content, bg=C["bg"])
        self._pages["Stats"] = f
        tk.Label(f, text="Study Stats", font=("Segoe UI",13,"bold"),
                 bg=C["bg"], fg=C["text"]).pack(anchor="w", pady=(0,12))
        s = self.stats
        h, m = s["total_minutes"]//60, s["total_minutes"]%60
        for icon, label, val in [
            ("📅","Total Sessions", str(s["total_sessions"])),
            ("⏱","Total Focus Time", f"{h}h {m}m"),
            ("🔥","Current Streak", f"{s['current_streak']} days"),
            ("🏆","Longest Streak", f"{s['longest_streak']} days"),
        ]:
            row = tk.Frame(f, bg=C["card"]); row.pack(fill="x", pady=3)
            tk.Label(row, text=icon, font=("Segoe UI",16), bg=C["card"]).pack(side="left", padx=12, pady=10)
            tk.Label(row, text=label, font=("Segoe UI",10), bg=C["card"], fg=C["subtext"]).pack(side="left")
            tk.Label(row, text=val, font=("Segoe UI",12,"bold"), bg=C["card"], fg=C["accent"]).pack(side="right", padx=16)
        if s.get("last_session_date"):
            tk.Label(f, text=f"Last session: {s['last_session_date']}",
                     bg=C["bg"], fg=C["subtext"], font=("Segoe UI",9)).pack(anchor="w", pady=8)
        tk.Button(f, text="Reset all stats", command=self._reset_stats,
                  bg=C["card"], fg=C["accent2"], relief="flat",
                  font=("Segoe UI",9), pady=5, cursor="hand2", bd=0).pack(anchor="e", pady=10)

    # ── Settings tab ──────────────────────────────────────────────────────────
    def _build_settings(self):
        C = self.C
        f = tk.Frame(self._content, bg=C["bg"])
        self._pages["Settings"] = f
        tk.Label(f, text="Settings", font=("Segoe UI",13,"bold"),
                 bg=C["bg"], fg=C["text"]).pack(anchor="w", pady=(0,12))

        def row(parent, icon_text):
            r = tk.Frame(parent, bg=C["card"]); r.pack(fill="x", pady=3)
            tk.Label(r, text=icon_text, bg=C["card"], fg=C["text"],
                     font=("Segoe UI",10)).pack(side="left", padx=12, pady=12)
            return r

        # Launch with Windows
        self._startup_var = tk.BooleanVar(value=startup_is_on())
        r = row(f, "🚀  Launch with Windows")
        self._toggle(r, self._startup_var, self._do_startup).pack(side="right", padx=12)

        # Break notifications
        self._notif_var = tk.BooleanVar(value=self.cfg.get("notify_break", True))
        r = row(f, "🔔  Break notifications")
        self._toggle(r, self._notif_var, self._save_cfg).pack(side="right", padx=12)

        # Minimize to tray
        self._tray_var = tk.BooleanVar(value=self.cfg.get("minimize_to_tray", True))
        r = row(f, "🗕  Minimize to tray on close (instead of quitting)")
        self._toggle(r, self._tray_var, self._save_cfg).pack(side="right", padx=12)

        # Session password
        r = row(f, "🔑  Session stop password")
        has = self.cfg.get("password_hash","")
        tk.Label(r, text="✓ Set" if has else "Not set",
                 bg=C["card"], fg=C["success"] if has else C["subtext"],
                 font=("Segoe UI",9)).pack(side="right", padx=6)
        tk.Button(r, text="Change", command=lambda: self._change_pw("password_hash"),
                  bg=C["accent"], fg="white", relief="flat",
                  font=("Segoe UI",9), padx=8, pady=3,
                  cursor="hand2", bd=0).pack(side="right", padx=6)

        # Parent password
        r = row(f, "👨‍👧  Parent password (overrides session pw)")
        hasp = self.cfg.get("parent_password_hash","")
        tk.Label(r, text="✓ Set" if hasp else "Not set",
                 bg=C["card"], fg=C["success"] if hasp else C["subtext"],
                 font=("Segoe UI",9)).pack(side="right", padx=6)
        tk.Button(r, text="Change", command=lambda: self._change_pw("parent_password_hash"),
                  bg=C["accent"], fg="white", relief="flat",
                  font=("Segoe UI",9), padx=8, pady=3,
                  cursor="hand2", bd=0).pack(side="right", padx=6)

        # About
        about = tk.Frame(f, bg=C["card"]); about.pack(fill="x", pady=3)
        tk.Label(about, text=f"FocusLock v{VERSION}  ·  made by zadwen  ·  github.com/zadwen/FocusLock",
                 bg=C["card"], fg=C["subtext"], font=("Segoe UI",9)).pack(padx=12, pady=10)

        tk.Label(f, text="Coming soon: daily goals, export stats, multiple profiles, Discord status",
                 bg=C["bg"], fg=C["subtext"], font=("Segoe UI",8,"italic")).pack(anchor="w", pady=(8,0))

    # ── Session logic ─────────────────────────────────────────────────────────
    def _toggle_session(self):
        if not self._locked: self._start()
        else: self._stop()

    def _start(self):
        C = self.C
        work, brk = PRESETS.get(self._preset.get(), (25,5))
        self._timer = PomodoroTimer(work, brk, on_tick=self._tick, on_phase=self._phase_change)
        self._progress["maximum"] = work * 60
        self._blocker = AppBlocker(self.cfg["blocklist"])
        self._blocker.start()
        if self._web_var.get():
            if not block_sites(self.cfg["website_blocklist"]):
                messagebox.showwarning("Admin needed",
                    "Website blocking needs Administrator.\nRight-click → Run as Administrator.")
        self._timer.start()
        self._locked = True
        self._paused = False
        self._session_start = datetime.datetime.now()
        self.cfg["session_name"] = self._sname.get()
        save_config(self.cfg)
        self._start_btn.configure(text="🔓  STOP SESSION", bg=C["accent2"])
        self._pause_btn.configure(state="normal")
        self._status.configure(text="🔒 Session active. Stay focused!")

    def _stop(self):
        # password check
        if self.cfg.get("password_hash") or self.cfg.get("parent_password_hash"):
            pw = simpledialog.askstring("Unlock", "Enter password to stop:", show="*")
            if not pw: return
            h = hash_pw(pw)
            if h != self.cfg.get("password_hash") and h != self.cfg.get("parent_password_hash"):
                messagebox.showerror("Wrong password", "Stay focused! 💪")
                return
        C = self.C
        if self._timer:   self._timer.pause()
        if self._blocker: self._blocker.stop()
        unblock_sites()
        self._locked = False
        self._paused = False
        self._start_btn.configure(text="🔒  START SESSION", bg=C["accent"])
        self._pause_btn.configure(state="disabled", text="⏸ Pause")
        self._status.configure(text="Session ended. Good work!")
        self._record()

    def _pause_resume(self):
        if not self._locked or not self._timer: return
        C = self.C
        if not self._paused:
            self._timer.pause()
            if self._blocker: self._blocker.stop()
            self._paused = True
            self._pause_btn.configure(text="▶ Resume")
            self._status.configure(text="⏸ Paused.")
        else:
            self._timer.start()
            self._blocker = AppBlocker(self.cfg["blocklist"])
            self._blocker.start()
            self._paused = False
            self._pause_btn.configure(text="⏸ Pause")
            self._status.configure(text="🔒 Back to focus.")

    def _reset_timer(self):
        if self._locked: messagebox.showinfo("Active","Stop the session first."); return
        if self._timer: self._timer.reset()
        work, _ = PRESETS.get(self._preset.get(), (25,5))
        self._timer_lbl.configure(text=f"{work:02d}:00")
        self._phase_lbl.configure(text="FOCUS TIME")
        self._progress["value"] = 0
        self._cycle_lbl.configure(text="No cycles yet")

    def _apply_preset(self):
        if self._locked: return
        work, brk = PRESETS[self._preset.get()]
        self.cfg["pomodoro_work"] = work
        self.cfg["pomodoro_break"] = brk
        save_config(self.cfg)
        self._timer_lbl.configure(text=f"{work:02d}:00")
        self._progress["value"] = 0

    # ── Timer callbacks ───────────────────────────────────────────────────────
    def _tick(self, rem, phase):
        self.after(0, self._draw_timer, rem, phase)

    def _draw_timer(self, rem, phase):
        m, s = divmod(rem, 60)
        self._timer_lbl.configure(text=f"{m:02d}:{s:02d}")
        total = (self.cfg["pomodoro_work"] if phase=="work" else self.cfg["pomodoro_break"]) * 60
        self._progress["maximum"] = total
        self._progress["value"]   = total - rem

    def _phase_change(self, phase, cycles):
        self.after(0, self._draw_phase, phase, cycles)

    def _draw_phase(self, phase, cycles):
        C = self.C
        if phase == "work":
            self._phase_lbl.configure(text="FOCUS TIME", fg=C["accent"])
            if self._notif_var.get(): notify("FocusLock","Break's over — back to work! 💪")
        else:
            self._phase_lbl.configure(text="☕ BREAK TIME", fg=C["success"])
            if self._notif_var.get(): notify("FocusLock",f"Nice! Take a break. ({cycles} cycles done)")
        self._cycle_lbl.configure(text=f"{cycles} cycle{'s' if cycles!=1 else ''} done")
        self.bell()

    # ── List management ───────────────────────────────────────────────────────
    def _add_app(self):
        v = simpledialog.askstring("Add app","Enter .exe name (e.g. discord.exe):")
        if v and v.strip():
            n = v.strip().lower()
            if n not in self.cfg["blocklist"]:
                self.cfg["blocklist"].append(n)
                self._app_lb.insert(tk.END, n)
                save_config(self.cfg)

    def _remove_app(self):
        sel = self._app_lb.curselection()
        if not sel: return
        v = self._app_lb.get(sel[0])
        self._app_lb.delete(sel[0])
        if v in self.cfg["blocklist"]: self.cfg["blocklist"].remove(v)
        save_config(self.cfg)

    def _reset_app_defaults(self):
        if messagebox.askyesno("Reset","Reset blocklist to defaults?"):
            self.cfg["blocklist"] = DEFAULT_APPS[:]
            self._app_lb.delete(0, tk.END)
            for a in self.cfg["blocklist"]: self._app_lb.insert(tk.END, a)
            save_config(self.cfg)

    def _add_site(self):
        v = simpledialog.askstring("Add site","Enter domain (e.g. reddit.com):")
        if v and v.strip():
            n = v.strip().lower()
            if n not in self.cfg["website_blocklist"]:
                self.cfg["website_blocklist"].append(n)
                self._web_lb.insert(tk.END, n)
                save_config(self.cfg)

    def _remove_site(self):
        sel = self._web_lb.curselection()
        if not sel: return
        v = self._web_lb.get(sel[0])
        self._web_lb.delete(sel[0])
        if v in self.cfg["website_blocklist"]: self.cfg["website_blocklist"].remove(v)
        save_config(self.cfg)

    # ── Passwords ─────────────────────────────────────────────────────────────
    def _change_pw(self, key):
        pw = simpledialog.askstring("Password","New password (blank = disable):", show="*")
        if pw is None: return
        self.cfg[key] = hash_pw(pw) if pw else ""
        save_config(self.cfg)
        messagebox.showinfo("Saved","Password updated!" if pw else "Password removed.")

    # ── Stats ─────────────────────────────────────────────────────────────────
    def _record(self):
        if not self._session_start: return
        mins = max(1, (datetime.datetime.now()-self._session_start).seconds//60)
        today = datetime.date.today().isoformat()
        self.stats["total_sessions"] += 1
        self.stats["total_minutes"]  += mins
        self.stats["sessions_by_date"][today] = self.stats["sessions_by_date"].get(today,0)+1
        last = self.stats.get("last_session_date","")
        if last:
            try:
                diff = (datetime.date.today() - datetime.date.fromisoformat(last)).days
                if diff == 1:   self.stats["current_streak"] += 1
                elif diff > 1:  self.stats["current_streak"] = 1
            except Exception:   self.stats["current_streak"] = 1
        else: self.stats["current_streak"] = 1
        self.stats["longest_streak"] = max(self.stats["longest_streak"], self.stats["current_streak"])
        self.stats["last_session_date"] = today
        save_stats(self.stats)
        self._session_start = None

    def _reset_stats(self):
        if messagebox.askyesno("Reset","Clear all your study stats?"):
            self.stats = {"total_sessions":0,"total_minutes":0,"sessions_by_date":{},
                          "current_streak":0,"longest_streak":0,"last_session_date":""}
            save_stats(self.stats)

    # ── Settings helpers ──────────────────────────────────────────────────────
    def _do_startup(self):
        if not set_startup(self._startup_var.get()):
            messagebox.showwarning("Error","Couldn't update startup. Try running as Admin.")
        self._save_cfg()

    def _save_cfg(self):
        self.cfg["block_websites"]   = self._web_var.get()
        self.cfg["notify_break"]     = self._notif_var.get()
        self.cfg["minimize_to_tray"] = self._tray_var.get()
        save_config(self.cfg)

    def _toggle_theme(self):
        self.cfg["theme"] = "light" if self.cfg["theme"]=="dark" else "dark"
        save_config(self.cfg)
        messagebox.showinfo("Theme","Restart FocusLock to apply the new theme.")

    # ── Close / minimize to tray ──────────────────────────────────────────────
    def _on_close(self):
        if self._locked:
            messagebox.showwarning("Locked","Stop the session before closing!")
            return
        if self._tray_var.get():
            self._minimize()
        else:
            self._quit()

    def _minimize(self):
        """Hide main window and show a small always-on-top restore bar."""
        self.withdraw()
        if self._mini_win and self._mini_win.winfo_exists():
            return  # already showing

        C = self.C
        w = tk.Toplevel(self)
        w.overrideredirect(True)        # no title bar / borders
        w.attributes("-topmost", True)  # always on top
        w.attributes("-alpha", 0.95)
        w.configure(bg=C["accent"])

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w.geometry(f"180x38+{sw-194}+{sh-70}")

        def restore():
            self._mini_win = None
            w.destroy()
            self.deiconify()
            self.lift()

        def quit_app():
            self._mini_win = None
            w.destroy()
            self._quit()

        tk.Button(w, text="🔒 FocusLock", command=restore,
                  bg=C["accent"], fg="white", relief="flat",
                  font=("Segoe UI",9,"bold"), cursor="hand2", bd=0
                  ).pack(side="left", padx=10, pady=6)
        tk.Button(w, text="✕", command=quit_app,
                  bg=C["accent"], fg="white", relief="flat",
                  font=("Segoe UI",10,"bold"), cursor="hand2", bd=0
                  ).pack(side="right", padx=8)

        self._mini_win = w

    def _quit(self):
        if self._blocker: self._blocker.stop()
        unblock_sites()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = FocusLock()
    app.mainloop()
