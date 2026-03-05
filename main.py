#!/usr/bin/env python3
"""
Smooth Floating Button v7 — Entry Point

A floating button for LXQt/Openbox that expands into a radial ring of
application windows with smooth animations, smart grouping, keyboard
navigation, and multi-monitor support.

Requirements:
    sudo apt install python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets
    sudo apt install wmctrl xdotool
"""

import sys

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    print(
        "❌ PySide6 is not installed. Install with:\n"
        "   sudo apt install python3-pyside6.qtcore "
        "python3-pyside6.qtgui python3-pyside6.qtwidgets"
    )
    raise

from ui.floating_button import FloatingButtonWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setApplicationName("FloatingButton")
    app.setOrganizationName("FloatingButton")

    btn = FloatingButtonWindow()
    btn.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
