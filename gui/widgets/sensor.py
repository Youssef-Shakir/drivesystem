"""
Sensor status widget.

Displays sensor connection status and current distance reading.
Windows XP style with large, visible elements.
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt

from ..theme import COLORS, xp_status_badge_style


class SensorWidget(QFrame):
    """
    Sensor status display with distance bar.
    XP-style panel with clear status indicators.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_card']};
                border: 2px groove {COLORS['border']};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # XP-style title bar
        title_bar = QLabel("  Ultrasonic Sensor")
        title_bar.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0058EE, stop:0.03 #3A6EA5, stop:0.08 #0054E3,
                stop:0.92 #0054E3, stop:0.97 #003399, stop:1 #002266);
            color: white;
            font-weight: bold;
            font-size: 12px;
            font-family: "Trebuchet MS", "Tahoma", sans-serif;
            padding: 6px;
            border: none;
        """)
        title_bar.setFixedHeight(28)
        main_layout.addWidget(title_bar)

        # Content
        content = QFrame()
        content.setStyleSheet(f"background-color: {COLORS['bg_card']}; border: none;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Status row
        status_row = QHBoxLayout()

        status_label = QLabel("Status:")
        status_label.setStyleSheet(f"""
            font-size: 12px;
            font-weight: bold;
            color: {COLORS['text_primary']};
            font-family: "Tahoma", sans-serif;
        """)
        status_row.addWidget(status_label)

        self.status_badge = QLabel("UNKNOWN")
        self._set_badge_style("unknown")
        status_row.addWidget(self.status_badge)

        status_row.addStretch()

        # Large distance display
        self.distance_label = QLabel("--- cm")
        self.distance_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 32px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
        """)
        status_row.addWidget(self.distance_label)

        layout.addLayout(status_row)

        # Distance bar with XP styling
        bar_frame = QFrame()
        bar_frame.setStyleSheet(f"""
            background-color: {COLORS['bg_primary']};
            border: 2px inset {COLORS['border']};
            padding: 4px;
        """)
        bar_layout = QVBoxLayout(bar_frame)
        bar_layout.setContentsMargins(4, 4, 4, 4)

        self.distance_bar = QProgressBar()
        self.distance_bar.setRange(0, 400)
        self.distance_bar.setValue(0)
        self.distance_bar.setTextVisible(True)
        self.distance_bar.setFormat("%v cm")
        self.distance_bar.setFixedHeight(28)
        self.distance_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                text-align: center;
                font-weight: bold;
                font-size: 11px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6699FF, stop:0.5 #3366DD, stop:1 #0054E3);
            }}
        """)
        bar_layout.addWidget(self.distance_bar)

        layout.addWidget(bar_frame)

        # Threshold indicator with XP look
        threshold_frame = QHBoxLayout()
        threshold_frame.addStretch()

        threshold_icon = QLabel("\u25BC")
        threshold_icon.setStyleSheet("color: #CC0000; font-size: 14px; font-weight: bold;")
        threshold_frame.addWidget(threshold_icon)

        self.threshold_label = QLabel("Detection threshold: 150 cm")
        self.threshold_label.setStyleSheet(f"""
            color: #CC0000;
            font-size: 11px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
        """)
        threshold_frame.addWidget(self.threshold_label)

        layout.addLayout(threshold_frame)
        main_layout.addWidget(content)

    def _set_badge_style(self, status: str):
        """Update badge appearance based on status."""
        if status == "online":
            self.status_badge.setText("ONLINE")
            self.status_badge.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #00FF00, stop:0.5 #00CC00, stop:1 #009900);
                color: white;
                padding: 4px 12px;
                border: 2px outset #00CC00;
                font-size: 11px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            """)
        elif status == "offline":
            self.status_badge.setText("OFFLINE")
            self.status_badge.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF6666, stop:0.5 #CC0000, stop:1 #990000);
                color: white;
                padding: 4px 12px;
                border: 2px outset #CC0000;
                font-size: 11px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            """)
        else:
            self.status_badge.setText("UNKNOWN")
            self.status_badge.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFF99, stop:0.5 #FFCC00, stop:1 #CC9900);
                color: black;
                padding: 4px 12px;
                border: 2px outset #FFCC00;
                font-size: 11px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            """)

    def set_status(self, status: str, distance: int):
        """Update sensor status and distance."""
        self.distance_label.setText(f"{distance} cm")
        self.distance_bar.setValue(min(400, distance))
        self._set_badge_style(status)

    def set_threshold(self, threshold_cm: int):
        """Update the displayed threshold value."""
        self.threshold_label.setText(f"Detection threshold: {threshold_cm} cm")
