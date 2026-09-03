"""
Statistics display widget.

Shows daily stats like car count, average service time, etc.
Windows XP style with large, visible numbers.
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt

from ..theme import COLORS


class StatsWidget(QFrame):
    """
    Today's statistics display - XP style with prominent numbers.
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
        title_bar = QLabel("  Today's Statistics")
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
        stats_layout = QHBoxLayout(content)
        stats_layout.setContentsMargins(12, 12, 12, 12)
        stats_layout.setSpacing(12)

        # Cars today
        cars_frame, self.cars_label = self._create_stat_box("0", "Cars Served")
        stats_layout.addWidget(cars_frame)

        # Avg time
        time_frame, self.time_label = self._create_stat_box("0:00", "Avg. Wait")
        stats_layout.addWidget(time_frame)

        # Current distance
        dist_frame, self.dist_label = self._create_stat_box("---", "Distance (cm)")
        stats_layout.addWidget(dist_frame)

        main_layout.addWidget(content)

    def _create_stat_box(self, value: str, label: str) -> tuple[QFrame, QLabel]:
        """Create a stat box with value and label - XP style."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            background-color: {COLORS['bg_primary']};
            border: 2px inset {COLORS['border']};
        """)

        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(12, 8, 12, 8)

        # Large value display - LCD style
        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setStyleSheet(f"""
            color: #000080;
            font-size: 36px;
            font-weight: bold;
            font-family: "Courier New", monospace;
            background-color: #E8E8E8;
            border: 1px solid {COLORS['border']};
            padding: 8px 16px;
        """)
        layout.addWidget(value_label)

        # Label below
        text_label = QLabel(label)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 11px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
            margin-top: 4px;
        """)
        layout.addWidget(text_label)

        return frame, value_label

    def update_stats(self, cars: int, avg_time: float, distance: int):
        """Update all statistics."""
        self.cars_label.setText(str(cars))

        mins = int(avg_time // 60)
        secs = int(avg_time % 60)
        self.time_label.setText(f"{mins}:{secs:02d}")

        self.dist_label.setText(str(distance) if distance > 0 else "---")

    def set_cars(self, count: int):
        """Update car count only."""
        self.cars_label.setText(str(count))

    def set_avg_time(self, seconds: float):
        """Update average time only."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        self.time_label.setText(f"{mins}:{secs:02d}")

    def set_distance(self, distance: int):
        """Update distance only."""
        self.dist_label.setText(str(distance) if distance > 0 else "---")
