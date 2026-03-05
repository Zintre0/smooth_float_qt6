# Smooth Floating Button v7 — LXQt/Openbox Edition

A smooth floating button that expands into a radial ring of application windows.
Features smart grouping, smooth animations, multi-monitor support, keyboard navigation,
configurable global hotkey, window thumbnail previews, and a live configuration dialog.

> **Tested on:** Lubuntu 25.04 · LXQt · Openbox · X11

## Features

- **Radial Ring UI** — windows arranged in a circle, grouped by application
- **Smart Grouping** — browsers, terminals, editors automatically consolidated
- **PWA Support** — `crx_` windows (Outlook, Teams, WhatsApp Web) detected by title
- **Smooth Animations** — elastic/cubic easing on ring entrance with breathing pulse
- **Shockwave Effect** — optional ripple on ring open
- **Multi-Monitor** — intelligently positions the ring on the correct screen
- **Keyboard Navigation** — Tab/Arrow keys to navigate, Enter to switch, Escape to close
- **Global Hotkey** — configurable shortcut (e.g. `<alt>+<space>`, `<cmd>+|`) to trigger the ring from anywhere
- **Peek on Hover** — hovering or keyboard-navigating a node previews the window
- **Peek Mode: raise** — brings the window briefly to the front
- **Peek Mode: thumbnail** — captures a live screenshot and shows it as a tooltip card
- **Edge Snapping** — button snaps magnetically to screen edges
- **Position Persistence** — remembers button location across sessions
- **Live Config Dialog** — sliders, checkboxes, and real-time CPU/GPU/RAM cost meters
- **Context Menu** — right-click for settings, config reload, cost display, and quit

## Requirements

### System Dependencies (Debian / Ubuntu / Lubuntu)

```bash
sudo apt install python3-pyside6.qtcore python3-pyside6.qtgui python3-pyside6.qtwidgets
sudo apt install wmctrl
```

### Python Dependencies

```bash
pip install -r requirements.txt
```

> `requirements.txt` includes `pynput` for global hotkey support.

## Usage

```bash
cd smooth_float_qt6_repo
python3 main.py
```

| Action | Result |
|---|---|
| Left Click | Open the window ring |
| Click & Drag | Move the floating button |
| Right Click | Context menu |
| Global Hotkey | Open the ring from anywhere |
| Arrow Keys / Tab | Navigate nodes in the ring |
| Enter / Space | Switch to selected window |
| Escape | Close the ring |

## Project Structure

```
smooth_float_qt6_repo/
├── main.py                   # Entry point
├── config.json               # User configuration (merged over safe defaults)
├── requirements.txt
├── README.md
├── core/
│   ├── config.py             # load/save/validate + deep-merge defaults
│   ├── cost_calculator.py    # CPU/GPU/RAM cost estimator
│   ├── window_manager.py     # wmctrl + smart grouping + PWA detection
│   ├── geometry.py           # Polar math for hub/node placement
│   ├── hotkey_manager.py     # pynput global hotkey → Qt signal
│   ├── thumbnail_cache.py    # Native Qt QScreen.grabWindow LRU cache
│   └── anim.py               # Easing helpers
└── ui/
    ├── ring_overlay.py       # Radial ring widget, peek logic, keyboard nav
    ├── floating_button.py    # Draggable button, edge snap, context menu
    └── config_dialog.py      # Live settings dialog with cost meters
```

## Configuration

All settings live in `config.json` and can also be changed live via right-click → *Configurar…*

| Section | Key | Description |
|---|---|---|
| `animations` | `ring_style` | `"elastic"` or `"cubic"` |
| `animations` | `pulse_speed` | Speed of the breathing pulse |
| `animations` | `fade_duration` | Ring entrance animation duration (ms) |
| `animations` | `shockwave` | Enable shockwave effect on open |
| `performance` | `max_fps` | Maximum repaint frame rate |
| `performance` | `peek_delay` | Milliseconds before peek activates on hover |
| `graphics` | `ring_size` | Ring diameter in pixels |
| `graphics` | `hub_radius` | Distance from center to app hubs |
| `graphics` | `spoke_length` | Distance from hub to window nodes |
| `graphics` | `button_size` | Floating button size in pixels |
| `behavior` | `global_hotkey` | pynput-format hotkey string, e.g. `<alt>+<space>` |
| `behavior` | `peek_mode` | `"raise"` (bring window forward) or `"thumbnail"` (capture preview) |
| `behavior` | `snap_threshold` | Pixels from edge to trigger snapping |
| `behavior` | `keyboard_nav` | Enable/disable keyboard navigation |
| `behavior` | `smart_position` | Remember button position across sessions |

## Debug Logging

Start with debug level 3 for verbose output:

```python
# In main.py, pass debug_level to HotkeyManager if needed
# Or just watch stderr for [HOTKEY] and [THUMB] prefixed lines
```

Three log levels:
- `L1` — errors / warnings
- `L2` — info (registration, start/stop)
- `L3` — verbose (every event, thread activity)

## Compatibility Notes

- **X11 only**: Uses `wmctrl` for window listing and `QScreen.grabWindow` for thumbnails
- **Wayland**: Not yet supported (thumbnail grab may return null)
- **pynput**: Must be installed for the global hotkey feature; app runs without it (hotkey silently disabled)
