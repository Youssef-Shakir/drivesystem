"""
Audio control widgets.

Volume sliders, mute buttons, and level meters.
Windows XP style with clear controls.
"""

import math

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..theme import COLORS, xp_slider_style


class AudioMeterWidget(QFrame):
    """
    Audio level meter - XP style with LED-like display.
    """

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.level = 0.0
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            background-color: {COLORS['bg_primary']};
            border: 1px solid {COLORS['border']};
            padding: 4px;
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        # Label
        self.label = QLabel(self.name)
        self.label.setFixedWidth(100)
        self.label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 12px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
        """)
        layout.addWidget(self.label)

        # Meter bar - LED style
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setValue(0)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(22)
        self.meter.setStyleSheet("""
            QProgressBar {
                background-color: #202020;
                border: 2px inset #808080;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00FF00, stop:0.6 #00FF00,
                    stop:0.7 #FFFF00, stop:0.85 #FFFF00,
                    stop:0.9 #FF0000, stop:1 #FF0000);
            }
        """)
        layout.addWidget(self.meter, 1)

        # dB label - LED style
        self.db_label = QLabel("-99 dB")
        self.db_label.setFixedWidth(60)
        self.db_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.db_label.setStyleSheet("""
            color: #00FF00;
            font-size: 11px;
            font-weight: bold;
            font-family: "Courier New", monospace;
            background-color: #000000;
            border: 1px inset #808080;
            padding: 2px;
        """)
        layout.addWidget(self.db_label)

    def set_level(self, level: float):
        """Set the meter level (0.0 to 1.0)."""
        self.level = max(0.0, min(1.0, level))
        self.meter.setValue(int(self.level * 100))

        if level < 0.01:
            self.db_label.setText("-99 dB")
            self.db_label.setStyleSheet("""
                color: #00FF00;
                font-size: 11px; font-weight: bold;
                font-family: "Courier New", monospace;
                background-color: #000000;
                border: 1px inset #808080; padding: 2px;
            """)
        else:
            db = 20 * math.log10(level)
            self.db_label.setText(f"{db:+.0f} dB")
            # Color based on level
            if level > 0.9:
                color = "#FF0000"
            elif level > 0.7:
                color = "#FFFF00"
            else:
                color = "#00FF00"
            self.db_label.setStyleSheet(f"""
                color: {color};
                font-size: 11px; font-weight: bold;
                font-family: "Courier New", monospace;
                background-color: #000000;
                border: 1px inset #808080; padding: 2px;
            """)


class VolumeControlWidget(QFrame):
    """
    Volume slider with mute button - XP style.
    """

    volume_changed = pyqtSignal(str, float)
    mute_changed = pyqtSignal(str, bool)

    def __init__(self, name: str, device_id: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.device_id = device_id
        self.muted = False
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            background-color: {COLORS['bg_primary']};
            border: 1px solid {COLORS['border']};
            padding: 6px;
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Header with mute button
        header = QHBoxLayout()

        self.mute_btn = QPushButton("Sound ON")
        self.mute_btn.setFixedSize(90, 28)
        self.mute_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7FD37F, stop:0.4 #5ABF5A, stop:0.5 #3C9A36, stop:1 #2D7D2D);
                color: white;
                border: 2px outset #5ABF5A;
                font-size: 10px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8FE38F, stop:0.4 #6ACF6A, stop:0.5 #4CAA46, stop:1 #3D8D3D);
            }
        """)
        self.mute_btn.clicked.connect(self._toggle_mute)
        header.addWidget(self.mute_btn)

        self.label = QLabel(self.name)
        self.label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 13px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
        """)
        header.addWidget(self.label)

        header.addStretch()

        self.value_label = QLabel("100%")
        self.value_label.setStyleSheet(f"""
            color: #000080;
            font-size: 14px;
            font-weight: bold;
            font-family: "Courier New", monospace;
            background-color: #E8E8E8;
            border: 1px solid {COLORS['border']};
            padding: 2px 8px;
        """)
        header.addWidget(self.value_label)

        layout.addLayout(header)

        # Slider with XP styling
        slider_frame = QFrame()
        slider_frame.setStyleSheet(f"""
            background-color: {COLORS['bg_card']};
            border: 2px inset {COLORS['border']};
            padding: 4px;
        """)
        slider_layout = QHBoxLayout(slider_frame)
        slider_layout.setContentsMargins(8, 4, 8, 4)

        min_label = QLabel("0")
        min_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        slider_layout.addWidget(min_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 150)
        self.slider.setValue(100)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #808080, stop:0.3 #C0C0C0, stop:1 #FFFFFF);
                height: 8px;
                border: 1px inset #808080;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.4 #F0F0F0, stop:0.5 #E0E0E0, stop:1 #C8C8C8);
                width: 20px;
                margin: -6px 0;
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
        self.slider.valueChanged.connect(self._on_value_changed)
        slider_layout.addWidget(self.slider, 1)

        max_label = QLabel("150")
        max_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
        slider_layout.addWidget(max_label)

        layout.addWidget(slider_frame)

    def _on_value_changed(self, value: int):
        self.value_label.setText(f"{value}%")
        self.volume_changed.emit(self.device_id, value / 100.0)

    def _toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            self.mute_btn.setText("MUTED")
            self.mute_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #FF6666, stop:0.4 #DD3333, stop:0.5 #CC0000, stop:1 #990000);
                    color: white;
                    border: 2px inset #CC0000;
                    font-size: 10px;
                    font-weight: bold;
                    font-family: "Tahoma", sans-serif;
                }
            """)
        else:
            self.mute_btn.setText("Sound ON")
            self.mute_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #7FD37F, stop:0.4 #5ABF5A, stop:0.5 #3C9A36, stop:1 #2D7D2D);
                    color: white;
                    border: 2px outset #5ABF5A;
                    font-size: 10px;
                    font-weight: bold;
                    font-family: "Tahoma", sans-serif;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #8FE38F, stop:0.4 #6ACF6A, stop:0.5 #4CAA46, stop:1 #3D8D3D);
                }
            """)
        self.mute_changed.emit(self.device_id, self.muted)

    def set_volume(self, value: float):
        """Set volume without emitting signal."""
        self.slider.blockSignals(True)
        self.slider.setValue(int(value * 100))
        self.value_label.setText(f"{int(value * 100)}%")
        self.slider.blockSignals(False)

    def set_muted(self, muted: bool):
        """Set mute state without emitting signal."""
        self.muted = muted
        if muted:
            self.mute_btn.setText("MUTED")
            self.mute_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #FF6666, stop:0.4 #DD3333, stop:0.5 #CC0000, stop:1 #990000);
                    color: white; border: 2px inset #CC0000;
                    font-size: 10px; font-weight: bold; font-family: "Tahoma", sans-serif;
                }
            """)
        else:
            self.mute_btn.setText("Sound ON")
            self.mute_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #7FD37F, stop:0.4 #5ABF5A, stop:0.5 #3C9A36, stop:1 #2D7D2D);
                    color: white; border: 2px outset #5ABF5A;
                    font-size: 10px; font-weight: bold; font-family: "Tahoma", sans-serif;
                }
            """)

    def get_volume(self) -> float:
        """Get current volume (0.0-1.5)."""
        return self.slider.value() / 100.0

    def is_muted(self) -> bool:
        """Get current mute state."""
        return self.muted
