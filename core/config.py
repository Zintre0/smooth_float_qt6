"""
Configuration management for smooth_float_qt6-v7.
Loads config.json, merges with safe defaults, validates, and saves.
"""

import json
from copy import deepcopy
from pathlib import Path

# ── Safe defaults ────────────────────────────────────────────────────
_DEFAULT = {
    "animations": {
        "ring_entrance": True,
        "ring_style": "elastic",       # "elastic" | "cubic"
        "pulse_speed": 0.040,
        "fade_duration": 350,          # ms
        "shockwave": False,
    },
    "performance": {
        "max_fps": 60,
        "enable_batch_render": True,
        "enable_cache": True,
        "peek_delay": 150,             # ms before peek activation
        "gpu_accel": True,
    },
    "graphics": {
        "ring_size": 780,
        "hub_radius": 190,
        "node_radius": 16,
        "hub_icon_size": 40,
        "spoke_length": 70,
        "button_size": 64,
        "node_border_width": 2.5,
    },
    "behavior": {
        "snap_to_edges": True,
        "snap_threshold": 25,          # px from edge to snap
        "smart_position": True,        # remember position across sessions
        "keyboard_nav": True,
        "global_hotkey": "<alt>+<space>", # pynput format: <alt>+<space>, <ctrl>+<alt>+r, etc.
        "peek_mode": "raise",          # "raise" (bring window forward) or "thumbnail" (show screenshot)
    },
    "costs": {
        "ring_size": 0.35,
        "hub_radius": 0.10,
        "node_radius": 0.18,
        "glow_effects": 0.25,
        "keyboard_nav": 0.02,
        "smart_grouping": 0.03,
        "shockwave": 0.12,
        "max_fps": 0.20,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    out = deepcopy(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_config(path: str = "config.json") -> dict:
    """Load user config from *path* and merge with safe defaults.

    If the file is missing or corrupt, defaults are returned silently.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            user_cfg = json.load(fh)
    except FileNotFoundError:
        return deepcopy(_DEFAULT)
    except Exception:
        return deepcopy(_DEFAULT)
    return deep_merge(_DEFAULT, user_cfg)


def validate_config_schema(cfg: dict) -> tuple[bool, str]:
    """Validate the basic structure of *cfg*.

    Returns ``(True, "ok")`` or ``(False, reason)``.
    """
    required_top = ["animations", "performance", "graphics", "costs"]
    for key in required_top:
        if key not in cfg or not isinstance(cfg[key], dict):
            return False, f"Missing or invalid section: {key}"

    if not isinstance(cfg["performance"].get("max_fps", 60), int):
        return False, "performance.max_fps must be int"

    for field in ("ring_size", "hub_radius", "node_radius", "hub_icon_size", "spoke_length"):
        if field not in cfg["graphics"]:
            return False, f"graphics.{field} is required"

    return True, "ok"


def save_config(cfg: dict, path: str = "config.json") -> bool:
    """Write *cfg* to *path* with pretty-print indentation."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return True
