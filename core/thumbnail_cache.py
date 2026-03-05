"""
Window thumbnail cache using native PySide6 screen grabbing.

Captures window screenshots by X11 window ID directly using Qt
(QScreen.grabWindow), avoiding external CLI tools and X11 colormap
errors on hardware-accelerated windows.
"""

import sys
import threading
import time
from typing import Optional
from collections import deque

from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtCore import QObject, Signal, Qt


def _log(msg: str):
    print(f"[THUMB] {msg}", file=sys.stderr, flush=True)


class ThumbnailCache(QObject):
    """LRU thumbnail cache using native Qt window grabbing.

    Emits ``thumbnail_ready(str, QPixmap)`` when an async capture completes.
    Since QScreen.grabWindow *must* run on the main GUI thread, we emit
    a private signal from the background thread to trigger the grab on the main thread.
    """

    thumbnail_ready = Signal(str, QPixmap)
    _request_grab = Signal(str, int, int)  # win_id, w, h

    def __init__(self, max_size: int = 30, ttl: float = 10.0, parent=None):
        super().__init__(parent)
        self._cache: dict[str, tuple[QPixmap, float]] = {}
        self._access_order: deque[str] = deque()
        self._max_size = max_size
        self._ttl = ttl
        self._pending: set[str] = set()

        # Connect the internal signal so the actual grab runs on the main GUI thread
        self._request_grab.connect(self._do_grab_on_main_thread)

        _log("Initialized native Qt grabber")

    @property
    def available(self) -> bool:
        return True  # Native Qt is always available

    # ── Cache access ─────────────────────────────────────────────────

    def get(self, win_id: str) -> Optional[QPixmap]:
        if win_id in self._cache:
            pix, ts = self._cache[win_id]
            if time.time() - ts < self._ttl:
                if win_id in self._access_order:
                    self._access_order.remove(win_id)
                self._access_order.append(win_id)
                return pix
            else:
                del self._cache[win_id]
        return None

    def put(self, win_id: str, pix: QPixmap):
        if len(self._cache) >= self._max_size:
            oldest = self._access_order.popleft()
            self._cache.pop(oldest, None)
        self._cache[win_id] = (pix, time.time())
        if win_id in self._access_order:
            self._access_order.remove(win_id)
        self._access_order.append(win_id)

    # ── Async capture ────────────────────────────────────────────────

    def capture_async(self, win_id: str, thumb_size: tuple[int, int] = (220, 165)):
        """Request a capture. The actual grab happens on the main thread."""
        cached = self.get(win_id)
        if cached:
            _log(f"Cache hit: {win_id}")
            self.thumbnail_ready.emit(win_id, cached)
            return

        if win_id in self._pending:
            return
        self._pending.add(win_id)

        # We emit a signal to bump the work to the main thread's event loop
        # so it doesn't freeze the caller right now, but still executes correctly.
        def _worker():
            self._request_grab.emit(win_id, thumb_size[0], thumb_size[1])

        threading.Thread(target=_worker, daemon=True).start()

    def _do_grab_on_main_thread(self, win_id: str, w: int, h: int):
        """Runs on the MAIN thread to safely invoke grabWindow and scale."""
        try:
            # Convert hex string (e.g. 0x044000e5) to integer for grabWindow
            wid_int = int(win_id, 16)
            
            screen = QGuiApplication.primaryScreen()
            if not screen:
                raise RuntimeError("No primary screen found")

            # Native Qt X11 window grab
            pix = screen.grabWindow(wid_int)
            
            if not pix.isNull():
                scaled = pix.scaled(
                    w, h,
                    aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                    mode=Qt.TransformationMode.SmoothTransformation,
                )
                self.put(win_id, scaled)
                _log(f"✓ Native grab OK: {win_id} ({scaled.width()}x{scaled.height()})")
                self.thumbnail_ready.emit(win_id, scaled)
            else:
                _log(f"✗ Native grab returned null pixmap for {win_id}")

        except Exception as exc:
            _log(f"✗ Native grab error for {win_id}: {exc}")
        finally:
            self._pending.discard(win_id)

    def clear(self):
        self._cache.clear()
        self._access_order.clear()
