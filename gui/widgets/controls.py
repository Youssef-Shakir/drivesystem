"""
Control widgets.

Push-to-talk button, mode toggle, and simulator controls.
Windows XP style with large, visible buttons.
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PyQt6.QtCore import pyqtSignal

from ..theme import COLORS, xp_button_style


class PTTButton(QPushButton):
    """
    Large push-to-talk button - XP style.
    Very visible with clear state indicators.
    """

    ptt_pressed = pyqtSignal()
    ptt_released = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ptt_mode = False
        self.is_active = False
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(70)
        self.setFont(self.font())
        self._update_style()

    def _update_style(self):
        if not self.ptt_mode:
            self.setText("FULL DUPLEX MODE - Audio Always Active")
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #7FD37F, stop:0.4 #5ABF5A, stop:0.5 #3C9A36, stop:1 #2D7D2D);
                    color: white;
                    border: 3px outset #5ABF5A;
                    font-size: 16px;
                    font-weight: bold;
                    font-family: "Tahoma", sans-serif;
                }}
            """)
        elif self.is_active:
            self.setText(">>> TRANSMITTING - RELEASE TO STOP <<<")
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #FF6666, stop:0.4 #DD3333, stop:0.5 #CC0000, stop:1 #990000);
                    color: white;
                    border: 3px inset #CC0000;
                    font-size: 18px;
                    font-weight: bold;
                    font-family: "Tahoma", sans-serif;
                }}
            """)
        else:
            self.setText("PUSH AND HOLD TO TALK")
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #6699FF, stop:0.4 #3366DD, stop:0.5 #0054E3, stop:1 #003399);
                    color: white;
                    border: 3px outset #3366DD;
                    font-size: 18px;
                    font-weight: bold;
                    font-family: "Tahoma", sans-serif;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #77AAFF, stop:0.4 #4477EE, stop:0.5 #1065F4, stop:1 #1044AA);
                }}
            """)

    def set_ptt_mode(self, enabled: bool):
        """Enable or disable PTT mode."""
        self.ptt_mode = enabled
        self.is_active = False
        self._update_style()

    def mousePressEvent(self, event):
        if self.ptt_mode:
            self.is_active = True
            self._update_style()
            self.ptt_pressed.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.ptt_mode:
            self.is_active = False
            self._update_style()
            self.ptt_released.emit()
        super().mouseReleaseEvent(event)


class ModeToggleWidget(QFrame):
    """
    Audio mode toggle - XP style with clear button states.
    """

    mode_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mode = "full_duplex"
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            background-color: {COLORS['bg_primary']};
            border: 2px groove {COLORS['border']};
            padding: 8px;
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        label = QLabel("Audio Mode:")
        label.setStyleSheet(f"""
            font-size: 12px;
            font-weight: bold;
            color: {COLORS['text_primary']};
            font-family: "Tahoma", sans-serif;
        """)
        layout.addWidget(label)

        self.duplex_btn = QPushButton("Full Duplex")
        self.duplex_btn.setCheckable(True)
        self.duplex_btn.setChecked(True)
        self.duplex_btn.setFixedHeight(36)
        self.duplex_btn.clicked.connect(lambda: self._set_mode("full_duplex"))
        layout.addWidget(self.duplex_btn)

        self.ptt_btn = QPushButton("Push-to-Talk")
        self.ptt_btn.setCheckable(True)
        self.ptt_btn.setFixedHeight(36)
        self.ptt_btn.clicked.connect(lambda: self._set_mode("ptt"))
        layout.addWidget(self.ptt_btn)

        layout.addStretch()
        self._update_styles()

    def _get_active_style(self) -> str:
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6699FF, stop:0.4 #3366DD, stop:0.5 #0054E3, stop:1 #003399);
                color: white;
                border: 2px inset #0054E3;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            }
        """

    def _get_inactive_style(self) -> str:
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.4 #F0F0F0, stop:0.5 #E0E0E0, stop:1 #C8C8C8);
                color: {COLORS['text_primary']};
                border: 2px outset #D4D0C8;
                padding: 6px 16px;
                font-size: 12px;
                font-family: "Tahoma", sans-serif;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.4 #E8E8FF, stop:0.5 #D8D8F0, stop:1 #C0C0E0);
                border: 2px outset #8080C0;
            }}
        """

    def _update_styles(self):
        self.duplex_btn.setStyleSheet(
            self._get_active_style() if self.current_mode == "full_duplex"
            else self._get_inactive_style()
        )
        self.ptt_btn.setStyleSheet(
            self._get_active_style() if self.current_mode == "ptt"
            else self._get_inactive_style()
        )

    def _set_mode(self, mode: str):
        self.current_mode = mode
        self.duplex_btn.setChecked(mode == "full_duplex")
        self.ptt_btn.setChecked(mode == "ptt")
        self._update_styles()
        self.mode_changed.emit(mode)

    def set_mode(self, mode: str):
        """Set mode without emitting signal."""
        self.current_mode = mode
        self.duplex_btn.setChecked(mode == "full_duplex")
        self.ptt_btn.setChecked(mode == "ptt")
        self._update_styles()

    def get_mode(self) -> str:
        """Get current mode."""
        return self.current_mode


