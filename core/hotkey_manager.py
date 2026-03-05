"""
Global hotkey manager using pynput.

Listens for a configurable key combination (e.g. ``<alt>+<space>``) in the
background and emits a Qt signal when triggered.

Debug levels (set via ``debug_level``):
  0 = silent
  1 = errors/warnings only
  2 = info (registration, start/stop)
  3 = verbose (every callback, thread activity)
"""

from __future__ import annotations

import sys
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

try:
    from pynput.keyboard import GlobalHotKeys, Key, KeyCode
    _HAS_PYNPUT = True
except ImportError:
    _HAS_PYNPUT = False


def _log(level: int, current_level: int, tag: str, msg: str):
    """Print a debug message if *level* <= *current_level*."""
    if level <= current_level:
        prefix = {1: "⚠", 2: "ℹ", 3: "🔍"}.get(level, "·")
        print(f"[HOTKEY {prefix} L{level}] {tag}: {msg}", file=sys.stderr, flush=True)


class HotkeyManager(QObject):
    """Background listener for a single global hotkey.

    Emits :pyqt:`triggered` when the configured shortcut is pressed.
    The hotkey string uses **pynput format**: ``<alt>+<space>``,
    ``<ctrl>+<alt>+r``, ``<cmd>+w``, etc.

    Call :meth:`start` to begin listening and :meth:`stop` to tear down.
    """

    triggered = Signal()

    def __init__(
        self,
        hotkey_str: str = "",
        debug_level: int = 2,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._hotkey_str = hotkey_str.strip()
        self._listener: Optional[GlobalHotKeys] = None
        self.debug_level = debug_level
        _log(2, self.debug_level, "init", f"HotkeyManager created, hotkey='{self._hotkey_str}'")

    @property
    def hotkey(self) -> str:
        return self._hotkey_str

    def set_hotkey(self, hotkey_str: str):
        """Change the hotkey.  Restarts the listener if already running."""
        was_running = self._listener is not None
        _log(2, self.debug_level, "set_hotkey",
             f"Changing hotkey: '{self._hotkey_str}' → '{hotkey_str}' (was_running={was_running})")
        if was_running:
            self.stop()
        self._hotkey_str = hotkey_str.strip()
        if was_running and self._hotkey_str:
            self.start()

    def start(self):
        """Start listening for the global hotkey in a daemon thread."""
        if not _HAS_PYNPUT:
            _log(1, self.debug_level, "start", "pynput not installed — global hotkey disabled.")
            return
        if not self._hotkey_str:
            _log(2, self.debug_level, "start", "Empty hotkey string — skipping.")
            return

        self.stop()

        _log(2, self.debug_level, "start", f"Registering hotkey: '{self._hotkey_str}'")
        _log(3, self.debug_level, "start", f"pynput GlobalHotKeys available: {_HAS_PYNPUT}")
        _log(3, self.debug_level, "start", f"Thread: {threading.current_thread().name}")

        try:
            self._listener = GlobalHotKeys({
                self._hotkey_str: self._on_activate,
            })
            self._listener.daemon = True
            self._listener.start()
            _log(2, self.debug_level, "start",
                 f"✓ Listener started for '{self._hotkey_str}' "
                 f"(thread={self._listener.name})")
        except Exception as exc:
            _log(1, self.debug_level, "start",
                 f"✗ Could not register hotkey '{self._hotkey_str}': {exc}")
            _log(3, self.debug_level, "start",
                 f"Exception type: {type(exc).__name__}, args: {exc.args}")
            self._listener = None

    def stop(self):
        """Stop the background listener."""
        if self._listener is not None:
            _log(2, self.debug_level, "stop", "Stopping listener…")
            try:
                self._listener.stop()
                _log(3, self.debug_level, "stop", "Listener stopped OK.")
            except Exception as exc:
                _log(1, self.debug_level, "stop", f"Error stopping listener: {exc}")
            self._listener = None

    def _on_activate(self):
        """Called from the pynput thread; emits the Qt signal (thread-safe)."""
        _log(3, self.debug_level, "activate",
             f"🔥 Hotkey '{self._hotkey_str}' triggered! "
             f"(thread={threading.current_thread().name})")
        self.triggered.emit()

    @staticmethod
    def available() -> bool:
        """Return True if pynput is importable."""
        return _HAS_PYNPUT
