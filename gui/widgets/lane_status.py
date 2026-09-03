"""
Lane status indicator widget.

Shows car presence with icon, status text, and wait timer.
Windows XP style with large, visible elements.
"""

from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox
from PyQt6.QtCore import Qt

from ..theme import COLORS


class LaneStatusWidget(QFrame):
    """
    Large lane status indicator with car icon and timer.
    XP-style groupbox with prominent display.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.car_present = False
        self.car_arrived_at: Optional[datetime] = None
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
        title_bar = QLabel("  Drive-Thru Lane Status")
        title_bar.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0058EE, stop:0.03 #3A6EA5, stop:0.08 #0054E3,
                stop:0.92 #0054E3, stop:0.97 #003399, stop:1 #002266);
            color: white;
            font-weight: bold;
            font-size: 13px;
            font-family: "Trebuchet MS", "Tahoma", sans-serif;
            padding: 8px;
            border: none;
        """)
        title_bar.setFixedHeight(32)
        main_layout.addWidget(title_bar)

        # Content area
        content = QFrame()
        content.setStyleSheet(f"background-color: {COLORS['bg_card']}; border: none;")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(30)

        # Left side - Large status indicator
        left_panel = QFrame()
        left_panel.setStyleSheet(f"""
            background-color: {COLORS['bg_primary']};
            border: 2px inset {COLORS['border']};
        """)
        left_panel.setFixedSize(200, 200)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Status indicator light
        self.status_light = QLabel()
        self.status_light.setFixedSize(120, 120)
        self.status_light.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_light_empty()
        left_layout.addWidget(self.status_light, alignment=Qt.AlignmentFlag.AlignCenter)

        content_layout.addWidget(left_panel)

        # Right side - Status info
        right_panel = QFrame()
        right_panel.setStyleSheet(f"background-color: {COLORS['bg_card']}; border: none;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Status text - LARGE
        self.status_label = QLabel("LANE EMPTY")
        self.status_label.setStyleSheet(f"""
            font-size: 28px;
            font-weight: bold;
            color: {COLORS['text_primary']};
            font-family: "Tahoma", sans-serif;
        """)
        right_layout.addWidget(self.status_label)

        # Subtitle
        self.subtitle_label = QLabel("No vehicle detected")
        self.subtitle_label.setStyleSheet(f"""
            font-size: 14px;
            color: {COLORS['text_secondary']};
            font-family: "Tahoma", sans-serif;
            margin-top: 4px;
        """)
        right_layout.addWidget(self.subtitle_label)

        right_layout.addSpacing(20)

        # Timer display - VERY LARGE
        timer_frame = QFrame()
        timer_frame.setStyleSheet(f"""
            background-color: #000000;
            border: 3px inset {COLORS['border']};
            padding: 10px;
        """)
        timer_layout = QVBoxLayout(timer_frame)

        timer_title = QLabel("WAIT TIME")
        timer_title.setStyleSheet("""
            color: #00FF00;
            font-size: 11px;
            font-family: "Courier New", monospace;
            font-weight: bold;
        """)
        timer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        timer_layout.addWidget(timer_title)

        self.timer_label = QLabel("--:--")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet("""
            font-size: 56px;
            font-weight: bold;
            color: #00FF00;
            font-family: "Courier New", monospace;
            background: transparent;
            border: none;
        """)
        timer_layout.addWidget(self.timer_label)

        right_layout.addWidget(timer_frame)
        right_layout.addStretch()

        content_layout.addWidget(right_panel, 1)
        main_layout.addWidget(content)

    def _set_light_empty(self):
        """Set indicator to empty state - gray."""
        self.status_light.setStyleSheet(f"""
            background: qradialgradient(cx:0.4, cy:0.4, radius:0.5,
                fx:0.3, fy:0.3,
                stop:0 #C0C0C0, stop:0.5 #808080, stop:1 #404040);
            border: 3px outset {COLORS['border']};
            border-radius: 60px;
        """)
        self.status_light.setText("")

    def _set_light_active(self):
        """Set indicator to active state - bright green/yellow pulsing look."""
        self.status_light.setStyleSheet("""
            background: qradialgradient(cx:0.4, cy:0.4, radius:0.5,
                fx:0.3, fy:0.3,
                stop:0 #FFFF00, stop:0.3 #FFCC00, stop:0.6 #FF9900, stop:1 #CC6600);
            border: 3px outset #FFCC00;
            border-radius: 60px;
        """)
        self.status_light.setText("")

    def set_car_present(self, present: bool, arrived_at: Optional[datetime] = None):
        """Update car presence state."""
        self.car_present = present
        self.car_arrived_at = arrived_at

        if present:
            self._set_light_active()
            self.status_label.setText("CUSTOMER WAITING")
            self.status_label.setStyleSheet(f"""
                font-size: 28px;
                font-weight: bold;
                color: #CC0000;
                font-family: "Tahoma", sans-serif;
            """)
            self.subtitle_label.setText("Vehicle at order point")
            self.timer_label.setText("0:00")
            self.timer_label.setStyleSheet("""
                font-size: 56px;
                font-weight: bold;
                color: #FF0000;
                font-family: "Courier New", monospace;
                background: transparent;
                border: none;
            """)
        else:
            self._set_light_empty()
            self.status_label.setText("LANE EMPTY")
            self.status_label.setStyleSheet(f"""
                font-size: 28px;
                font-weight: bold;
                color: {COLORS['text_primary']};
                font-family: "Tahoma", sans-serif;
            """)
            self.subtitle_label.setText("No vehicle detected")
            self.timer_label.setText("--:--")
            self.timer_label.setStyleSheet("""
                font-size: 56px;
                font-weight: bold;
                color: #00FF00;
                font-family: "Courier New", monospace;
                background: transparent;
                border: none;
            """)
            self.car_arrived_at = None

    def update_timer(self):
        """Update the wait timer display."""
        if self.car_present and self.car_arrived_at:
            elapsed = (datetime.now() - self.car_arrived_at).total_seconds()
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            self.timer_label.setText(f"{mins}:{secs:02d}")

            # Change color based on wait time
            if elapsed > 120:  # > 2 min - RED
                self.timer_label.setStyleSheet("""
                    font-size: 56px; font-weight: bold; color: #FF0000;
                    font-family: "Courier New", monospace;
                    background: transparent; border: none;
                """)
            elif elapsed > 60:  # > 1 min - YELLOW
                self.timer_label.setStyleSheet("""
                    font-size: 56px; font-weight: bold; color: #FFCC00;
                    font-family: "Courier New", monospace;
                    background: transparent; border: none;
                """)
            else:  # < 1 min - GREEN
                self.timer_label.setStyleSheet("""
                    font-size: 56px; font-weight: bold; color: #00FF00;
                    font-family: "Courier New", monospace;
                    background: transparent; border: none;
                """)

    def get_wait_time_seconds(self) -> float:
        """Get current wait time in seconds."""
        if self.car_present and self.car_arrived_at:
            return (datetime.now() - self.car_arrived_at).total_seconds()
        return 0.0
