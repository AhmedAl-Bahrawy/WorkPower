"""Reusable themed UI components for FocusLock using PySide6."""

import math
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, 
                               QHBoxLayout, QLineEdit, QScrollArea, QListWidget, QGraphicsDropShadowEffect, QSizePolicy)
from PySide6.QtCore import Qt, Signal, Property, QRectF, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QIcon, QBrush, QPainterPath

# ─────────────────────────────────────────────────────────────────────────────
# Theme styling functions
# ─────────────────────────────────────────────────────────────────────────────
class Theme:
    def __init__(self, name, colors):
        self.name = name
        self.c = colors

    def apply_to_app(self, app):
        """Apply global stylesheet to the application."""
        c = self.c
        style = f"""
        QWidget {{
            background-color: {c['bg']};
            color: {c['text']};
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
        }}
        QMainWindow, QDialog {{
            background-color: {c['bg']};
        }}
        QFrame#card {{
            background-color: {c['card']};
            border-radius: 12px;
            border: 1px solid {c['border']};
        }}
        QFrame#sidebar {{
            background-color: {c['sidebar']};
            border-right: 1px solid {c['border']};
        }}
        QLabel {{
            background: transparent;
        }}
        QLineEdit {{
            background-color: {c['input']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 8px 12px;
        }}
        QLineEdit:focus {{
            border: 1px solid {c['accent']};
        }}
        QScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 8px;
            margin: 0px 0px 0px 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {c['muted']};
            min-height: 20px;
            border-radius: 4px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
        }}
        QListWidget {{
            background-color: {c['card']};
            border-radius: 8px;
            border: 1px solid {c['border']};
            outline: 0;
        }}
        QListWidget::item {{
            padding: 8px;
            border-bottom: 1px solid {c['border']};
        }}
        QListWidget::item:selected {{
            background-color: {c['accent']};
            color: white;
        }}
        """
        app.setStyleSheet(style)


# ─────────────────────────────────────────────────────────────────────────────
# Label helper
# ─────────────────────────────────────────────────────────────────────────────
def label(text="", style="text", theme=None):
    lbl = QLabel(text)
    if not theme:
        return lbl
        
    c = theme.c
    
    fg_map = {
        "text":    c["text"],
        "subtext": c["subtext"],
        "muted":   c["muted"],
        "accent":  c["accent"],
        "success": c["success"],
        "warn":    c["warn"],
        "danger":  c["danger"],
        "heading": c["text"],
        "title":   c["text"],
        "caption": c["subtext"],
    }
    
    font_weight = "bold" if style in ["title", "heading", "caption"] else "normal"
    font_size = "18px" if style == "title" else "14px" if style == "heading" else "12px" if style in ["caption", "subtext"] else "11px" if style == "muted" else "14px"
    
    lbl.setStyleSheet(f"color: {fg_map.get(style, c['text'])}; font-weight: {font_weight}; font-size: {font_size};")
    return lbl

# ─────────────────────────────────────────────────────────────────────────────
# Layout helpers
# ─────────────────────────────────────────────────────────────────────────────
def make_card(theme=None):
    """A flat card-coloured frame with rounded corners."""
    frame = QFrame()
    frame.setObjectName("card")
    
    # Optional drop shadow
    if theme:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 4)
        frame.setGraphicsEffect(shadow)
        
    return frame

def divider(theme):
    """Thin horizontal separator."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setStyleSheet(f"border: none; background-color: {theme.c['border']}; height: 1px;")
    return line

# ─────────────────────────────────────────────────────────────────────────────
# Button helper
# ─────────────────────────────────────────────────────────────────────────────
def button(text, command=None, variant="primary", theme=None, icon=None):
    btn = QPushButton(text)
    if icon:
        btn.setIcon(QIcon(icon))
        
    if theme:
        c = theme.c
        styles = {
            "primary":   (c["accent"],   "white",            c["accent_hover"]),
            "secondary": (c["card"],     c["text"],          c["card_hover"]),
            "danger":    (c["danger"],   "white",            "#cc3355"),
            "ghost":     ("transparent", c["subtext"],       c["card"]),
            "success":   (c["success"],  "white",            "#2aad72"),
        }
        bg, fg, hover = styles.get(variant, styles["secondary"])
        border = f"1px solid {c['border']}" if variant == "secondary" else "none"
        
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: {border};
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {bg};
            }}
        """)
        
    btn.setCursor(Qt.PointingHandCursor)
    if command:
        btn.clicked.connect(command)
    return btn