class SimulatorWidget(QFrame):
    """
    Simulator controls - XP style with prominent buttons.
    """

    car_arrived = pyqtSignal()
    car_left = pyqtSignal()

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

        # XP-style title bar - orange/yellow for test mode
        title_bar = QFrame()
        title_bar.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFCC00, stop:0.03 #E6B800, stop:0.08 #FFB300,
                stop:0.92 #FF9900, stop:0.97 #CC7700, stop:1 #996600);
            border: none;
        """)
        title_bar.setFixedHeight(28)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(8, 0, 8, 0)

        title = QLabel("Simulator - Test Mode")
        title.setStyleSheet("""
            color: black;
            font-weight: bold;
            font-size: 12px;
            font-family: "Trebuchet MS", "Tahoma", sans-serif;
        """)
        title_layout.addWidget(title)

        title_layout.addStretch()

        warning = QLabel("FOR TESTING ONLY")
        warning.setStyleSheet("""
            color: #990000;
            font-weight: bold;
            font-size: 10px;
            font-family: "Tahoma", sans-serif;
        """)
        title_layout.addWidget(warning)

        main_layout.addWidget(title_bar)

        # Content
        content = QFrame()
        content.setStyleSheet(f"background-color: {COLORS['bg_card']}; border: none;")
        layout = QHBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(20)

        # Car arrives button - GREEN
        self.arrive_btn = QPushButton("Car Arrives")
        self.arrive_btn.setFixedHeight(50)
        self.arrive_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7FD37F, stop:0.4 #5ABF5A, stop:0.5 #3C9A36, stop:1 #2D7D2D);
                color: white;
                border: 3px outset #5ABF5A;
                font-size: 14px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8FE38F, stop:0.4 #6ACF6A, stop:0.5 #4CAA46, stop:1 #3D8D3D);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2D7D2D, stop:0.5 #3C9A36, stop:1 #5ABF5A);
                border: 3px inset #3C9A36;
            }
        """)
        self.arrive_btn.clicked.connect(self.car_arrived.emit)
        layout.addWidget(self.arrive_btn)

        # Car leaves button - BLUE
        self.leave_btn = QPushButton("Car Leaves")
        self.leave_btn.setFixedHeight(50)
        self.leave_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6699FF, stop:0.4 #3366DD, stop:0.5 #0054E3, stop:1 #003399);
                color: white;
                border: 3px outset #3366DD;
                font-size: 14px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #77AAFF, stop:0.4 #4477EE, stop:0.5 #1065F4, stop:1 #1044AA);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #003399, stop:0.5 #0054E3, stop:1 #3366DD);
                border: 3px inset #0054E3;
            }
        """)
        self.leave_btn.clicked.connect(self.car_left.emit)
        layout.addWidget(self.leave_btn)

        main_layout.addWidget(content)

    def set_enabled(self, enabled: bool):
        """Enable or disable simulator controls."""
        self.arrive_btn.setEnabled(enabled)
        self.leave_btn.setEnabled(enabled)
