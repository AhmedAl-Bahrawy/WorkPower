"""Modal dialogs for picking apps and websites — polished v2."""

import tkinter as tk
from tkinter import filedialog, messagebox

from ..blocking.processes import exe_from_path, list_running_processes
from ..blocking.website_blocker import is_valid_domain, normalize_domain
from ..constants import SUGGESTED_APPS, SUGGESTED_SITES
from .widgets import button, entry, label, make_card, ScrollableFrame


# ─────────────────────────────────────────────────────────────────────────────
# App Picker Dialog
# ─────────────────────────────────────────────────────────────────────────────
class AppPickerDialog(tk.Toplevel):
    """Pick running apps, browse for an executable, or type a process name."""

    def __init__(self, parent, theme, existing=None, on_add=None):
        super().__init__(parent)
        self.theme = theme
        self.existing = {e.lower() for e in (existing or [])}
        self.on_add = on_add
        self._processes = []

        self.title("Add Application to Blocklist")
        self.geometry("680x600")
        self.minsize(600, 500)
        self.configure(bg=theme.c["bg"])
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)

        self._build()
        self._refresh_processes()

    def _build(self):
        t = self.theme
        c = t.c

        # ── Header ──────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=c["surface"] if "surface" in c else c["card"])
        header.pack(fill="x")
        inner_h = tk.Frame(header, bg=header.cget("bg"))
        inner_h.pack(fill="x", padx=20, pady=16)

        tk.Label(
            inner_h, text="🚫  Block an Application",
            font=("Segoe UI Semibold", 14), bg=header.cget("bg"), fg=c["text"],
        ).pack(anchor="w")
        tk.Label(
            inner_h,
            text="Select a running app, browse for any .exe, or use Quick Add below.",
            font=("Segoe UI", 9), bg=header.cget("bg"), fg=c["subtext"],
        ).pack(anchor="w", pady=(3, 0))

        sep = tk.Frame(self, bg=c["border"], height=1)
        sep.pack(fill="x")

        # ── Body ────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # Search + Refresh row
        search_row = tk.Frame(body, bg=c["bg"])
        search_row.pack(fill="x", pady=(0, 8))

        tk.Label(
            search_row, text="Running processes",
            font=("Segoe UI Semibold", 10), bg=c["bg"], fg=c["text"],
        ).pack(side="left")
        button(
            search_row, t, "⟳  Refresh",
            command=self._refresh_processes, variant="secondary",
            font=("Segoe UI", 9), padx=10, pady=5,
        ).pack(side="right")

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_processes())
        sf, se = entry(
            body, t, textvariable=self._search_var,
            placeholder="Filter processes…", width=50,
        )
        sf.pack(fill="x", pady=(0, 8))
        se.focus_set()

        # Process list
        list_frame = tk.Frame(body, bg=c["card"])
        list_frame.pack(fill="both", expand=True, pady=(0, 8))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self._list = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            bg=c["card"],
            fg=c["text"],
            selectbackground=c["accent"],
            selectforeground="white",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
        )
        self._list.pack(fill="both", expand=True, padx=10, pady=10)
        scrollbar.config(command=self._list.yview)
        self._list.bind("<Double-Button-1>", lambda _e: self._add_selected())

        # Action buttons
        action_row = tk.Frame(body, bg=c["bg"])
        action_row.pack(fill="x", pady=(0, 12))

        button(
            action_row, t, "✅  Add Selected",
            command=self._add_selected, variant="primary",
            font=("Segoe UI Semibold", 10), padx=14, pady=7,
        ).pack(side="left")
        button(
            action_row, t, "📂  Browse .exe…",
            command=self._browse_exe, variant="secondary",
            font=("Segoe UI", 9), padx=12, pady=7,
        ).pack(side="left", padx=(8, 0))
        button(
            action_row, t, "✏️  Type manually…",
            command=self._manual_entry, variant="secondary",
            font=("Segoe UI", 9), padx=12, pady=7,
        ).pack(side="left", padx=(8, 0))

        # ── Quick Add section ─────────────────────────────────────────────
        qa_label = tk.Label(
            body, text="Quick Add",
            font=("Segoe UI Semibold", 10), bg=c["bg"], fg=c["text"],
        )
        qa_label.pack(anchor="w", pady=(4, 6))

        qa_scroll = ScrollableFrame(body, t)
        qa_scroll.pack(fill="x")
        qa_inner = qa_scroll.inner

        for category, apps in SUGGESTED_APPS.items():
            cat_frame = tk.Frame(qa_inner, bg=c["bg"])
            cat_frame.pack(fill="x", pady=(4, 2))

            tk.Label(
                cat_frame, text=category,
                font=("Segoe UI", 8, "bold"), bg=c["bg"], fg=c["muted"],
            ).pack(anchor="w", pady=(0, 4))

            chips_frame = tk.Frame(cat_frame, bg=c["bg"])
            chips_frame.pack(fill="x")

            for display, exe in apps:
                is_blocked = exe.lower() in self.existing
                chip_text = f"{display} ✓" if is_blocked else display
                chip = button(
                    chips_frame, t, chip_text,
                    command=lambda e=exe, d=display: self._add_one(e, d, "suggested"),
                    variant="secondary",
                    font=("Segoe UI", 8),
                    padx=8, pady=4,
                )
                if is_blocked:
                    chip.configure(fg=c["success"])
                chip.pack(side="left", padx=(0, 6), pady=(0, 6))

    def _refresh_processes(self):
        self._processes = list_running_processes()
        self._filter_processes()

    def _filter_processes(self):
        query = self._search_var.get().strip().lower()
        # Ignore placeholder text
        if query in ("filter processes…",):
            query = ""
        self._list.delete(0, tk.END)
        for proc in self._processes:
            hay = f"{proc['display']} {proc['exe']} {proc.get('path', '')}".lower()
            if query and query not in hay:
                continue
            blocked = "  ✓ blocked" if proc["exe"] in self.existing else ""
            line = f"  {proc['display']:<28}  {proc['exe']}"
            if proc.get("pid"):
                line += f"  (PID {proc['pid']})"
            line += blocked
            self._list.insert(tk.END, line)

    def _selected_process(self):
        sel = self._list.curselection()
        if not sel:
            return None
        query = self._search_var.get().strip().lower()
        if query in ("filter processes…",):
            query = ""
        visible = []
        for proc in self._processes:
            hay = f"{proc['display']} {proc['exe']} {proc.get('path', '')}".lower()
            if query and query not in hay:
                continue
            visible.append(proc)
        if sel[0] >= len(visible):
            return None
        return visible[sel[0]]

    def _add_one(self, exe, display, source):
        exe = exe.lower()
        if not exe.endswith(".exe"):
            exe += ".exe"
        if exe in self.existing:
            messagebox.showinfo(
                "Already blocked",
                f"{display} is already in your blocklist.",
                parent=self,
            )
            return
        if self.on_add:
            self.on_add(exe, display, source)
        self.existing.add(exe)
        self._filter_processes()

    def _add_selected(self):
        proc = self._selected_process()
        if not proc:
            messagebox.showinfo(
                "Select an app",
                "Choose a running application from the list first.",
                parent=self,
            )
            return
        self._add_one(proc["exe"], proc["display"], "running")

    def _browse_exe(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Select application executable",
            filetypes=[("Executables", "*.exe"), ("All files", "*.*")],
        )
        if not path:
            return
        exe, display = exe_from_path(path)
        if not exe:
            return
        self._add_one(exe, display, "browse")

    def _manual_entry(self):
        dialog = tk.Toplevel(self)
        dialog.title("Enter process name")
        dialog.geometry("440x180")
        dialog.configure(bg=self.theme.c["bg"])
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        tk.Label(
            dialog,
            text="Enter the process name (e.g.  discord.exe)",
            font=("Segoe UI", 10), bg=self.theme.c["bg"], fg=self.theme.c["text"],
        ).pack(anchor="w", padx=20, pady=(20, 8))

        var = tk.StringVar()
        frame, widget = entry(dialog, self.theme, textvariable=var, width=44)
        frame.pack(fill="x", padx=20)
        widget.focus_set()

        def submit():
            value = var.get().strip()
            if not value:
                return
            exe = value.lower()
            if not exe.endswith(".exe"):
                exe += ".exe"
            self._add_one(exe, exe.replace(".exe", "").title(), "manual")
            dialog.destroy()

        row = tk.Frame(dialog, bg=self.theme.c["bg"])
        row.pack(fill="x", padx=20, pady=16)
        button(row, self.theme, "Add", command=submit,
               font=("Segoe UI Semibold", 10)).pack(side="left")
        button(row, self.theme, "Cancel", command=dialog.destroy,
               variant="secondary").pack(side="left", padx=(8, 0))
        widget.bind("<Return>", lambda _e: submit())


