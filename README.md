# Smooth Floating Button - Advanced LXQt/Openbox Edition

A smooth floating button that expands into a ring of application windows when clicked. Features multi-monitor support, keyboard navigation, persistence, and smart grouping.

## Features

- **Smooth Animations:** Fluid entrance and exit animations for the ring menu.
- **Smart Grouping:** Groups windows of the same application together.
- **Multi-Monitor Support:** Intelligently positions the ring on the correct screen.
- **Keyboard Navigation:** Navigate through windows using arrow keys or Tab.
- **Persistence:** Remembers the floating button's position.
- **Edge Snapping:** Button snaps to screen edges for easy access.
- **Customizable:** Configuration available in the code (will be moved to external config in future).

## Requirements

### System Dependencies (Debian/Ubuntu/Linux Mint)

```bash
sudo apt install wmctrl xdotool
```

### Python Dependencies

```bash
pip install -r requirements.txt
```

## Usage

Run the script:

```bash
python main.py
```

- **Left Click:** Open the window ring.
- **Click & Drag:** Move the floating button.
- **Right Click:** Open context menu (Quit).
- **Keyboard:**
    - `Arrow Keys` / `Tab`: Navigate windows in the ring.
    - `Enter` / `Space`: Switch to selected window.
    - `Escape`: Close the ring.

## Configuration

Configuration options can be found at the top of `main.py` in the `CONFIG` dictionary.
