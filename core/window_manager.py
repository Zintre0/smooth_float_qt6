"""
Window detection and smart grouping via wmctrl.
"""

import subprocess
from collections import defaultdict


# ── App-name normalization ───────────────────────────────────────────

# Explicit class → display-name mapping for common apps
_APP_MAP: dict[str, str] = {
    "brave-browser": "Brave",
    "firefox":       "Firefox",
    "google-chrome": "Chrome",
    "chromium":      "Chromium",
    "code":          "Code",
    "vscodium":      "Code",
    "qterminal":     "Terminal",
    "konsole":       "Terminal",
    "gnome-terminal":"Terminal",
    "xfce4-terminal":"Terminal",
    "terminator":    "Terminal",
    "alacritty":     "Terminal",
    "kitty":         "Terminal",
    "pcmanfm-qt":    "Files",
    "pcmanfm":       "Files",
    "dolphin":       "Files",
    "nautilus":      "Files",
    "thunar":        "Files",
}

# Window classes to silently ignore
_IGNORE_CLASSES: set[str] = {
    "pcmanfm-desktop", "xfdesktop", "lxqt-panel",
    "desktop_window", "plank", "cairo-dock", "conky",
}

_IGNORE_TITLES: set[str] = {"float", "floating button", "desktop", "desplegar"}


def _extract_pwa_name(title: str) -> str:
    """Extract a clean app name from a PWA window title.

    Examples:
        "Outlook (PWA)"                              → "Outlook"
        "Microsoft Teams (PWA) - (2) Chat | ..."     → "Teams"
        "WhatsApp Web"                               → "WhatsApp"
        "Spotify - Some Song"                        → "Spotify"

    Falls back to the first word of the title if nothing better is found.
    """
    # Strip "(PWA)" marker if present
    clean = title
    pwa_idx = clean.find("(PWA)")
    if pwa_idx >= 0:
        clean = clean[:pwa_idx].strip()

    # Remove trailing " - ..." suffix (subtitle)
    dash_idx = clean.find(" - ")
    if dash_idx >= 0:
        clean = clean[:dash_idx].strip()

    # Remove trailing " | ..." suffix
    pipe_idx = clean.find(" | ")
    if pipe_idx >= 0:
        clean = clean[:pipe_idx].strip()

    # Shorten multi-word names: "Microsoft Teams" → "Teams"
    words = clean.split()
    if len(words) > 1:
        # Keep last meaningful word (usually the product name)
        return words[-1]

    return clean if clean else title.split()[0] if title.strip() else "PWA"


def _normalize_app_name(name: str) -> str:
    """Consolidate app names so browsers / editors / terminals group together."""
    low = name.lower()

    # Check explicit map first
    if low in _APP_MAP:
        return _APP_MAP[low]

    # Heuristic grouping
    if any(x in low for x in ("brave", "firefox", "chrome", "chromium", "edge")):
        if "brave" in low:
            return "Brave"
        if "firefox" in low:
            return "Firefox"
        if "chrome" in low:
            return "Chrome"

    if any(x in low for x in ("code", "vscode", "vscodium")):
        return "Code"

    if any(x in low for x in ("terminal", "konsole", "qterminal", "gnome-terminal", "terminator", "alacritty", "kitty")):
        return "Terminal"

    return name


# ── Public API ───────────────────────────────────────────────────────

def list_windows() -> list[dict]:
    """Return a list of ``{id, app, title}`` dicts for open application windows.

    Uses ``wmctrl -lx``.  Returns an empty list if wmctrl is unavailable.
    """
    try:
        result = subprocess.run(
            ["wmctrl", "-lx"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return []

    windows: list[dict] = []

    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue

        parts = line.split(None, 4)
        if len(parts) < 5:
            continue

        win_id  = parts[0]
        desktop = parts[1]
        full_class = parts[2]                      # e.g. "crx_abc123.Brave"
        win_class = full_class.split(".")[0].lower() # e.g. "crx_abc123"
        title   = parts[4].strip()

        # Skip desktop & panel windows
        if desktop == "-1":
            continue
        if win_class in _IGNORE_CLASSES:
            continue
        if any(ign in title.lower() for ign in _IGNORE_TITLES):
            continue
        if not title:
            continue

        # PWA windows: crx_ prefix → extract app name from the title
        if win_class.startswith("crx_"):
            app_name = _extract_pwa_name(title)
        else:
            app_name = _APP_MAP.get(win_class, win_class.capitalize())

        windows.append({
            "id":    win_id,
            "app":   app_name,
            "title": title,
        })

    return windows


def smart_group(windows: list[dict]) -> dict[str, list[dict]]:
    """Group *windows* by normalized application name."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for win in windows:
        key = _normalize_app_name(win.get("app", "App"))
        groups[key].append(win)
    return dict(groups)
