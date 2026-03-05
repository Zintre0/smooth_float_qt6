"""
ConfigDialog — live configuration panel with real-time cost meters.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QSlider, QPushButton, QProgressBar, QComboBox, QWidget, QMessageBox,
    QLineEdit,
)

from core.config import load_config, save_config, validate_config_schema
from core.cost_calculator import estimate_costs


# ── LabeledSlider ────────────────────────────────────────────────────

class LabeledSlider(QWidget):
    """Horizontal slider with a label and live value display."""

    def __init__(self, text, minv, maxv, step=1, initial=None, suffix="", parent=None):
        super().__init__(parent)
        self.suffix = suffix

        layout = QVBoxLayout(self)

        # Header row: label + current value
        self.lbl = QLabel(text)
        self.value_lbl = QLabel()
        header = QHBoxLayout()
        header.addWidget(self.lbl)
        header.addStretch()
        header.addWidget(self.value_lbl)
        layout.addLayout(header)

        # Slider
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(minv)
        self.slider.setMaximum(maxv)
        self.slider.setSingleStep(step)
        if initial is not None:
            self.slider.setValue(initial)
        layout.addWidget(self.slider)

        self._update_label(self.slider.value())
        self.slider.valueChanged.connect(self._update_label)

    def _update_label(self, v):
        self.value_lbl.setText(f"{v}{self.suffix}")

    def value(self):
        return self.slider.value()

    def setValue(self, v):
        self.slider.setValue(v)


# ── HotkeyCapture ────────────────────────────────────────────────────

# Map Qt modifier keys to pynput format tokens
_QT_MOD_MAP = {
    Qt.Key.Key_Control: "<ctrl>",
    Qt.Key.Key_Alt:     "<alt>",
    Qt.Key.Key_Shift:   "<shift>",
    Qt.Key.Key_Super_L: "<cmd>",
    Qt.Key.Key_Super_R: "<cmd>",
    Qt.Key.Key_Meta:    "<cmd>",
}

# Map Qt special keys to pynput names
_QT_SPECIAL_MAP = {
    Qt.Key.Key_Space:     "<space>",
    Qt.Key.Key_Tab:       "<tab>",
    Qt.Key.Key_Return:    "<enter>",
    Qt.Key.Key_Escape:    "<esc>",
    Qt.Key.Key_Backspace: "<backspace>",
    Qt.Key.Key_Delete:    "<delete>",
    Qt.Key.Key_F1:  "<f1>",  Qt.Key.Key_F2:  "<f2>",
    Qt.Key.Key_F3:  "<f3>",  Qt.Key.Key_F4:  "<f4>",
    Qt.Key.Key_F5:  "<f5>",  Qt.Key.Key_F6:  "<f6>",
    Qt.Key.Key_F7:  "<f7>",  Qt.Key.Key_F8:  "<f8>",
    Qt.Key.Key_F9:  "<f9>",  Qt.Key.Key_F10: "<f10>",
    Qt.Key.Key_F11: "<f11>", Qt.Key.Key_F12: "<f12>",
}


class HotkeyCapture(QWidget):
    """A text field + button that records a key combination in pynput format.

    Click 'Grabar' then press the desired shortcut. The widget converts
    Qt key events into pynput-compatible strings like ``<alt>+space``.
    """

    def __init__(self, label: str, initial: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))

        self.line = QLineEdit(initial)
        self.line.setReadOnly(True)
        self.line.setPlaceholderText("Sin atajo")
        layout.addWidget(self.line)

        self.btn_record = QPushButton("Grabar")
        self.btn_record.setFixedWidth(70)
        self.btn_record.clicked.connect(self._start_recording)
        layout.addWidget(self.btn_record)

        self.btn_clear = QPushButton("✕")
        self.btn_clear.setFixedWidth(30)
        self.btn_clear.clicked.connect(self._clear)
        layout.addWidget(self.btn_clear)

        self._recording = False

    def value(self) -> str:
        return self.line.text().strip()

    def setValue(self, v: str):
        self.line.setText(v)

    def _start_recording(self):
        self._recording = True
        self.line.setText("Presiona la combinación…")
        self.line.setFocus()
        self.btn_record.setText("…")

    def _clear(self):
        self._recording = False
        self.line.setText("")
        self.btn_record.setText("Grabar")

    def keyPressEvent(self, event):
        if not self._recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        # Ignore bare modifier presses — wait for the actual key
        if key in _QT_MOD_MAP:
            return

        parts = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("<ctrl>")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("<alt>")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("<shift>")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("<cmd>")

        # Convert the key itself
        if key in _QT_SPECIAL_MAP:
            parts.append(_QT_SPECIAL_MAP[key])
        else:
            ch = event.text().strip().lower()
            if ch:
                parts.append(ch)
            else:
                # Fallback: try QKeySequence
                seq = QKeySequence(key).toString().lower()
                if seq:
                    parts.append(seq)

        hotkey = "+".join(parts) if parts else ""
        self.line.setText(hotkey)
        self._recording = False
        self.btn_record.setText("Grabar")


# ── ConfigDialog ─────────────────────────────────────────────────────

class ConfigDialog(QDialog):
    """Settings dialog with live CPU/GPU/RAM cost estimations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración – smooth_float_qt6-v7")
        self.setMinimumWidth(520)

        self.cfg = load_config("config.json")
        validate_config_schema(self.cfg)

        main = QVBoxLayout(self)

        # ── Graphics section ──
        g = self.cfg["graphics"]
        self.sl_ring = LabeledSlider(
            "Tamaño del ring", 400, 1200, step=10,
            initial=int(g["ring_size"]), suffix=" px",
        )
        self.sl_hub = LabeledSlider(
            "Radio del hub", 100, 300, step=5,
            initial=int(g["hub_radius"]), suffix=" px",
        )
        self.sl_node = LabeledSlider(
            "Radio del nodo", 8, 40, step=1,
            initial=int(g["node_radius"]), suffix=" px",
        )
        self.sl_icon = LabeledSlider(
            "Tamaño icono hub", 20, 96, step=2,
            initial=int(g["hub_icon_size"]), suffix=" px",
        )
        self.sl_spoke = LabeledSlider(
            "Longitud spokes", 40, 150, step=2,
            initial=int(g["spoke_length"]), suffix=" px",
        )

        main.addWidget(QLabel("── Gráficos ──"))
        for w in (self.sl_ring, self.sl_hub, self.sl_node, self.sl_icon, self.sl_spoke):
            main.addWidget(w)

        # ── Performance section ──
        p = self.cfg["performance"]
        self.sl_fps = LabeledSlider(
            "FPS máximos", 30, 165, step=5,
            initial=int(p["max_fps"]), suffix=" fps",
        )
        self.sl_peek = LabeledSlider(
            "Retardo peek", 0, 600, step=25,
            initial=int(p["peek_delay"]), suffix=" ms",
        )
        self.cb_batch = QCheckBox("Batch render (optimización)")
        self.cb_batch.setChecked(bool(p["enable_batch_render"]))
        self.cb_cache = QCheckBox("Cache habilitado")
        self.cb_cache.setChecked(bool(p["enable_cache"]))
        self.cb_gpu = QCheckBox("GPU accel (indicador)")
        self.cb_gpu.setChecked(bool(p["gpu_accel"]))

        main.addSpacing(8)
        main.addWidget(QLabel("── Performance ──"))
        for w in (self.sl_fps, self.sl_peek, self.cb_batch, self.cb_cache, self.cb_gpu):
            main.addWidget(w)

        # ── Animations section ──
        a = self.cfg["animations"]
        self.cb_ring_in = QCheckBox("Animación de entrada del ring")
        self.cb_ring_in.setChecked(bool(a["ring_entrance"]))
        self.cmb_style = QComboBox()
        self.cmb_style.addItems(["elastic", "cubic"])
        self.cmb_style.setCurrentText(str(a.get("ring_style", "elastic")))
        self.sl_pulse = LabeledSlider(
            "Velocidad pulso botón", 1, 100, step=1,
            initial=int(float(a["pulse_speed"]) * 1000), suffix=" ×1e-3",
        )
        self.sl_fade = LabeledSlider(
            "Duración fade ring", 100, 1000, step=25,
            initial=int(a["fade_duration"]), suffix=" ms",
        )
        self.cb_shock = QCheckBox("Shockwave (visual)")
        self.cb_shock.setChecked(bool(a["shockwave"]))

        main.addSpacing(8)
        main.addWidget(QLabel("── Animaciones ──"))
        style_row = QHBoxLayout()
        style_row.addWidget(self.cb_ring_in)
        style_row.addWidget(QLabel("Estilo:"))
        style_row.addWidget(self.cmb_style)
        main.addLayout(style_row)
        for w in (self.sl_pulse, self.sl_fade, self.cb_shock):
            main.addWidget(w)

        # ── Behavior section ──
        b = self.cfg.get("behavior", {})
        self.cb_snap = QCheckBox("Snap a bordes de pantalla")
        self.cb_snap.setChecked(bool(b.get("snap_to_edges", True)))
        self.sl_snap_thr = LabeledSlider(
            "Umbral de snap", 5, 80, step=5,
            initial=int(b.get("snap_threshold", 25)), suffix=" px",
        )
        self.cb_smart_pos = QCheckBox("Recordar posición al cerrar")
        self.cb_smart_pos.setChecked(bool(b.get("smart_position", True)))
        self.cb_kbd = QCheckBox("Navegación por teclado")
        self.cb_kbd.setChecked(bool(b.get("keyboard_nav", True)))

        # Global hotkey capture
        self.hotkey_input = HotkeyCapture(
            "Atajo global:",
            initial=b.get("global_hotkey", "<alt>+<space>"),
        )

        # Peek mode selector
        peek_row = QHBoxLayout()
        peek_row.addWidget(QLabel("Modo peek:"))
        self.cmb_peek = QComboBox()
        self.cmb_peek.addItems(["raise", "thumbnail"])
        self.cmb_peek.setCurrentText(str(b.get("peek_mode", "raise")))
        self.cmb_peek.setToolTip(
            "raise = trae la ventana al frente\n"
            "thumbnail = captura y muestra una miniatura"
        )
        peek_row.addWidget(self.cmb_peek)

        main.addSpacing(8)
        main.addWidget(QLabel("── Comportamiento ──"))
        for w in (self.cb_snap, self.sl_snap_thr, self.cb_smart_pos, self.cb_kbd, self.hotkey_input):
            main.addWidget(w)
        main.addLayout(peek_row)

        # ── Cost meters ──
        self.pb_cpu = QProgressBar()
        self.pb_cpu.setFormat("CPU %p%")
        self.pb_gpu = QProgressBar()
        self.pb_gpu.setFormat("GPU %p%")
        self.pb_ram = QProgressBar()
        self.pb_ram.setFormat("RAM %p%")

        main.addSpacing(8)
        main.addWidget(QLabel("── Costos estimados ──"))
        main.addWidget(self.pb_cpu)
        main.addWidget(self.pb_gpu)
        main.addWidget(self.pb_ram)

        # ── Action buttons ──
        btns = QHBoxLayout()
        self.btn_apply = QPushButton("Guardar")
        self.btn_cancel = QPushButton("Cancelar")
        btns.addStretch()
        btns.addWidget(self.btn_apply)
        btns.addWidget(self.btn_cancel)
        main.addLayout(btns)

        # ── Connect signals ──
        for sl in (
            self.sl_ring, self.sl_hub, self.sl_node, self.sl_icon, self.sl_spoke,
            self.sl_fps, self.sl_peek, self.sl_pulse, self.sl_fade, self.sl_snap_thr,
        ):
            sl.slider.valueChanged.connect(self._refresh_costs)

        for cb in (
            self.cb_batch, self.cb_cache, self.cb_gpu,
            self.cb_ring_in, self.cb_shock,
            self.cb_snap, self.cb_smart_pos, self.cb_kbd,
        ):
            cb.stateChanged.connect(self._refresh_costs)

        self.cmb_style.currentTextChanged.connect(self._refresh_costs)
        self.btn_apply.clicked.connect(self._save)
        self.btn_cancel.clicked.connect(self.reject)

        self._refresh_costs()

    # ── Helpers ──────────────────────────────────────────────────────

    def _current_cfg(self) -> dict:
        """Build a config dict from the current widget values."""
        cfg = load_config("config.json")  # start from defaults + file

        cfg["graphics"]["ring_size"]     = int(self.sl_ring.value())
        cfg["graphics"]["hub_radius"]    = int(self.sl_hub.value())
        cfg["graphics"]["node_radius"]   = int(self.sl_node.value())
        cfg["graphics"]["hub_icon_size"] = int(self.sl_icon.value())
        cfg["graphics"]["spoke_length"]  = int(self.sl_spoke.value())

        cfg["performance"]["max_fps"]           = int(self.sl_fps.value())
        cfg["performance"]["peek_delay"]        = int(self.sl_peek.value())
        cfg["performance"]["enable_batch_render"] = bool(self.cb_batch.isChecked())
        cfg["performance"]["enable_cache"]      = bool(self.cb_cache.isChecked())
        cfg["performance"]["gpu_accel"]         = bool(self.cb_gpu.isChecked())

        cfg["animations"]["ring_entrance"] = bool(self.cb_ring_in.isChecked())
        cfg["animations"]["ring_style"]    = self.cmb_style.currentText()
        cfg["animations"]["pulse_speed"]   = round(self.sl_pulse.value() / 1000.0, 3)
        cfg["animations"]["fade_duration"] = int(self.sl_fade.value())
        cfg["animations"]["shockwave"]     = bool(self.cb_shock.isChecked())

        if "behavior" not in cfg:
            cfg["behavior"] = {}
        cfg["behavior"]["snap_to_edges"]  = bool(self.cb_snap.isChecked())
        cfg["behavior"]["snap_threshold"] = int(self.sl_snap_thr.value())
        cfg["behavior"]["smart_position"] = bool(self.cb_smart_pos.isChecked())
        cfg["behavior"]["keyboard_nav"]   = bool(self.cb_kbd.isChecked())
        cfg["behavior"]["global_hotkey"]   = self.hotkey_input.value()
        cfg["behavior"]["peek_mode"]       = self.cmb_peek.currentText()

        return cfg

    def _refresh_costs(self):
        cfg = self._current_cfg()
        costs = estimate_costs(cfg)
        self.pb_cpu.setValue(int(costs["cpu_pct"]))
        self.pb_gpu.setValue(int(costs["gpu_pct"]))
        self.pb_ram.setValue(int(costs["ram_pct"]))

    def _save(self):
        cfg = self._current_cfg()
        ok, msg = validate_config_schema(cfg)
        if not ok:
            QMessageBox.critical(self, "Error de configuración", msg)
            return
        save_config(cfg, "config.json")
        self.accept()
