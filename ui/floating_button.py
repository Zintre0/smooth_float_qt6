"""
FloatingButtonWindow — the draggable floating button.

Pulse animation, hover effects, edge-snapping, position persistence,
context menu, and single-click / double-click to open the ring overlay.
"""

import math

from PySide6.QtCore import Qt, QTimer, QPoint, QPointF, QSettings
from PySide6.QtGui import (
    QColor, QPainter, QRadialGradient, QPen, QFont, QCursor, QGuiApplication,
)
from PySide6.QtWidgets import QMainWindow, QApplication, QMenu, QMessageBox, QDialog

from core.config import load_config, validate_config_schema, save_config
from core.cost_calculator import estimate_costs
from core.hotkey_manager import HotkeyManager
from ui.ring_overlay import RingOverlay


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


class FloatingButtonWindow(QMainWindow):
    """A small draggable floating button that opens the window-ring on click."""

    def __init__(self):
        super().__init__()

        # Load configuration
        self.cfg = load_config("config.json")
        ok, msg = validate_config_schema(self.cfg)
        if not ok:
            QMessageBox.critical(self, "Invalid Config", msg)

        # Window setup
        self.btn_size = int(self.cfg["graphics"].get("button_size", 64))
        self.setFixedSize(self.btn_size, self.btn_size)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint
            | Qt.Tool
        )

        # State
        self.is_dragging = False
        self.click_pos = QPoint()
        self.drag_start = QPoint()
        self.pulse: float = 0.0
        self.is_hovering = False
        self.ring = None  # prevent GC of the overlay

        # Position persistence
        self.settings = QSettings("FloatingButton", "WindowSwitcher")
        behavior = self.cfg.get("behavior", {})
        if behavior.get("smart_position", True):
            saved = self.settings.value("button_position")
            if saved:
                self.move(saved)
            else:
                self.move(300, 300)
        else:
            self.move(300, 300)

        # Animation timer (shares FPS with config)
        fps = max(20, int(self.cfg["performance"].get("max_fps", 60)))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(_clamp(int(1000 / fps), 10, 50))

        # Context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        # Global hotkey
        hotkey_str = self.cfg.get("behavior", {}).get("global_hotkey", "")
        self.hotkey_mgr = HotkeyManager(hotkey_str, debug_level=3, parent=self)
        self.hotkey_mgr.triggered.connect(self._open_ring)
        self.hotkey_mgr.start()

    # ── Animation tick ───────────────────────────────────────────────

    def _tick(self):
        self.pulse += float(self.cfg["animations"].get("pulse_speed", 0.04))
        self.update()

    # ── Painting ─────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2

        # Breathing pulse
        pulse_factor = 0.92 + 0.08 * math.sin(self.pulse)
        if self.is_hovering:
            pulse_factor *= 1.1
        radius = 28 * pulse_factor

        # Outer glow
        glow = QRadialGradient(cx, cy, radius * 1.5)
        glow.setColorAt(0, QColor(100, 160, 255, 80))
        glow.setColorAt(1, QColor(60, 80, 200, 0))
        p.setBrush(glow)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), radius * 1.5, radius * 1.5)

        # Main body
        grad = QRadialGradient(cx, cy, radius)
        if self.is_hovering:
            grad.setColorAt(0, QColor(120, 180, 255))
            grad.setColorAt(1, QColor(80, 120, 220))
        else:
            grad.setColorAt(0, QColor(100, 160, 255))
            grad.setColorAt(1, QColor(60, 80, 200))

        p.setBrush(grad)
        p.setPen(QPen(QColor(255, 255, 255, 200), 2.5))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Center icon (diamond)
        p.setPen(Qt.white)
        p.setFont(QFont("Sans", 18, QFont.Bold))
        p.drawText(int(cx - 9), int(cy + 9), "◆")

    # ── Hover effects ────────────────────────────────────────────────

    def enterEvent(self, event):
        self.is_hovering = True
        self.update()

    def leaveEvent(self, event):
        self.is_hovering = False
        self.update()

    # ── Drag & click ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.click_pos = event.globalPosition().toPoint()
            self.drag_start = self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if not self.is_dragging:
            return

        delta = event.globalPosition().toPoint() - self.click_pos
        new_pos = self.drag_start + delta

        behavior = self.cfg.get("behavior", {})
        if behavior.get("snap_to_edges", True):
            self._snap_to_edges(new_pos)
        else:
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if not self.is_dragging:
            return
        self.is_dragging = False

        # Save position
        behavior = self.cfg.get("behavior", {})
        if behavior.get("smart_position", True):
            self.settings.setValue("button_position", self.pos())

        # Click vs drag — open ring if nearly no movement
        if (event.globalPosition().toPoint() - self.click_pos).manhattanLength() < 10:
            self._open_ring()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._open_ring()

    # ── Edge snapping ────────────────────────────────────────────────

    def _snap_to_edges(self, new_pos: QPoint):
        screen = QGuiApplication.screenAt(QCursor.pos())
        if not screen:
            self.move(new_pos)
            return

        geo = screen.availableGeometry()
        threshold = int(self.cfg.get("behavior", {}).get("snap_threshold", 25))

        x = new_pos.x()
        y = new_pos.y()

        # Horizontal snap
        if abs(x - geo.left()) < threshold:
            x = geo.left() + 5
        elif abs(x + self.width() - geo.right()) < threshold:
            x = geo.right() - self.width() - 5

        # Vertical snap
        if abs(y - geo.top()) < threshold:
            y = geo.top() + 5
        elif abs(y + self.height() - geo.bottom()) < threshold:
            y = geo.bottom() - self.height() - 5

        self.move(QPoint(x, y))

    # ── Ring ─────────────────────────────────────────────────────────

    def _open_ring(self):
        center = self.frameGeometry().center()
        self.ring = RingOverlay(self.cfg, center, parent=None)
        self.ring.show()
        self.ring.raise_()
        self.ring.activateWindow()

    # ── Context menu ─────────────────────────────────────────────────

    def _show_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 5px;
            }
            QMenu::item {
                padding: 7px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #4a90e2;
            }
        """)

        cfg_action = menu.addAction("Configurar…")
        reload_action = menu.addAction("Recargar configuración")
        costs_action = menu.addAction("Mostrar costos")
        menu.addSeparator()
        quit_action = menu.addAction("Salir")

        act = menu.exec(self.mapToGlobal(pos))

        if act == cfg_action:
            self._open_config_dialog()
        elif act == reload_action:
            self.cfg = load_config("config.json")
            self._apply_config_changes()
            QMessageBox.information(self, "Config", "Configuración recargada.")
        elif act == costs_action:
            costs = estimate_costs(self.cfg)
            QMessageBox.information(
                self, "Costos",
                f"CPU: {costs['cpu_pct']}%\nGPU: {costs['gpu_pct']}%\nRAM: {costs['ram_pct']}%",
            )
        elif act == quit_action:
            QApplication.quit()

    def _open_config_dialog(self):
        try:
            from ui.config_dialog import ConfigDialog
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not open ConfigDialog:\n{exc}")
            return

        dlg = ConfigDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cfg = load_config("config.json")
            self._apply_config_changes()

    def _apply_config_changes(self):
        """Re-apply runtime settings that may have changed in config."""
        fps = max(20, int(self.cfg["performance"].get("max_fps", 60)))
        self.timer.setInterval(_clamp(int(1000 / fps), 10, 50))

        # Hot-swap global hotkey
        new_hotkey = self.cfg.get("behavior", {}).get("global_hotkey", "")
        self.hotkey_mgr.set_hotkey(new_hotkey)
