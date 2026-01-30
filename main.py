#!/usr/bin/env python3
"""
Smooth Floating Button - Advanced LXQt/Openbox Edition
Multi-monitor, keyboard navigation, persistence, smart grouping

Requirements:
sudo apt install python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets
sudo apt install wmctrl xdotool
"""

import sys
import subprocess
import math
import colorsys
import json
from pathlib import Path
from collections import defaultdict
from PySide6.QtCore import (Qt, QTimer, QPoint, Property, QPropertyAnimation, 
                            QEasingCurve, QRect, QPointF, QSettings, Signal)
from PySide6.QtGui import (QColor, QPainter, QRadialGradient, QFont, QPen, 
                          QIcon, QCursor, QPixmap, QLinearGradient, QBrush)
from PySide6.QtWidgets import QApplication, QWidget, QMainWindow, QMenu

# --- CONFIGURATION ---
CONFIG = {
    "RING_SIZE": 800,        
    "HUB_RADIUS": 190,
    "SPOKE_LENGTH": 70,      
    "HUB_ICON_SIZE": 40,
    "NODE_RADIUS": 16,       
    "NODE_BORDER_WIDTH": 2.5,  
    "PEEK_ENABLED": True,
    "PEEK_DELAY": 150,       # ms before peeking
    "TITLE_FONT_SIZE": 12,   
    "ANIM_DURATION": 350,
    "BUTTON_SIZE": 64,
    "UPDATE_INTERVAL": 16,
    "SMART_POSITION": True,  # Remember position across sessions
    "SNAP_TO_EDGES": True,   # Magnetic edge snapping
    "SNAP_THRESHOLD": 25,    # pixels from edge to snap
    "KEYBOARD_NAV": True,    # Arrow key navigation
}

