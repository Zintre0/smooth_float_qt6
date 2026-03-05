"""
RingOverlay — full-screen transparent radial ring menu.

Shows application windows grouped by app around a circular hub layout.
Supports hover detection, keyboard navigation, and peek-on-hover.
Configurable peek_mode: "raise" (bring window forward) or "thumbnail"
(capture and display a miniature screenshot).
"""

import math
import subprocess
import colorsys
from typing import Optional

from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPointF, QRect, QRectF,
    Property, QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import (
    QColor, QPainter, QRadialGradient, QLinearGradient,
    QPen, QBrush, QFont, QIcon, QPixmap, QGuiApplication,
)
from PySide6.QtWidgets import QWidget

from core.window_manager import list_windows, smart_group
from core.geometry import build_ring_geometry
from core.thumbnail_cache import ThumbnailCache


# ── Helpers ──────────────────────────────────────────────────────────

def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _icon_from_theme(names: list[str], size: int) -> QPixmap:
    """Try each icon name from the current theme; fall back to a generic icon."""
    icon = QIcon()
    for name in names:
        if not name:
            continue
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            break
    if icon.isNull():
        icon = QIcon.fromTheme("application-x-executable")
    return icon.pixmap(size, size)


# Icon-name hints for common apps
_ICON_MAP: dict[str, str] = {
    "brave":    "brave-browser",
    "firefox":  "firefox",
    "chrome":   "google-chrome",
    "code":     "vscode",
    "terminal": "utilities-terminal",
    "files":    "system-file-manager",
}


# ── RingOverlay ──────────────────────────────────────────────────────