# ─────────────────────────────────────────────────────────────────────────────
# Toggle switch (Custom QWidget)
# ─────────────────────────────────────────────────────────────────────────────
class ToggleButton(QWidget):
    toggled = Signal(bool)
    
    def __init__(self, theme, initial_state=False):
        super().__init__()
        self.theme = theme
        self._is_checked = initial_state
        self._circle_pos = 2 if not initial_state else 26
        
        self.setFixedSize(48, 24)
        self.setCursor(Qt.PointingHandCursor)
        
        # Animation
        self._anim = QPropertyAnimation(self, b"circle_pos")
        self._anim.setEasingCurve(QEasingCurve.InOutQuad)
        self._anim.setDuration(150)
        
        self._circle_pos = 2 if not initial_state else 26
        
    @Property(float)
    def circle_pos(self):
        return self._circle_pos
        
    @circle_pos.setter
    def circle_pos(self, pos):
        self._circle_pos = pos
        self.update()
        
    def isChecked(self):
        return self._is_checked
        
    def setChecked(self, state, animate=True):
        if self._is_checked != state:
            self._is_checked = state
            
            end_val = 26 if state else 2
            
            if animate:
                self._anim.setStartValue(self._circle_pos)
                self._anim.setEndValue(end_val)
                self._anim.start()
            else:
                self.circle_pos = end_val
                
            self.toggled.emit(state)
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._is_checked)
        super().mouseReleaseEvent(event)
        
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        
        c = self.theme.c
        bg_color = QColor(c["accent"]) if self._is_checked else QColor(c["border"])
        
        # Draw background
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)
        
        # Draw circle
        circle_color = QColor("white") if self._is_checked else QColor(c["subtext"])
        p.setBrush(QBrush(circle_color))
        p.drawEllipse(int(self._circle_pos), 2, 20, 20)

# ─────────────────────────────────────────────────────────────────────────────
# Scrollable Frame Helper
# ─────────────────────────────────────────────────────────────────────────────
class ScrollableFrame(QScrollArea):
    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        
        self.inner = QWidget()
        self.inner.setStyleSheet("background: transparent;")
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(8)
        self.inner_layout.setAlignment(Qt.AlignTop)
        
        self.setWidget(self.inner)
        
    def scroll_to_bottom(self):
        # Allow layout to update first
        QTimer.singleShot(10, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))


# ─────────────────────────────────────────────────────────────────────────────
# Circular / arc timer on a QWidget
# ─────────────────────────────────────────────────────────────────────────────
class CircularTimer(QWidget):
    """
    A widget that draws a round progress ring using QPainter.
    Call .set_value(remaining, total, phase) to update it.
    """

    def __init__(self, theme, size=240):
        super().__init__()
        self.theme = theme
        self.setFixedSize(size, size)
        
        self._total = 1
        self._remaining = 1
        self._phase = "work"
        
    def set_value(self, remaining, total, phase):
        self._remaining = remaining
        self._total = max(total, 1)
        self._phase = phase
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        size = min(self.width(), self.height())
        cx = self.width() / 2
        cy = self.height() / 2
        
        r_outer = size / 2 - 12
        r_inner = r_outer - 18
        
        c = self.theme.c
        
        # Track ring (background circle)
        track_pen = QPen(QColor(c["border"]))
        track_pen.setWidth(18)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawEllipse(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2))
        
        # Progress arc
        frac = self._remaining / self._total
        arc_deg = frac * 360
        ring_color_hex = c["timer_work"] if self._phase == "work" else c["timer_break"]
        ring_color = QColor(ring_color_hex)
        
        if arc_deg > 0:
            arc_pen = QPen(ring_color)
            arc_pen.setWidth(18)
            arc_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(arc_pen)
            
            # drawArc takes angles in 1/16ths of a degree. 90 degrees is top.
            # It draws counter-clockwise if positive, so we use negative for clockwise.
            # We want it to decrease counter-clockwise (so start at 90, span is arc_deg * 16)
            start_angle = 90 * 16
            span_angle = int(arc_deg * 16)
            
            painter.drawArc(QRectF(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2), start_angle, span_angle)
            
        # Inner fill circle
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(c["timer_bg"])))
        painter.drawEllipse(QRectF(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2))
        
        # Glowing dot at arc tip (only if arc is drawn and not full)
        if 0 < arc_deg < 360:
            painter.setBrush(QBrush(ring_color))
            painter.setPen(QPen(QColor(c["bg"]), 2))
            
            angle_rad = math.radians(90 + arc_deg)
            dot_x = cx + r_outer * math.cos(angle_rad)
            dot_y = cy - r_outer * math.sin(angle_rad)
            
            painter.drawEllipse(QRectF(dot_x - 7, dot_y - 7, 14, 14))