class WindowRing(QWidget):
    """Enhanced hierarchical graph switcher with keyboard navigation"""
    def __init__(self, parent, windows, global_center, target_screen):
        super().__init__()
        self.parent_btn = parent
        self.groups = defaultdict(list)
        
        # Smart grouping: merge similar apps
        for w in windows:
            app_key = self._normalize_app_name(w['app'])
            self.groups[app_key].append(w)
        
        # Remove single-window groups of certain apps (optional)
        # This keeps the graph cleaner for apps with many windows
        
        self.ring_size = CONFIG["RING_SIZE"]
        self.hub_radius = CONFIG["HUB_RADIUS"]
        self.spoke_length = CONFIG["SPOKE_LENGTH"]
        
        # --- INTELLIGENT MULTI-MONITOR CENTERING ---
        screen_geo = target_screen.geometry()
        available_geo = target_screen.availableGeometry()
        
        target_x = global_center.x() - (self.ring_size // 2)
        target_y = global_center.y() - (self.ring_size // 2)
        
        # Smart clamping with edge detection
        padding = 15
        x = max(available_geo.left() + padding, 
                min(target_x, available_geo.right() - self.ring_size - padding))
        y = max(available_geo.top() + padding, 
                min(target_y, available_geo.bottom() - self.ring_size - padding))
        
        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.ToolTip | 
            Qt.WindowType.NoDropShadowWindowHint |
            Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        
        self.setFixedSize(self.ring_size, self.ring_size)
        self.move(x, y)
        
        # State management
        self._anim_progress = 0.0
        self.hover_win_id = None
        self.selected_index = -1  # For keyboard navigation
        self.node_positions = [] 
        self.flat_windows = []    # Flattened list for keyboard nav
        self.icon_cache = {}
        self.peek_timer = QTimer(self)
        self.peek_timer.setSingleShot(True)
        self.peek_timer.timeout.connect(self._do_peek)
        self.pending_peek_id = None

        # Smooth entrance animation
        self.anim = QPropertyAnimation(self, b"anim_progress")
        self.anim.setDuration(CONFIG["ANIM_DURATION"])
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.setFocus()

    def _normalize_app_name(self, app_name):
        """Normalize app names for better grouping"""
        app_lower = app_name.lower()
        
        # Browser consolidation
        if any(x in app_lower for x in ['chrome', 'chromium', 'brave', 'firefox', 'edge']):
            if 'brave' in app_lower:
                return 'Brave'
            elif 'firefox' in app_lower:
                return 'Firefox'
            elif 'chrome' in app_lower:
                return 'Chrome'
        
        # Code editors
        if any(x in app_lower for x in ['code', 'vscode', 'vscodium']):
            return 'Code'
        
        # Terminals
        if any(x in app_lower for x in ['terminal', 'konsole', 'qterminal', 'gnome-terminal']):
            return 'Terminal'
        
        return app_name

    @Property(float)
    def anim_progress(self): 
        return self._anim_progress
    
    @anim_progress.setter
    def anim_progress(self, val):
        self._anim_progress = max(0.0, min(1.0, val))
        self.update()

    def get_app_icon(self, app_name):
        """Enhanced icon loading with better fallbacks"""
        if app_name in self.icon_cache:
            return self.icon_cache[app_name]
        
        icon_map = {
            'brave': 'brave-browser',
            'firefox': 'firefox',
            'chrome': 'google-chrome',
            'code': 'vscode',
            'terminal': 'utilities-terminal',
            'qterminal': 'utilities-terminal',
            'pcmanfm': 'system-file-manager',
            'dolphin': 'system-file-manager',
            'nautilus': 'system-file-manager',
        }
        
        icon_names = [
            icon_map.get(app_name.lower(), app_name.lower()),
            app_name.lower(),
            app_name.lower().replace(' ', '-'),
            app_name.lower().split()[0] if ' ' in app_name else app_name.lower()
        ]
        
        icon = QIcon()
        for name in icon_names:
            icon = QIcon.fromTheme(name)
            if not icon.isNull():
                break
        
        if icon.isNull():
            icon = QIcon.fromTheme("application-x-executable")
        
        pix = icon.pixmap(CONFIG["HUB_ICON_SIZE"], CONFIG["HUB_ICON_SIZE"])
        self.icon_cache[app_name] = pix
        return pix

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        cx, cy = self.width() / 2, self.height() / 2
        prog = self._anim_progress
        
        # Elegant background with depth
        for i in range(3):
            grad = QRadialGradient(cx, cy, (380 - i*30) * prog)
            alpha = int((200 - i*50) * prog)
            grad.setColorAt(0, QColor(20, 20, 35, alpha))
            grad.setColorAt(0.8, QColor(10, 10, 20, alpha // 2))
            grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(int(cx), int(cy)), 
                              int((380 - i*30) * prog), 
                              int((380 - i*30) * prog))

        self.node_positions = []
        self.flat_windows = []
        
        app_names = sorted(self.groups.keys())
        num_apps = len(app_names)
        
        if num_apps == 0:
            return
        
        flat_idx = 0
        for i, app_name in enumerate(app_names):
            angle = (2 * math.pi * i / num_apps) - (math.pi / 2)
            hub_dist = self.hub_radius * prog
            hub_x = cx + hub_dist * math.cos(angle)
            hub_y = cy + hub_dist * math.sin(angle)
            
            # Vibrant, consistent colors
            hue = (hash(app_name) % 360) / 360.0
            r, g, b = colorsys.hls_to_rgb(hue, 0.6, 0.85)
            app_color = QColor.fromRgbF(r, g, b, prog)
            
            # Hub glow effect
            hub_glow = QRadialGradient(hub_x, hub_y, 50 * prog)
            hub_glow.setColorAt(0, QColor(app_color.red(), app_color.green(), 
                                          app_color.blue(), int(60 * prog)))
            hub_glow.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setBrush(hub_glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(hub_x, hub_y), 50 * prog, 50 * prog)
            
            # App icon
            pix = self.get_app_icon(app_name)
            if not pix.isNull():
                icon_size = CONFIG["HUB_ICON_SIZE"]
                painter.setOpacity(prog)
                painter.drawPixmap(
                    int(hub_x - icon_size/2), 
                    int(hub_y - icon_size/2), 
                    pix
                )
                painter.setOpacity(1.0)
            
            # Window nodes
            wins = self.groups[app_name]
            num_wins = len(wins)
            
            for j, win in enumerate(wins):
                spoke_off = (j - (num_wins-1)/2) * (math.pi / 11) if num_wins > 1 else 0
                total_angle = angle + spoke_off
                
                win_x = hub_x + self.spoke_length * prog * math.cos(total_angle)
                win_y = hub_y + self.spoke_length * prog * math.sin(total_angle)
                
                # Connection line with gradient
                grad_line = QLinearGradient(hub_x, hub_y, win_x, win_y)
                grad_line.setColorAt(0, QColor(app_color.red(), app_color.green(), 
                                               app_color.blue(), int(120 * prog)))
                grad_line.setColorAt(1, QColor(255, 255, 255, int(100 * prog)))
                painter.setPen(QPen(QBrush(grad_line), 2.0))
                painter.drawLine(QPointF(hub_x, hub_y), QPointF(win_x, win_y))
                
                # Node appearance
                is_hovered = self.hover_win_id == win['id']
                is_selected = self.selected_index == flat_idx
                
                radius = CONFIG["NODE_RADIUS"] * prog
                if is_hovered or is_selected:
                    radius *= 1.6
                
                self.node_positions.append((QPointF(win_x, win_y), radius, win))
                self.flat_windows.append(win)
                
                # Node glow for selection
                if is_hovered or is_selected:
                    glow = QRadialGradient(win_x, win_y, radius * 1.8)
                    glow.setColorAt(0, QColor(255, 255, 255, 100))
                    glow.setColorAt(1, QColor(255, 255, 255, 0))
                    painter.setBrush(glow)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(QPointF(win_x, win_y), radius * 1.8, radius * 1.8)
                
                # Node circle
                painter.setBrush(app_color)
                if is_hovered or is_selected:
                    painter.setPen(QPen(Qt.GlobalColor.white, CONFIG["NODE_BORDER_WIDTH"] + 1))
                else:
                    painter.setPen(QPen(QColor(255, 255, 255, int(220 * prog)), 
                                       CONFIG["NODE_BORDER_WIDTH"]))
                
                painter.drawEllipse(QPointF(win_x, win_y), radius, radius)
                
                # Window title overlay
                if is_hovered or is_selected:
                    title_text = win['title'][:55]
                    painter.setFont(QFont("Sans", CONFIG["TITLE_FONT_SIZE"], QFont.Weight.Bold))
                    
                    fm = painter.fontMetrics()
                    text_width = fm.horizontalAdvance(title_text)
                    text_height = fm.height()
                    
                    # Smart positioning
                    title_x = win_x + 45 if win_x < cx else win_x - text_width - 45
                    title_y = win_y
                    
                    # Semi-transparent background
                    padding = 8
                    text_rect = QRect(int(title_x - padding), 
                                     int(title_y - text_height/2 - padding/2), 
                                     text_width + padding*2, 
                                     text_height + padding)
                    
                    painter.setBrush(QColor(0, 0, 0, 200))
                    painter.setPen(QPen(app_color, 2))
                    painter.drawRoundedRect(text_rect, 6, 6)
                    
                    painter.setPen(Qt.GlobalColor.white)
                    painter.drawText(int(title_x), int(title_y + text_height/3), title_text)
                
                flat_idx += 1

            # App label
            painter.setPen(QColor(255, 255, 255, int(240 * prog)))
            painter.setFont(QFont("Sans", 11, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            label_width = fm.horizontalAdvance(app_name)
            label_x = hub_x - label_width/2
            
            # Label background
            label_rect = QRect(int(label_x - 5), int(hub_y - 35), label_width + 10, 18)
            painter.setBrush(QColor(0, 0, 0, int(150 * prog)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(label_rect, 4, 4)
            
            painter.setPen(QColor(255, 255, 255, int(240 * prog)))
            painter.drawText(int(label_x), int(hub_y - 22), app_name)

        # Center info
        if num_apps > 0:
            painter.setPen(QColor(200, 200, 200, int(180 * prog)))
            painter.setFont(QFont("Sans", 10, QFont.Weight.Normal))
            total_wins = sum(len(wins) for wins in self.groups.values())
            info_text = f"{total_wins} windows · {num_apps} apps"
            fm = painter.fontMetrics()
            info_width = fm.horizontalAdvance(info_text)
            painter.drawText(int(cx - info_width/2), int(cy + 5), info_text)

    def mouseMoveEvent(self, event):
        pos = event.position()
        new_hover_id = None
        new_selected = -1
        
        for idx, (center, radius, win) in enumerate(self.node_positions):
            dx = pos.x() - center.x()
            dy = pos.y() - center.y()
            dist = math.sqrt(dx*dx + dy*dy)
            
            if dist < radius + 20:
                new_hover_id = win['id']
                new_selected = idx
                break
        
        if new_hover_id != self.hover_win_id:
            self.hover_win_id = new_hover_id
            self.selected_index = new_selected
            
            # Delayed peek
            self.peek_timer.stop()
            if self.hover_win_id and CONFIG["PEEK_ENABLED"]:
                self.pending_peek_id = self.hover_win_id
                self.peek_timer.start(CONFIG["PEEK_DELAY"])
            
            self.update()

    def _do_peek(self):
        """Execute delayed peek"""
        if self.pending_peek_id:
            try:
                subprocess.run(["wmctrl", "-i", "-a", self.pending_peek_id], 
                             timeout=0.5, capture_output=True)
                self.raise_()
                self.activateWindow()
            except:
                pass

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.hover_win_id:
                subprocess.run(["wmctrl", "-i", "-a", self.hover_win_id])
                self.close()
            else:
                self.close()

    def keyPressEvent(self, event):
        key = event.key()
        
        if key == Qt.Key.Key_Escape:
            self.close()
            
        elif CONFIG["KEYBOARD_NAV"] and key in (Qt.Key.Key_Tab, Qt.Key.Key_Right, Qt.Key.Key_Down):
            # Next window
            if self.flat_windows:
                self.selected_index = (self.selected_index + 1) % len(self.flat_windows)
                self.hover_win_id = self.flat_windows[self.selected_index]['id']
                self.update()
                
        elif CONFIG["KEYBOARD_NAV"] and key in (Qt.Key.Key_Backtab, Qt.Key.Key_Left, Qt.Key.Key_Up):
            # Previous window
            if self.flat_windows:
                self.selected_index = (self.selected_index - 1) % len(self.flat_windows)
                self.hover_win_id = self.flat_windows[self.selected_index]['id']
                self.update()
                
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            if self.hover_win_id:
                subprocess.run(["wmctrl", "-i", "-a", self.hover_win_id])
                self.close()

class FloatingButton(QMainWindow):
    def __init__(self):
        super().__init__()
        self.btn_size = CONFIG["BUTTON_SIZE"]
        
        # Settings persistence
        self.settings = QSettings("FloatingButton", "WindowSwitcher")
        
        # Window setup
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.X11BypassWindowManagerHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.btn_size, self.btn_size)
        
        # Restore position
        if CONFIG["SMART_POSITION"]:
            saved_pos = self.settings.value("button_position")
            if saved_pos:
                self.move(saved_pos)
            else:
                self.move(300, 300)
        else:
            self.move(300, 300)
        
        # State
        self.is_dragging = False
        self.click_pos = QPoint()
        self.drag_start_pos = QPoint()
        self.pulse = 0.0
        self.is_hovering = False
        
        # Animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(CONFIG["UPDATE_INTERVAL"])
        
        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def update_animation(self):
        self.pulse += 0.04
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        cx, cy = self.width() / 2, self.height() / 2
        
        # Breathing effect
        pulse_factor = 0.92 + 0.08 * math.sin(self.pulse)
        if self.is_hovering:
            pulse_factor *= 1.1
        
        radius = 28 * pulse_factor
        
        # Outer glow
        glow = QRadialGradient(cx, cy, radius * 1.5)
        glow.setColorAt(0, QColor(100, 160, 255, 80))
        glow.setColorAt(1, QColor(60, 80, 200, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), radius * 1.5, radius * 1.5)
        
        # Main button
        grad = QRadialGradient(cx, cy, radius)
        if self.is_hovering:
            grad.setColorAt(0, QColor(120, 180, 255))
            grad.setColorAt(1, QColor(80, 120, 220))
        else:
            grad.setColorAt(0, QColor(100, 160, 255))
            grad.setColorAt(1, QColor(60, 80, 200))
        
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 2.5))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
        
        # Icon
        painter.setPen(Qt.GlobalColor.white)
        painter.setFont(QFont("Sans", 18, QFont.Weight.Bold))
        painter.drawText(int(cx - 9), int(cy + 9), "◆")

    def enterEvent(self, event):
        self.is_hovering = True
        self.update()

    def leaveEvent(self, event):
        self.is_hovering = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.click_pos = event.globalPosition().toPoint()
            self.drag_start_pos = self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            delta = event.globalPosition().toPoint() - self.click_pos
            new_pos = self.drag_start_pos + delta
            
            # Edge snapping
            if CONFIG["SNAP_TO_EDGES"]:
                screen = QApplication.screenAt(QCursor.pos())
                if screen:
                    geo = screen.availableGeometry()
                    threshold = CONFIG["SNAP_THRESHOLD"]
                    
                    # Snap to left
                    if abs(new_pos.x() - geo.left()) < threshold:
                        new_pos.setX(geo.left() + 5)
                    # Snap to right
                    elif abs(new_pos.x() + self.width() - geo.right()) < threshold:
                        new_pos.setX(geo.right() - self.width() - 5)
                    
                    # Snap to top
                    if abs(new_pos.y() - geo.top()) < threshold:
                        new_pos.setY(geo.top() + 5)
                    # Snap to bottom
                    elif abs(new_pos.y() + self.height() - geo.bottom()) < threshold:
                        new_pos.setY(geo.bottom() - self.height() - 5)
            
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            
            # Save position
            if CONFIG["SMART_POSITION"]:
                self.settings.setValue("button_position", self.pos())
            
            # Click vs drag detection
            if (event.globalPosition().toPoint() - self.click_pos).manhattanLength() < 10:
                self.show_ring()

    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: white;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #4a90e2;
            }
        """)
        
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.quit)
        
        menu.exec(self.mapToGlobal(pos))

    def get_windows(self):
        """Enhanced window detection"""
        try:
            result = subprocess.run(
                ["wmctrl", "-lx"], 
                capture_output=True, 
                text=True,
                timeout=2
            )
            
            windows = []
            ignore_classes = {
                'pcmanfm-desktop', 'xfdesktop', 'lxqt-panel', 
                'desktop_window', 'plank', 'cairo-dock', 'conky'
            }
            ignore_titles = {'float', 'floating button', 'desktop'}
            
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                    
                parts = line.split(None, 4)
                if len(parts) < 5:
                    continue
                
                win_id = parts[0]
                desktop = parts[1]
                win_class = parts[2].split('.')[0].lower()
                title = parts[4]
                
                # Skip desktop windows
                if desktop == '-1':
                    continue
                
                # Filter unwanted
                if any(ign in win_class for ign in ignore_classes):
                    continue
                if any(ign in title.lower() for ign in ignore_titles):
                    continue
                if not title.strip():
                    continue
                
                # Clean app name
                app_name = win_class.capitalize()
                app_map = {
                    'brave-browser': 'Brave',
                    'code': 'VSCode',
                    'qterminal': 'Terminal',
                    'pcmanfm-qt': 'Files',
                }
                app_name = app_map.get(win_class, app_name)
                
                windows.append({
                    'id': win_id, 
                    'app': app_name, 
                    'title': title.strip()
                })
            
            return windows
            
        except Exception as e:
            print(f"Error getting windows: {e}")
            return []

    def show_ring(self):
        """Display the enhanced window ring"""
        wins = self.get_windows()
        if not wins:
            return
        
        button_center = self.frameGeometry().center()
        screen = QApplication.screenAt(button_center)
        if not screen:
            screen = QApplication.primaryScreen()
        
        self.ring = WindowRing(self, wins, button_center, screen)
        self.ring.show()
        self.ring.raise_()
        self.ring.activateWindow()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setApplicationName("FloatingButton")
    app.setOrganizationName("FloatingButton")
    
    btn = FloatingButton()
    btn.show()
    
    sys.exit(app.exec())