class RingOverlay(QWidget):
    """Transparent overlay that renders the radial window-ring."""

    def __init__(self, cfg: dict, button_center: QPoint, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.ToolTip
            | Qt.X11BypassWindowManagerHint
        )
        self.setMouseTracking(True)

        # State
        self.progress: float = 0.0
        self.hover_win_id: Optional[str] = None
        self.selected_index: int = -1
        self.icon_cache: dict[str, QPixmap] = {}
        self.flat_nodes: list[dict] = []
        self._last_positions: list[tuple[QPointF, float, dict]] = []

        # Peek mode: "raise" or "thumbnail"
        self._peek_mode = str(cfg.get("behavior", {}).get("peek_mode", "raise")).lower()

        # Thumbnail cache (used when peek_mode == "thumbnail")
        self.thumb_cache = ThumbnailCache(parent=self)
        self.thumb_cache.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._active_thumb: Optional[QPixmap] = None
        self._active_thumb_id: Optional[str] = None

        # Peek timer (shared by mouse hover and keyboard nav)
        self.peek_timer = QTimer(self)
        self.peek_timer.setSingleShot(True)
        self.peek_timer.timeout.connect(self._do_peek)
        self.pending_peek_id: Optional[str] = None

        # Size and placement
        self.ring_size = int(self.cfg["graphics"]["ring_size"])
        self.setFixedSize(self.ring_size, self.ring_size)
        self._place_on_screen(button_center)

        # Load window data
        self._refresh_model()

        # Entrance animation
        self.anim = QPropertyAnimation(self, b"animProgress")
        self.anim.setDuration(int(self.cfg["animations"]["fade_duration"]))
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        style = str(self.cfg["animations"].get("ring_style", "elastic")).lower()
        if style in ("elastic", "elasticout"):
            self.anim.setEasingCurve(QEasingCurve.OutBack)
        else:
            self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.start()

        # FPS-capped repaint
        fps = max(20, int(self.cfg["performance"].get("max_fps", 60)))
        self.repaint_timer = QTimer(self)
        self.repaint_timer.setInterval(int(1000 / fps))
        self.repaint_timer.timeout.connect(self.update)
        self.repaint_timer.start()

        self.setFocus()

    # ── Qt Property for animation ────────────────────────────────────

    def _get_anim_progress(self) -> float:
        return self.progress

    def _set_anim_progress(self, value: float):
        self.progress = _clamp(float(value), 0.0, 1.0)

    animProgress = Property(float, _get_anim_progress, _set_anim_progress)

    # ── Helpers ──────────────────────────────────────────────────────

    def _place_on_screen(self, button_center: QPoint):
        """Position the overlay centered on *button_center*, clamped to screen."""
        screen = QGuiApplication.screenAt(button_center)
        if not screen:
            screen = QGuiApplication.primaryScreen()
        ag = screen.availableGeometry()
        pad = 12
        x = _clamp(
            button_center.x() - self.ring_size // 2,
            ag.left() + pad,
            ag.right() - self.ring_size - pad,
        )
        y = _clamp(
            button_center.y() - self.ring_size // 2,
            ag.top() + pad,
            ag.bottom() - self.ring_size - pad,
        )
        self.move(int(x), int(y))

    def _refresh_model(self):
        """Fetch open windows, group them, and compute geometry."""
        wins = list_windows()
        groups = smart_group(wins)
        self.geom = build_ring_geometry(groups, self.cfg)
        self.flat_nodes = self.geom.get("nodes", [])

    def _get_icon(self, app: str) -> QPixmap:
        """Load an icon for *app*, with caching."""
        if app in self.icon_cache:
            return self.icon_cache[app]
        hint = _ICON_MAP.get(app.lower(), app.lower())
        names = [
            hint,
            app.lower(),
            app.lower().replace(" ", "-"),
        ]
        pix = _icon_from_theme(names, int(self.cfg["graphics"]["hub_icon_size"]))
        self.icon_cache[app] = pix
        return pix

    # ── Peek logic (shared by mouse + keyboard) ─────────────────────

    def _start_peek(self, win_id: str, force_thumbnail: bool = False):
        """Start the peek timer for *win_id*.
        If *force_thumbnail* is True, ignore peek_mode and capture a thumbnail.
        """
        self.peek_timer.stop()
        peek_delay = int(self.cfg["performance"].get("peek_delay", 150))
        if win_id and peek_delay >= 0:
            self.pending_peek_id = win_id
            self._pending_force_thumb = force_thumbnail
            self.peek_timer.start(peek_delay)
        else:
            self._pending_force_thumb = False

    def _do_peek(self):
        """Execute the actual peek based on peek_mode and _pending_force_thumb."""
        if not self.pending_peek_id:
            return

        force = getattr(self, "_pending_force_thumb", False)
        self._pending_force_thumb = False  # consume once
        mode = "thumbnail" if force else self._peek_mode

        if mode == "thumbnail":
            self.thumb_cache.capture_async(self.pending_peek_id)
        else:
            try:
                subprocess.run(
                    ["wmctrl", "-i", "-a", self.pending_peek_id],
                    capture_output=True, timeout=0.5,
                )
                self.raise_()
                self.activateWindow()
            except Exception:
                pass

    def _on_thumbnail_ready(self, win_id: str, pix: QPixmap):
        """Slot: a thumbnail capture completed."""
        if win_id == self.hover_win_id:
            self._active_thumb = pix
            self._active_thumb_id = win_id
            self.update()

    # ── Paint ────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        cx = cy = self.width() / 2
        prog = self.progress

        # ── Background: layered radial depth ──
        half = cx
        for i in range(3):
            layer_radius = half * (0.95 - i * 0.08) * prog
            grad = QRadialGradient(cx, cy, max(layer_radius, 1))
            alpha = int((200 - i * 50) * prog)
            grad.setColorAt(0, QColor(20, 20, 35, alpha))
            grad.setColorAt(0.7, QColor(10, 10, 20, alpha // 2))
            grad.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(grad)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(int(cx), int(cy)), int(layer_radius), int(layer_radius))

        hubs = self.geom.get("hubs", [])
        nodes = self.geom.get("nodes", [])
        total_wins = len(nodes)
        total_apps = len(hubs)

        # ── Pre-compute colors per app ──
        app_colors: dict[str, QColor] = {}
        for hub in hubs:
            app = hub["app"]
            hue = (hash(app) % 360) / 360.0
            r, g, b = colorsys.hls_to_rgb(hue, 0.6, 0.85)
            app_colors[app] = QColor.fromRgbF(r, g, b, prog)

        # ── Draw hubs ──
        icon_size = int(self.cfg["graphics"]["hub_icon_size"])
        for hub in hubs:
            hx, hy, app = hub["x"], hub["y"], hub["app"]

            # Hub glow
            hub_glow = QRadialGradient(hx, hy, 50 * prog)
            c = app_colors[app]
            hub_glow.setColorAt(0, QColor(c.red(), c.green(), c.blue(), int(60 * prog)))
            hub_glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(hub_glow)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(hx, hy), 50 * prog, 50 * prog)

            # Icon
            pix = self._get_icon(app)
            p.setOpacity(prog)
            p.drawPixmap(int(hx - icon_size / 2), int(hy - icon_size / 2), pix)
            p.setOpacity(1.0)

            # App label
            p.setPen(QColor(255, 255, 255, int(240 * prog)))
            p.setFont(QFont("Sans", 11, QFont.Bold))
            fm = p.fontMetrics()
            label_w = fm.horizontalAdvance(app)
            label_x = hx - label_w / 2

            # Label background
            label_rect = QRect(int(label_x - 5), int(hy - 35), label_w + 10, 18)
            p.setBrush(QColor(0, 0, 0, int(150 * prog)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(label_rect, 4, 4)

            p.setPen(QColor(255, 255, 255, int(240 * prog)))
            p.drawText(int(label_x), int(hy - 22), app)

        # ── Draw connection lines + nodes ──
        self._last_positions = []
        node_radius_base = float(self.cfg["graphics"]["node_radius"]) * prog
        border_w = float(self.cfg["graphics"].get("node_border_width", 2.5))

        for idx, node in enumerate(nodes):
            app = node["app"]
            nx, ny = node["x"], node["y"]

            # Find parent hub position for the line
            hub_pos = None
            for hub in hubs:
                if hub["app"] == app:
                    hub_pos = (hub["x"], hub["y"])
                    break
            if hub_pos is None:
                hub_pos = (cx, cy)

            # Gradient line from hub to node
            grad_line = QLinearGradient(hub_pos[0], hub_pos[1], nx, ny)
            c = app_colors[app]
            grad_line.setColorAt(0, QColor(c.red(), c.green(), c.blue(), int(120 * prog)))
            grad_line.setColorAt(1, QColor(255, 255, 255, int(100 * prog)))
            p.setPen(QPen(QBrush(grad_line), 2.0))
            p.drawLine(QPointF(hub_pos[0], hub_pos[1]), QPointF(nx, ny))

            # Node state
            is_hovered = self.hover_win_id == node["id"]
            is_selected = self.selected_index == idx
            highlighted = is_hovered or is_selected
            radius = node_radius_base * (1.6 if highlighted else 1.0)

            # Glow on highlight
            if highlighted:
                glow = QRadialGradient(nx, ny, radius * 1.8)
                glow.setColorAt(0, QColor(255, 255, 255, 100))
                glow.setColorAt(1, QColor(255, 255, 255, 0))
                p.setBrush(glow)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(nx, ny), radius * 1.8, radius * 1.8)

            # Node circle
            p.setBrush(app_colors[app])
            if highlighted:
                p.setPen(QPen(Qt.white, border_w + 1))
            else:
                p.setPen(QPen(QColor(255, 255, 255, int(220 * prog)), border_w))
            p.drawEllipse(QPointF(nx, ny), radius, radius)

            # Save the unscaled base radius for mouse hit detection to prevent overlap
            self._last_positions.append((QPointF(nx, ny), node_radius_base, node))

            # ── Tooltip on highlight ──
            if highlighted:
                title_text = node["title"][:55]

                # Check if we have a thumbnail to show
                mode = "thumbnail" if getattr(self, "_pending_force_thumb", False) else self._peek_mode
                show_thumb = (
                    mode == "thumbnail"
                    and self._active_thumb is not None
                    and self._active_thumb_id == node["id"]
                )

                if show_thumb:
                    self._draw_thumbnail_tooltip(p, nx, ny, cx, app_colors.get(app), node, self._active_thumb)
                else:
                    self._draw_text_tooltip(p, nx, ny, cx, app_colors.get(app), title_text)

        # ── Center info text ──
        if total_apps > 0:
            p.setPen(QColor(200, 200, 200, int(180 * prog)))
            p.setFont(QFont("Sans", 10))
            mode_label = f"[{self._peek_mode}]" if self._peek_mode == "thumbnail" else ""
            info = f"{total_wins} windows · {total_apps} apps {mode_label}"
            fm = p.fontMetrics()
            info_w = fm.horizontalAdvance(info)
            p.drawText(int(cx - info_w / 2), int(cy + 5), info)

    # ── Tooltip drawing helpers ──────────────────────────────────────

    def _draw_text_tooltip(self, p: QPainter, nx, ny, cx, color, title_text):
        """Draw a simple text tooltip near a node."""
        p.setFont(QFont("Sans", 12, QFont.Bold))
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(title_text)
        text_h = fm.height()

        title_x = nx + 45 if nx < cx else nx - text_w - 45
        title_y = ny
        padding = 8

        text_rect = QRect(
            int(title_x - padding),
            int(title_y - text_h / 2 - padding / 2),
            text_w + padding * 2,
            text_h + padding,
        )

        p.setBrush(QColor(0, 0, 0, 200))
        p.setPen(QPen(color, 2) if color else QPen(Qt.white, 2))
        p.drawRoundedRect(text_rect, 6, 6)

        p.setPen(Qt.white)
        p.drawText(int(title_x), int(title_y + text_h / 3), title_text)

    def _draw_thumbnail_tooltip(self, p: QPainter, nx, ny, cx, color, node, thumb: QPixmap):
        """Draw a thumbnail preview tooltip near a node."""
        tw, th = thumb.width(), thumb.height()
        padding = 6
        title_text = node["title"][:45]

        p.setFont(QFont("Sans", 10, QFont.Bold))
        fm = p.fontMetrics()
        text_h = fm.height()

        total_w = tw + padding * 2
        total_h = th + text_h + padding * 3

        # Position tooltip
        if nx < cx:
            tooltip_x = nx + 50
        else:
            tooltip_x = nx - total_w - 50

        tooltip_y = ny - total_h / 2

        # Clamp to widget bounds
        tooltip_x = _clamp(tooltip_x, 5, self.width() - total_w - 5)
        tooltip_y = _clamp(tooltip_y, 5, self.height() - total_h - 5)

        # Background
        bg_rect = QRectF(tooltip_x, tooltip_y, total_w, total_h)
        p.setBrush(QColor(15, 15, 25, 230))
        p.setPen(QPen(color, 2) if color else QPen(Qt.white, 2))
        p.drawRoundedRect(bg_rect, 8, 8)

        # Thumbnail image
        img_x = tooltip_x + padding
        img_y = tooltip_y + padding
        p.drawPixmap(int(img_x), int(img_y), thumb)

        # Border around the image
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(img_x, img_y, tw, th), 4, 4)

        # Title text below image
        p.setPen(Qt.white)
        text_y = img_y + th + padding + text_h - 3
        text_w = fm.horizontalAdvance(title_text)
        text_x = tooltip_x + (total_w - text_w) / 2
        p.drawText(int(text_x), int(text_y), title_text)

    # ── Mouse events ─────────────────────────────────────────────────

    def closeEvent(self, event):
        """Clean up timers and cache on close."""
        self.peek_timer.stop()
        self.repaint_timer.stop()
        self.thumb_cache.clear()
        super().closeEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position()
        new_hover = None
        new_index = -1

        for idx, (center, radius, node) in enumerate(self._last_positions):
            dx = pos.x() - center.x()
            dy = pos.y() - center.y()
            if math.hypot(dx, dy) < radius + 20:
                new_hover = node["id"]
                new_index = idx
                break

        if new_hover != self.hover_win_id:
            self.hover_win_id = new_hover
            self.selected_index = new_index

            # Clear stale thumbnail
            if self._active_thumb_id and self._active_thumb_id != new_hover:
                self._active_thumb = None
                self._active_thumb_id = None

            # Start peek
            if new_hover:
                self._start_peek(new_hover)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.hover_win_id:
                try:
                    subprocess.run(["wmctrl", "-i", "-a", self.hover_win_id])
                except Exception:
                    pass
                self.close()
            else:
                self.close()
        elif event.button() == Qt.RightButton:
            self.close()

    # ── Keyboard navigation ──────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key_Escape:
            self.close()

        elif key in (Qt.Key_Tab, Qt.Key_Right, Qt.Key_Down):
            if self.flat_nodes:
                self.selected_index = (self.selected_index + 1) % len(self.flat_nodes)
                self._select_by_keyboard()

        elif key in (Qt.Key_Backtab, Qt.Key_Left, Qt.Key_Up):
            if self.flat_nodes:
                self.selected_index = (self.selected_index - 1) % len(self.flat_nodes)
                self._select_by_keyboard()

        elif key in (Qt.Key_Return, Qt.Key_Space):
            if self.hover_win_id:
                try:
                    subprocess.run(["wmctrl", "-i", "-a", self.hover_win_id])
                except Exception:
                    pass
            self.close()

    def _select_by_keyboard(self):
        """Handle keyboard selection: update hover and trigger peek."""
        node = self.flat_nodes[self.selected_index]
        self.hover_win_id = node["id"]

        # Clear stale thumbnail
        self._active_thumb = None
        self._active_thumb_id = None

        # Trigger peek (force thumbnail so we don't steal focus)
        self._start_peek(node["id"], force_thumbnail=True)