# ─────────────────────────────────────────────────────────────────────────────
# Mini bar chart (7-day widget)
# ─────────────────────────────────────────────────────────────────────────────
class BarChart(QWidget):
    def __init__(self, theme, data=None, labels=None, height=120):
        super().__init__()
        self.theme = theme
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._data = data or []
        self._labels = labels or []

    def set_data(self, data, labels):
        self._data = data
        self._labels = labels
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        c = self.theme.c
        w = self.width()
        h = self.height()
        
        n = len(self._data)
        mx = max(self._data) if max(self._data) > 0 else 1
        
        pad_x = 20
        pad_top = 20
        pad_bot = 24
        
        usable_w = w - (pad_x * 2)
        bar_w = max(8, (usable_w / n) - 12)
        gap = (usable_w - (n * bar_w)) / max(n - 1, 1) if n > 1 else 0
        
        font_val = QFont("Segoe UI", 8)
        font_lbl = QFont("Segoe UI", 9)
        
        for i, val in enumerate(self._data):
            x = pad_x + i * (bar_w + gap)
            bar_h = max(4, (val / mx) * (h - pad_top - pad_bot))
            y = h - pad_bot - bar_h
            
            # Bar fill with rounded top corners
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, bar_w, bar_h), 4, 4)
            # Make bottom flat by adding a rect over it
            path.addRect(QRectF(x, y + 4, bar_w, bar_h - 4))
            
            painter.fillPath(path, QBrush(QColor(c["accent"])))
            
            # Value label if > 0
            if val > 0:
                painter.setFont(font_val)
                painter.setPen(QColor(c["text"]))
                # Center text over bar
                text_rect = QRectF(x - 10, y - 18, bar_w + 20, 15)
                painter.drawText(text_rect, Qt.AlignCenter, str(val))
                
            # Day label
            if i < len(self._labels):
                painter.setFont(font_lbl)
                painter.setPen(QColor(c["subtext"]))
                text_rect = QRectF(x - 10, h - pad_bot + 4, bar_w + 20, 15)
                painter.drawText(text_rect, Qt.AlignCenter, self._labels[i])


# ─────────────────────────────────────────────────────────────────────────────
# Stat card
# ─────────────────────────────────────────────────────────────────────────────
def stat_card(theme, icon, title, value, color=None):
    c = theme.c
    card = make_card(theme)
    color = color or c["accent"]
    
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)
    
    top = QWidget()
    top_layout = QHBoxLayout(top)
    top_layout.setContentsMargins(0, 0, 0, 0)
    top_layout.setSpacing(10)
    
    icon_lbl = QLabel(icon)
    icon_lbl.setStyleSheet(f"font-size: 24px; color: {color};")
    top_layout.addWidget(icon_lbl)
    
    title_lbl = label(title, "subtext", theme)
    top_layout.addWidget(title_lbl)
    top_layout.addStretch()
    
    layout.addWidget(top)
    
    val_lbl = QLabel(value)
    val_lbl.setStyleSheet(f"font-family: 'Segoe UI Semibold'; font-size: 24px; color: {c['text']};")
    layout.addWidget(val_lbl)
    
    return card