# ─────────────────────────────────────────────────────────────────────────────
# Site Picker Dialog
# ─────────────────────────────────────────────────────────────────────────────
class SitePickerDialog(tk.Toplevel):
    """Add websites to the blocklist with validation and quick suggestions."""

    def __init__(self, parent, theme, existing=None, on_add=None):
        super().__init__(parent)
        self.theme = theme
        self.existing = {normalize_domain(e) for e in (existing or [])}
        self.on_add = on_add

        self.title("Add Website to Blocklist")
        self.geometry("620x580")
        self.minsize(520, 460)
        self.configure(bg=theme.c["bg"])
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)

        self._build()

    def _build(self):
        t = self.theme
        c = t.c

        # ── Header ──────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=c["surface"] if "surface" in c else c["card"])
        header.pack(fill="x")
        inner_h = tk.Frame(header, bg=header.cget("bg"))
        inner_h.pack(fill="x", padx=20, pady=16)

        tk.Label(
            inner_h, text="🌐  Block a Website",
            font=("Segoe UI Semibold", 14), bg=header.cget("bg"), fg=c["text"],
        ).pack(anchor="w")
        tk.Label(
            inner_h,
            text="Enter any URL — https://, www., and paths are cleaned automatically.",
            font=("Segoe UI", 9), bg=header.cget("bg"), fg=c["subtext"],
        ).pack(anchor="w", pady=(3, 0))

        sep = tk.Frame(self, bg=c["border"], height=1)
        sep.pack(fill="x")

        # ── Body ────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # Domain input
        tk.Label(
            body, text="Website or URL",
            font=("Segoe UI Semibold", 10), bg=c["bg"], fg=c["text"],
        ).pack(anchor="w", pady=(0, 6))

        input_row = tk.Frame(body, bg=c["bg"])
        input_row.pack(fill="x", pady=(0, 8))

        self._domain_var = tk.StringVar()
        domain_frame, domain_entry = entry(
            input_row, t,
            textvariable=self._domain_var,
            placeholder="e.g. reddit.com or https://www.youtube.com/…",
            width=50,
        )
        domain_frame.pack(side="left", fill="x", expand=True)
        domain_entry.focus_set()
        domain_entry.bind("<Return>", lambda _e: self._add_typed())

        button(
            input_row, t, "Add →",
            command=self._add_typed, variant="primary",
            font=("Segoe UI Semibold", 10), padx=14, pady=7,
        ).pack(side="left", padx=(8, 0))

        # ── Quick Add suggestions ─────────────────────────────────────────
        tk.Label(
            body, text="Quick Add  —  Popular distractions",
            font=("Segoe UI Semibold", 10), bg=c["bg"], fg=c["text"],
        ).pack(anchor="w", pady=(16, 8))

        qa_scroll = ScrollableFrame(body, t)
        qa_scroll.pack(fill="both", expand=True)
        qa_inner = qa_scroll.inner

        for category, sites in SUGGESTED_SITES.items():
            cat_frame = tk.Frame(qa_inner, bg=c["bg"])
            cat_frame.pack(fill="x", pady=(4, 2))

            tk.Label(
                cat_frame, text=category,
                font=("Segoe UI", 8, "bold"), bg=c["bg"], fg=c["muted"],
            ).pack(anchor="w", pady=(0, 4))

            chips_frame = tk.Frame(cat_frame, bg=c["bg"])
            chips_frame.pack(fill="x")

            for site in sites:
                is_blocked = site in self.existing
                chip_text = f"{site} ✓" if is_blocked else site
                chip = button(
                    chips_frame, t, chip_text,
                    command=lambda s=site: self._add_one(s),
                    variant="secondary",
                    font=("Segoe UI", 8),
                    padx=8, pady=4,
                    state="disabled" if is_blocked else "normal",
                )
                if is_blocked:
                    chip.configure(fg=c["success"])
                chip.pack(side="left", padx=(0, 6), pady=(0, 6))

    def _add_typed(self):
        domain = normalize_domain(self._domain_var.get())
        if not domain or domain in ("e.g. reddit.com or https://www.youtube.com/…",):
            messagebox.showinfo(
                "Enter a domain",
                "Type a website such as  youtube.com  or paste the full URL.",
                parent=self,
            )
            return
        if not is_valid_domain(domain):
            messagebox.showerror(
                "Invalid domain",
                f"'{domain}' doesn't look like a valid domain.\nExample:  reddit.com",
                parent=self,
            )
            return
        self._add_one(domain)
        self._domain_var.set("")

    def _add_one(self, domain):
        domain = normalize_domain(domain)
        if not domain:
            return
        if domain in self.existing:
            messagebox.showinfo(
                "Already blocked",
                f"{domain} is already in your blocklist.",
                parent=self,
            )
            return
        if self.on_add:
            self.on_add(domain)
        self.existing.add(domain)
