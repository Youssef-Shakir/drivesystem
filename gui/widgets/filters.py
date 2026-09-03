"""
Audio filter control widgets.

Controls for configuring audio processing filters.
Windows XP style with clear controls.
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QSlider, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..theme import COLORS


class FilterControlWidget(QFrame):
    """
    Single filter control - XP style with enable toggle and sliders.
    """

    settings_changed = pyqtSignal(str, dict)

    def __init__(self, name: str, filter_id: str, params: list, parent=None):
        super().__init__(parent)
        self.name = name
        self.filter_id = filter_id
        self.params = params
        self.param_sliders: dict[str, QSlider] = {}
        self.param_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            background-color: {COLORS['bg_card']};
            border: 2px groove {COLORS['border']};
            margin-bottom: 4px;
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header bar
        header = QFrame()
        header.setStyleSheet(f"""
            background-color: {COLORS['bg_primary']};
            border: none;
            border-bottom: 1px solid {COLORS['border']};
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)

        self.enable_cb = QCheckBox()
        self.enable_cb.setChecked(True)
        self.enable_cb.setStyleSheet("""
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: white;
                border: 2px inset #808080;
            }
            QCheckBox::indicator:checked {
                background-color: white;
                border: 2px inset #808080;
                image: url(data:image/png;base64,);
            }
        """)
        header_layout.addWidget(self.enable_cb)

        title = QLabel(self.name)
        title.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 12px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.status_label = QLabel("ON")
        self.status_label.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #00FF00, stop:0.5 #00CC00, stop:1 #009900);
            color: white;
            padding: 2px 8px;
            border: 1px outset #00CC00;
            font-size: 10px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
        """)
        header_layout.addWidget(self.status_label)

        layout.addWidget(header)

        # Parameters area
        self.params_widget = QFrame()
        self.params_widget.setStyleSheet(f"background-color: {COLORS['bg_card']}; border: none;")
        params_layout = QVBoxLayout(self.params_widget)
        params_layout.setContentsMargins(12, 8, 12, 8)
        params_layout.setSpacing(6)

        for param_name, param_id, min_val, max_val, default, unit in self.params:
            row = QHBoxLayout()

            label = QLabel(f"{param_name}:")
            label.setFixedWidth(90)
            label.setStyleSheet(f"""
                color: {COLORS['text_primary']};
                font-size: 11px;
                font-family: "Tahoma", sans-serif;
            """)
            row.addWidget(label)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(min_val, max_val)
            slider.setValue(default)
            slider.setFixedHeight(24)
            slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #808080, stop:0.3 #C0C0C0, stop:1 #FFFFFF);
                    height: 6px;
                    border: 1px inset #808080;
                }
                QSlider::handle:horizontal {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #FFFFFF, stop:0.4 #F0F0F0, stop:0.5 #E0E0E0, stop:1 #C8C8C8);
                    width: 16px;
                    margin: -5px 0;
                    border: 2px outset #D4D0C8;
                }
                QSlider::handle:horizontal:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #FFFFFF, stop:0.4 #E8E8FF, stop:0.5 #D8D8F0, stop:1 #C0C0E0);
                    border: 2px outset #8080C0;
                }
                QSlider::sub-page:horizontal {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #0054E3, stop:0.5 #3169C6, stop:1 #6699FF);
                    border: 1px solid #003399;
                }
            """)
            row.addWidget(slider, 1)

            value_label = QLabel(f"{default} {unit}")
            value_label.setFixedWidth(70)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            value_label.setStyleSheet(f"""
                color: #000080;
                font-size: 11px;
                font-weight: bold;
                font-family: "Courier New", monospace;
                background-color: #E8E8E8;
                border: 1px solid {COLORS['border']};
                padding: 2px 4px;
            """)
            row.addWidget(value_label)

            slider.valueChanged.connect(
                lambda v, lbl=value_label, u=unit: lbl.setText(f"{v} {u}")
            )
            slider.valueChanged.connect(self._emit_settings_changed)

            self.param_sliders[param_id] = slider
            self.param_labels[param_id] = value_label
            params_layout.addLayout(row)

        layout.addWidget(self.params_widget)

        # Connect enable checkbox
        self.enable_cb.toggled.connect(self._on_enable_toggled)
        self.enable_cb.toggled.connect(self._emit_settings_changed)

    def _on_enable_toggled(self, enabled: bool):
        """Handle enable checkbox toggle."""
        self.params_widget.setEnabled(enabled)
        if enabled:
            self.status_label.setText("ON")
            self.status_label.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #00FF00, stop:0.5 #00CC00, stop:1 #009900);
                color: white; padding: 2px 8px;
                border: 1px outset #00CC00;
                font-size: 10px; font-weight: bold;
                font-family: "Tahoma", sans-serif;
            """)
        else:
            self.status_label.setText("OFF")
            self.status_label.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C0C0C0, stop:0.5 #808080, stop:1 #606060);
                color: white; padding: 2px 8px;
                border: 1px inset #808080;
                font-size: 10px; font-weight: bold;
                font-family: "Tahoma", sans-serif;
            """)

    def _emit_settings_changed(self):
        self.settings_changed.emit(self.filter_id, self.get_settings())

    def get_settings(self) -> dict:
        settings = {"enabled": self.enable_cb.isChecked()}
        for param_id, slider in self.param_sliders.items():
            settings[param_id] = slider.value()
        return settings

    def set_settings(self, settings: dict):
        if "enabled" in settings:
            self.enable_cb.setChecked(settings["enabled"])

        for param_id, slider in self.param_sliders.items():
            if param_id in settings:
                slider.blockSignals(True)
                slider.setValue(int(settings[param_id]))
                slider.blockSignals(False)
                if param_id in self.param_labels:
                    unit = ""
                    for p in self.params:
                        if p[1] == param_id:
                            unit = p[5]
                            break
                    self.param_labels[param_id].setText(f"{settings[param_id]} {unit}")

    def is_enabled(self) -> bool:
        return self.enable_cb.isChecked()

    def set_enabled(self, enabled: bool):
        self.enable_cb.setChecked(enabled)