# ─────────────────────────────────────────────────────────────────────────────
# Blocklist item card
# ─────────────────────────────────────────────────────────────────────────────
APP_ICONS = {
    "chrome.exe": "🌐", "firefox.exe": "🦊", "msedge.exe": "🌀", "opera.exe": "🔴", "brave.exe": "🦁",
    "discord.exe": "💬", "slack.exe": "💼", "ms-teams.exe": "📋", "telegram.exe": "✈️", "whatsapp.exe": "📱",
    "steam.exe": "🎮", "steamwebhelper.exe": "🎮", "epicgameslauncher.exe": "🎮", "battle.net.exe": "⚔️",
    "leagueclient.exe": "🎯", "valorant-win64-shipping.exe": "🎯", "robloxplayerbeta.exe": "🧱",
    "spotify.exe": "🎵", "twitchui.exe": "📺", "vlc.exe": "🎬", "itunes.exe": "🎵",
    "zoom.exe": "📹", "obs64.exe": "🔴", "photoshop.exe": "🎨", "blender.exe": "🔵",
}

SITE_ICONS = {
    "youtube.com": "📺", "twitch.tv": "📺", "netflix.com": "🎬", "twitter.com": "🐦", "x.com": "✖️",
    "instagram.com": "📸", "facebook.com": "👍", "tiktok.com": "🎵", "reddit.com": "🤖",
    "discord.com": "💬", "slack.com": "💼", "linkedin.com": "💼", "amazon.com": "🛒", "ebay.com": "🛒",
    "pinterest.com": "📌", "medium.com": "📝", "whatsapp.com": "📱",
}

class BlocklistItemCard(QFrame):
    def __init__(self, theme, name, identifier, item_type="app", enabled=True, on_remove=None, on_toggle=None):
        super().__init__()
        self.setObjectName("card")
        self.theme = theme
        self.identifier = identifier
        
        c = theme.c
        self.setStyleSheet(f"QFrame#card {{ background-color: {c['card']}; border: 1px solid {c['border']}; border-radius: 8px; margin-bottom: 4px; }}")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Icon
        icon_text = APP_ICONS.get(identifier.lower(), "🚫") if item_type == "app" else SITE_ICONS.get(identifier.lower(), "🌐")
        icon_lbl = QLabel(icon_text)
        icon_lbl.setStyleSheet("font-size: 20px;")
        layout.addWidget(icon_lbl)
        
        # Text details
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(8, 0, 8, 0)
        
        self.name_lbl = QLabel(name)
        self.name_lbl.setStyleSheet(f"font-family: 'Segoe UI Semibold'; font-size: 14px; color: {c['text'] if enabled else c['muted']};")
        text_layout.addWidget(self.name_lbl)
        
        self.id_lbl = QLabel(identifier)
        self.id_lbl.setStyleSheet(f"font-family: 'Consolas'; font-size: 12px; color: {c['subtext'] if enabled else c['muted']};")
        text_layout.addWidget(self.id_lbl)
        
        layout.addLayout(text_layout)
        layout.addStretch()
        
        # Toggle
        self.toggle = ToggleButton(theme, enabled)
        if on_toggle:
            self.toggle.toggled.connect(lambda state: self._handle_toggle(state, on_toggle))
        layout.addWidget(self.toggle)
        
        # Remove button
        rm_btn = QPushButton("✕")
        rm_btn.setFixedSize(32, 32)
        rm_btn.setCursor(Qt.PointingHandCursor)
        rm_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {c['muted']}; font-size: 16px; border: none; border-radius: 16px; }}
            QPushButton:hover {{ background: {c['danger']}; color: white; }}
        """)
        if on_remove:
            rm_btn.clicked.connect(lambda: on_remove(self.identifier))
        layout.addWidget(rm_btn)
        
    def _handle_toggle(self, state, callback):
        c = self.theme.c
        self.name_lbl.setStyleSheet(f"font-family: 'Segoe UI Semibold'; font-size: 14px; color: {c['text'] if state else c['muted']};")
        self.id_lbl.setStyleSheet(f"font-family: 'Consolas'; font-size: 12px; color: {c['subtext'] if state else c['muted']};")
        callback(self.identifier, state)
