"""Reusable themed UI components for FocusLock."""

import math
import tkinter as tk
from tkinter import ttk


# ─────────────────────────────────────────────────────────────────────────────
# Theme object
# ─────────────────────────────────────────────────────────────────────────────
class Theme:
    def __init__(self, name, colors):
        self.name = name
        self.c = colors

    def configure_root(self, root):
        root.configure(bg=self.c["bg"])

    def style_progressbar(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Focus.Horizontal.TProgressbar",
            troughcolor=self.c["border"],
            background=self.c["accent"],
            bordercolor=self.c["border"],
            lightcolor=self.c["accent"],
            darkcolor=self.c["accent"],
            thickness=8,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Layout helpers
# ─────────────────────────────────────────────────────────────────────────────
def make_card(parent, theme, **kwargs):
    """A flat card-coloured frame."""
    return tk.Frame(parent, bg=theme.c["card"], **kwargs)


def divider(parent, theme):
    """Thin horizontal separator."""
    return tk.Frame(parent, bg=theme.c["border"], height=1)


# ─────────────────────────────────────────────────────────────────────────────
# Label helper
# ─────────────────────────────────────────────────────────────────────────────
def label(parent, theme, text="", style="text", font=None, **kwargs):
    fg_map = {
        "text":    theme.c["text"],
        "subtext": theme.c["subtext"],
        "muted":   theme.c["muted"],
        "accent":  theme.c["accent"],
        "success": theme.c["success"],
        "warn":    theme.c["warn"],
        "danger":  theme.c["danger"],
        "heading": theme.c["text"],
        "title":   theme.c["text"],
        "caption": theme.c["subtext"],
    }
    font_map = {
        "title":   ("Segoe UI Semibold", 18),
        "heading": ("Segoe UI Semibold", 13),
        "caption": ("Segoe UI", 9),
        "subtext": ("Segoe UI", 9),
        "muted":   ("Segoe UI", 8),
    }
    fg = fg_map.get(style, theme.c["text"])
    default_font = font_map.get(style, ("Segoe UI", 10))
    return tk.Label(
        parent,
        text=text,
        bg=kwargs.pop("bg", parent.cget("bg")),
        fg=fg,
        font=font or default_font,
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Button helper with hover
# ─────────────────────────────────────────────────────────────────────────────
def button(parent, theme, text, command=None, variant="primary", **kwargs):
    styles = {
        "primary":   (theme.c["accent"],   "white",            theme.c["accent_hover"]),
        "secondary": (theme.c["card"],     theme.c["text"],    theme.c["card_hover"]),
        "danger":    (theme.c["danger"],   "white",            "#cc3355"),
        "ghost":     (parent.cget("bg"),   theme.c["subtext"], theme.c["card"]),
        "success":   (theme.c["success"],  "white",            "#2aad72"),
    }
    bg, fg, hover = styles.get(variant, styles["secondary"])
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=hover,
        activeforeground=fg,
        relief="flat",
        font=kwargs.pop("font", ("Segoe UI", 10)),
        cursor="hand2",
        bd=0,
        padx=kwargs.pop("padx", 14),
        pady=kwargs.pop("pady", 8),
        **kwargs,
    )

    def on_enter(_): btn.configure(bg=hover)
    def on_leave(_): btn.configure(bg=bg)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


# ─────────────────────────────────────────────────────────────────────────────
# Entry helper
# ─────────────────────────────────────────────────────────────────────────────
def entry(parent, theme, textvariable=None, placeholder="", **kwargs):
    frame = tk.Frame(parent, bg=theme.c["border"], padx=1, pady=1)
    widget = tk.Entry(
        frame,
        textvariable=textvariable,
        bg=theme.c["input"],
        fg=theme.c["text"],
        insertbackground=theme.c["accent"],
        relief="flat",
        font=kwargs.pop("font", ("Segoe UI", 10)),
        **kwargs,
    )
    widget.pack(fill="both", expand=True, ipady=6, ipadx=8)

    # Placeholder logic
    if placeholder:
        widget.config(fg=theme.c["subtext"])
        widget.insert(0, placeholder)

        def on_focus_in(_):
            if widget.get() == placeholder:
                widget.delete(0, tk.END)
                widget.config(fg=theme.c["text"])

        def on_focus_out(_):
            if not widget.get():
                widget.insert(0, placeholder)
                widget.config(fg=theme.c["subtext"])

        widget.bind("<FocusIn>", on_focus_in)
        widget.bind("<FocusOut>", on_focus_out)

    return frame, widget


# ─────────────────────────────────────────────────────────────────────────────
# Toggle switch
# ─────────────────────────────────────────────────────────────────────────────
def toggle_button(parent, theme, variable, command=None):
    btn = tk.Button(
        parent,
        text="",
        relief="flat",
        font=("Segoe UI", 8, "bold"),
        padx=10,
        pady=5,
        cursor="hand2",
        bd=0,
        width=6,
    )

    def refresh():
        on = variable.get()
        btn.configure(
            text=" ON " if on else " OFF",
            bg=theme.c["accent"] if on else theme.c["border"],
            fg="white" if on else theme.c["subtext"],
            activebackground=theme.c["accent_hover"] if on else theme.c["card_hover"],
        )

    def click():
        variable.set(not variable.get())
        refresh()
        if command:
            command()

    btn.configure(command=click)
    refresh()
    return btn


# ─────────────────────────────────────────────────────────────────────────────
# Scrollable listbox
# ─────────────────────────────────────────────────────────────────────────────
def scrollable_list(parent, theme, height=16, selectmode=tk.EXTENDED):
    container = tk.Frame(parent, bg=theme.c["card"])
    scrollbar = tk.Scrollbar(container)
    scrollbar.pack(side="right", fill="y")
    listbox = tk.Listbox(
        container,
        yscrollcommand=scrollbar.set,
        bg=theme.c["card"],
        fg=theme.c["text"],
        selectbackground=theme.c["accent"],
        selectforeground="white",
        font=("Segoe UI", 10),
        relief="flat",
        bd=0,
        highlightthickness=0,
        height=height,
        selectmode=selectmode,
        activestyle="none",
    )
    listbox.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
    scrollbar.config(command=listbox.yview)
    return container, listbox


# ─────────────────────────────────────────────────────────────────────────────
# Circular / arc timer on a Canvas
# ─────────────────────────────────────────────────────────────────────────────
class CircularTimer(tk.Canvas):
    """
    A canvas widget that draws a round progress ring.
    Call .set_value(remaining, total, phase) to update it.
    """

    def __init__(self, parent, theme, size=220, **kwargs):
        self.theme = theme
        self.size = size
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=parent.cget("bg"),
            highlightthickness=0,
            **kwargs,
        )
        self._phase = "work"
        self._draw(1, 1)

    def set_value(self, remaining, total, phase):
        self._phase = phase
        self._draw(remaining, total)

    def _draw(self, remaining, total):
        self.delete("all")
        cx = cy = self.size / 2
        r_outer = self.size / 2 - 8
        r_inner = r_outer - 18
        c = self.theme.c

        # Track ring (background circle)
        self.create_oval(
            cx - r_outer, cy - r_outer,
            cx + r_outer, cy + r_outer,
            outline=c["border"], width=18, fill="",
        )

        # Progress arc
        frac = remaining / max(total, 1)
        arc_deg = frac * 360
        ring_color = c["timer_work"] if self._phase == "work" else c["timer_break"]

        if arc_deg > 0:
            self.create_arc(
                cx - r_outer, cy - r_outer,
                cx + r_outer, cy + r_outer,
                start=90, extent=arc_deg,
                outline=ring_color, width=18,
                style="arc",
            )

        # Inner fill circle
        self.create_oval(
            cx - r_inner, cy - r_inner,
            cx + r_inner, cy + r_inner,
            fill=c["timer_bg"], outline="",
        )

        # Glowing dot at arc tip
        if arc_deg > 0:
            angle_rad = math.radians(90 - arc_deg)
            dot_x = cx + r_outer * math.cos(angle_rad)
            dot_y = cy - r_outer * math.sin(angle_rad)
            self.create_oval(
                dot_x - 7, dot_y - 7,
                dot_x + 7, dot_y + 7,
                fill=ring_color, outline=c["bg"], width=2,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Scrollable frame (for card-based blocklists)
# ─────────────────────────────────────────────────────────────────────────────
class ScrollableFrame(tk.Frame):
    """A frame with a vertical scrollbar; place children in .inner."""

    def __init__(self, parent, theme, **kwargs):
        super().__init__(parent, bg=theme.c["bg"], **kwargs)
        self.theme = theme

        self._canvas = tk.Canvas(
            self, bg=theme.c["bg"],
            highlightthickness=0, bd=0,
        )
        self._scrollbar = tk.Scrollbar(
            self, orient="vertical",
            command=self._canvas.yview,
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self._canvas, bg=theme.c["bg"])
        self._win = self._canvas.create_window(
            (0, 0), window=self.inner, anchor="nw",
        )

        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)

    def _on_inner_configure(self, _event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._win, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def scroll_to_bottom(self):
        self._canvas.yview_moveto(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Blocklist item card
# ─────────────────────────────────────────────────────────────────────────────
APP_ICONS = {
    "chrome.exe": "🌐",
    "firefox.exe": "🦊",
    "msedge.exe": "🌀",
    "opera.exe": "🔴",
    "brave.exe": "🦁",
    "discord.exe": "💬",
    "slack.exe": "💼",
    "ms-teams.exe": "📋",
    "telegram.exe": "✈️",
    "whatsapp.exe": "📱",
    "signal.exe": "🔒",
    "skype.exe": "💙",
    "steam.exe": "🎮",
    "steamwebhelper.exe": "🎮",
    "epicgameslauncher.exe": "🎮",
    "battle.net.exe": "⚔️",
    "leagueclient.exe": "🎯",
    "valorant-win64-shipping.exe": "🎯",
    "robloxplayerbeta.exe": "🧱",
    "spotify.exe": "🎵",
    "twitchui.exe": "📺",
    "vlc.exe": "🎬",
    "itunes.exe": "🎵",
    "zoom.exe": "📹",
    "obs64.exe": "🔴",
    "photoshop.exe": "🎨",
    "blender.exe": "🔵",
}

SITE_ICONS = {
    "youtube.com": "📺",
    "twitch.tv": "📺",
    "netflix.com": "🎬",
    "twitter.com": "🐦",
    "x.com": "✖️",
    "instagram.com": "📸",
    "facebook.com": "👍",
    "tiktok.com": "🎵",
    "reddit.com": "🤖",
    "discord.com": "💬",
    "slack.com": "💼",
    "linkedin.com": "💼",
    "amazon.com": "🛒",
    "ebay.com": "🛒",
    "pinterest.com": "📌",
    "medium.com": "📝",
    "whatsapp.com": "📱",
}


def blocklist_item_card(parent, theme, name, identifier, item_type="app",
                        enabled=True, on_remove=None, on_toggle=None):
    """
    A rich card row for a blocklist item.
    item_type: 'app' or 'site'
    Returns the card frame.
    """
    c = theme.c
    card = tk.Frame(parent, bg=c["card"], pady=0)

    # Icon
    if item_type == "app":
        icon = APP_ICONS.get(identifier.lower(), "🚫")
    else:
        icon = SITE_ICONS.get(identifier.lower(), "🌐")

    icon_lbl = tk.Label(
        card, text=icon, font=("Segoe UI", 15),
        bg=c["card"], fg=c["text"], width=3,
    )
    icon_lbl.pack(side="left", padx=(12, 4), pady=10)

    # Name + identifier
    text_frame = tk.Frame(card, bg=c["card"])
    text_frame.pack(side="left", fill="x", expand=True, pady=10)
    tk.Label(
        text_frame, text=name, font=("Segoe UI Semibold", 10),
        bg=c["card"], fg=c["text"] if enabled else c["muted"],
        anchor="w",
    ).pack(anchor="w")
    tk.Label(
        text_frame, text=identifier, font=("Consolas", 8),
        bg=c["card"], fg=c["subtext"] if enabled else c["muted"],
        anchor="w",
    ).pack(anchor="w")

    # Toggle enabled/disabled
    enabled_var = tk.BooleanVar(value=enabled)
    tog = toggle_button(card, theme, enabled_var,
                        command=lambda: on_toggle(identifier, enabled_var.get()) if on_toggle else None)
    tog.pack(side="right", padx=(4, 4), pady=10)

    # Remove button
    def _remove():
        card.destroy()
        if on_remove:
            on_remove(identifier)

    rm = tk.Button(
        card, text="✕", command=_remove,
        bg=c["card"], fg=c["muted"],
        activebackground=c["danger"], activeforeground="white",
        relief="flat", bd=0, font=("Segoe UI", 11),
        cursor="hand2", padx=8, pady=8,
    )
    rm.pack(side="right", padx=(0, 4), pady=10)

    def _rm_enter(_): rm.configure(fg=c["danger"], bg=c["card_hover"])
    def _rm_leave(_): rm.configure(fg=c["muted"], bg=c["card"])
    rm.bind("<Enter>", _rm_enter)
    rm.bind("<Leave>", _rm_leave)

    # Separator
    sep = tk.Frame(card, bg=c["border"], height=1)
    sep.place(relx=0, rely=1.0, relwidth=1.0, anchor="sw")

    return card


# ─────────────────────────────────────────────────────────────────────────────
# Stat card
# ─────────────────────────────────────────────────────────────────────────────
def stat_card(parent, theme, icon, title, value, color=None):
    c = theme.c
    card = tk.Frame(parent, bg=c["card"], padx=16, pady=14)
    color = color or c["accent"]

    top = tk.Frame(card, bg=c["card"])
    top.pack(fill="x")
    tk.Label(top, text=icon, font=("Segoe UI", 22), bg=c["card"], fg=color).pack(side="left")
    tk.Label(
        top, text=title, font=("Segoe UI", 9),
        bg=c["card"], fg=c["subtext"],
    ).pack(side="left", padx=(8, 0), pady=(10, 0))

    tk.Label(
        card, text=value, font=("Segoe UI Semibold", 22),
        bg=c["card"], fg=c["text"],
    ).pack(anchor="w", pady=(6, 0))

    return card


# ─────────────────────────────────────────────────────────────────────────────
# Mini bar chart (7-day canvas)
# ─────────────────────────────────────────────────────────────────────────────
class BarChart(tk.Canvas):
    def __init__(self, parent, theme, data, labels=None, **kwargs):
        self.theme = theme
        super().__init__(
            parent, bg=theme.c["card"],
            highlightthickness=0, bd=0, **kwargs,
        )
        self.bind("<Configure>", lambda _e: self._draw(data, labels))
        self._data = data
        self._labels = labels
        self.after(50, lambda: self._draw(data, labels))

    def _draw(self, data, labels):
        self.delete("all")
        if not data:
            return
        c = self.theme.c
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return

        n = len(data)
        mx = max(data) if max(data) > 0 else 1
        bar_w = max(8, (w - 40) / n - 8)
        gap = (w - 40 - n * bar_w) / max(n - 1, 1)
        pad_x = 20
        pad_top = 16
        pad_bot = 24

        for i, val in enumerate(data):
            x = pad_x + i * (bar_w + gap)
            bar_h = max(4, (val / mx) * (h - pad_top - pad_bot))
            y1 = h - pad_bot - bar_h
            y2 = h - pad_bot

            # Bar fill
            self.create_rectangle(
                x, y1, x + bar_w, y2,
                fill=c["accent"], outline="", width=0,
            )
            # Value label if > 0
            if val > 0:
                self.create_text(
                    x + bar_w / 2, y1 - 6,
                    text=str(val), fill=c["subtext"],
                    font=("Segoe UI", 7),
                )
            # Day label
            if labels and i < len(labels):
                self.create_text(
                    x + bar_w / 2, h - 10,
                    text=labels[i], fill=c["muted"],
                    font=("Segoe UI", 7),
                )
