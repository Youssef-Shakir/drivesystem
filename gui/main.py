#!/usr/bin/env python3
"""
Drive-Thru Intercom - Native Linux GUI Application

A PyQt6-based dashboard for the drive-thru intercom system.
Designed for dedicated kiosk operation on Ubuntu.

Usage:
    python -m gui              # Run with real backend
    python -m gui --demo       # Run in demo mode (no hardware needed)
    python -m gui --fullscreen # Start fullscreen
"""

import sys
import os
import json
import random
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QTabWidget, QScrollArea, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPalette, QColor

# Import theme and widgets
from .theme import COLORS, get_stylesheet
from .widgets import (
    LaneStatusWidget, SensorWidget, StatsWidget,
    AudioMeterWidget, VolumeControlWidget,
    PTTButton, ModeToggleWidget, SimulatorWidget,
    FilterControlWidget,
)


class DriveThruApp(QMainWindow):
    """Main application window."""

    def __init__(self, demo_mode: bool = False):
        super().__init__()
        self.demo_mode = demo_mode
        self.presence_filter = None
        self.serial_listener = None
        self.audio_controller = None
        self.database = None

        self._setup_backend()
        self._setup_ui()
        self._setup_timers()

    def _setup_backend(self):
        """Initialize backend services."""
        if self.demo_mode:
            self._setup_demo_backend()
        else:
            self._setup_real_backend()

    def _setup_demo_backend(self):
        """Setup demo/mock backend for preview."""
        from .demo import (
            init_demo_mode, get_demo_database, get_demo_audio,
            get_demo_serial, create_demo_presence
        )

        init_demo_mode()
        self.database = get_demo_database()
        self.audio_controller = get_demo_audio()
        self.serial_listener = get_demo_serial()
        self.presence_filter = create_demo_presence(
            on_car_arrived=self._on_car_arrived,
            on_car_left=self._on_car_left,
        )

    def _setup_real_backend(self):
        """Setup real backend services."""
        try:
            # Add parent directory to path for server imports
            sys.path.insert(0, str(Path(__file__).parent.parent))

            from server.config import init_config, get_config
            from server.database import init_database, get_database
            from server.presence_filter import PresenceFilter
            from server.audio_control import init_audio_controller, get_audio_controller
            from server.serial_listener import init_serial_listener, get_serial_listener

            config = init_config()
            init_database(config.database_path)
            self.database = get_database()

            self.audio_controller = init_audio_controller(
                outdoor_mic_node=config.outdoor_mic_node,
                outdoor_speaker_node=config.outdoor_speaker_node,
                headset_sink_node=config.headset_sink_node,
                headset_source_node=config.headset_source_node,
                default_volumes=config.default_volumes,
            )

            self.presence_filter = PresenceFilter(
                threshold_cm=config.detect_threshold_cm,
                on_car_arrived=self._on_car_arrived,
                on_car_left=self._on_car_left,
            )

            self.serial_listener = init_serial_listener(
                port=config.serial_port,
                baudrate=config.serial_baudrate,
                heartbeat_timeout_sec=config.heartbeat_timeout_sec,
                on_event=self._on_serial_event,
            )
            self.serial_listener.start()

        except Exception as e:
            print(f"Backend init error: {e}")
            print("Falling back to demo mode...")
            self.demo_mode = True
            self._setup_demo_backend()

    def _on_car_arrived(self):
        """Handle car arrival."""
        if self.database:
            self.database.log_arrival()
        self.lane_widget.set_car_present(True, datetime.now())

        # Play chime (only in real mode)
        if not self.demo_mode:
            self._play_chime()

    def _on_car_left(self, duration: float):
        """Handle car departure."""
        if self.database:
            self.database.log_departure(duration)
        self.lane_widget.set_car_present(False)

    def _on_serial_event(self, event: str):
        """Handle serial events."""
        if self.presence_filter:
            self.presence_filter.process_event(event)

    def _play_chime(self):
        """Play arrival chime sound."""
        try:
            chime_path = Path(__file__).parent.parent / "sounds" / "chime.wav"
            if chime_path.exists():
                subprocess.Popen(
                    ["pw-play", str(chime_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        except Exception:
            pass

    def _setup_ui(self):
        """Setup the user interface - Windows XP style."""
        self.setWindowTitle("Drive-Thru Intercom System - Yousif Shakir" + (" [DEMO]" if self.demo_mode else ""))
        self.setMinimumSize(900, 700)
        self.setStyleSheet(get_stylesheet())

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # XP-style application header
        header = self._create_header()
        main_layout.addWidget(header)

        # Main content area - two columns
        content = QHBoxLayout()
        content.setSpacing(8)

        # LEFT COLUMN - Lane status (prominent) + Simulator
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        # Lane status - LARGE and prominent
        self.lane_widget = LaneStatusWidget()
        left_col.addWidget(self.lane_widget, 2)

        # Simulator below lane status
        self.simulator_widget = SimulatorWidget()
        self.simulator_widget.car_arrived.connect(self._simulate_car_arrived)
        self.simulator_widget.car_left.connect(self._simulate_car_left)
        left_col.addWidget(self.simulator_widget)

        content.addLayout(left_col, 3)

        # RIGHT COLUMN - Sensor, Stats, Tabs
        right_col = QVBoxLayout()
        right_col.setSpacing(8)

        # Sensor widget
        self.sensor_widget = SensorWidget()
        right_col.addWidget(self.sensor_widget)

        # Stats widget
        self.stats_widget = StatsWidget()
        right_col.addWidget(self.stats_widget)

        # Tabs for audio controls
        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 2px solid {COLORS['border']};
                background-color: {COLORS['bg_card']};
            }}
        """)
        tabs.addTab(self._create_levels_tab(), "Audio Levels")
        tabs.addTab(self._create_volume_tab(), "Volume Control")
        tabs.addTab(self._create_mode_tab(), "Audio Mode")
        tabs.addTab(self._create_filters_tab(), "Filters")
        right_col.addWidget(tabs, 1)

        content.addLayout(right_col, 2)

        main_layout.addLayout(content, 1)

        # PTT Button at bottom - VERY prominent
        self.ptt_button = PTTButton()
        self.ptt_button.ptt_pressed.connect(self._on_ptt_pressed)
        self.ptt_button.ptt_released.connect(self._on_ptt_released)
        main_layout.addWidget(self.ptt_button)

    def _create_header(self) -> QFrame:
        """Create the XP-style header bar."""
        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0058EE, stop:0.03 #3A6EA5, stop:0.08 #0054E3,
                    stop:0.92 #0054E3, stop:0.97 #003399, stop:1 #002266);
                border: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 0, 8, 0)

        title = QLabel("Drive-Thru Intercom System")
        title.setStyleSheet("""
            color: white;
            font-size: 14px;
            font-weight: bold;
            font-family: "Trebuchet MS", "Tahoma", sans-serif;
        """)
        layout.addWidget(title)

        # Author credit
        author = QLabel("by Yousif Shakir - www.donialink.com")
        author.setStyleSheet("""
            color: #B0C4FF;
            font-size: 10px;
            font-family: "Tahoma", sans-serif;
            margin-left: 10px;
        """)
        layout.addWidget(author)

        if self.demo_mode:
            demo_badge = QLabel("DEMO")
            demo_badge.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFF00, stop:0.5 #FFCC00, stop:1 #CC9900);
                color: black;
                padding: 2px 10px;
                border: 1px outset #FFCC00;
                font-size: 10px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            """)
            layout.addWidget(demo_badge)

        layout.addStretch()

        # Time display
        self.time_label = QLabel("")
        self.time_label.setStyleSheet("""
            color: white;
            font-size: 12px;
            font-family: "Tahoma", sans-serif;
        """)
        layout.addWidget(self.time_label)
        self._update_time()

        # XP-style window buttons
        fullscreen_btn = QPushButton("\u2610")
        fullscreen_btn.setFixedSize(28, 22)
        fullscreen_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.4 #F0F0F0, stop:0.5 #E0E0E0, stop:1 #C8C8C8);
                color: black;
                border: 1px outset #D4D0C8;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.4 #E8E8FF, stop:0.5 #D8D8F0, stop:1 #C0C0E0);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C8C8C8, stop:0.5 #E0E0E0, stop:1 #F0F0F0);
                border: 1px inset #D4D0C8;
            }
        """)
        fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        layout.addWidget(fullscreen_btn)

        return header

    def _update_time(self):
        """Update the time display in header."""
        from datetime import datetime
        now = datetime.now()
        self.time_label.setText(now.strftime("%I:%M %p"))

    def _create_levels_tab(self) -> QWidget:
        """Create the audio levels tab - XP style."""
        widget = QWidget()
        widget.setStyleSheet(f"background-color: {COLORS['bg_card']};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Real-time Audio Level Meters")
        title.setStyleSheet(f"""
            color: {COLORS['xp_blue_dark']};
            font-size: 12px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
            margin-bottom: 8px;
        """)
        layout.addWidget(title)

        self.meter_outdoor_mic = AudioMeterWidget("Outdoor Mic")
        layout.addWidget(self.meter_outdoor_mic)

        self.meter_speaker = AudioMeterWidget("Speaker Out")
        layout.addWidget(self.meter_speaker)

        self.meter_headset = AudioMeterWidget("Headset")
        layout.addWidget(self.meter_headset)

        layout.addStretch()
        return widget

    def _create_volume_tab(self) -> QWidget:
        """Create the volume control tab - XP style."""
        widget = QWidget()
        widget.setStyleSheet(f"background-color: {COLORS['bg_card']};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Adjust Volume Levels")
        title.setStyleSheet(f"""
            color: {COLORS['xp_blue_dark']};
            font-size: 12px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
            margin-bottom: 8px;
        """)
        layout.addWidget(title)

        self.vol_outdoor_mic = VolumeControlWidget("Outdoor Mic", "outdoor_mic")
        self.vol_outdoor_mic.volume_changed.connect(self._on_volume_changed)
        self.vol_outdoor_mic.mute_changed.connect(self._on_mute_changed)
        layout.addWidget(self.vol_outdoor_mic)

        self.vol_speaker = VolumeControlWidget("Outdoor Speaker", "outdoor_speaker")
        self.vol_speaker.volume_changed.connect(self._on_volume_changed)
        self.vol_speaker.mute_changed.connect(self._on_mute_changed)
        layout.addWidget(self.vol_speaker)

        self.vol_headset = VolumeControlWidget("Headset", "headset")
        self.vol_headset.volume_changed.connect(self._on_volume_changed)
        self.vol_headset.mute_changed.connect(self._on_mute_changed)
        layout.addWidget(self.vol_headset)

        layout.addStretch()
        return widget

    def _create_mode_tab(self) -> QWidget:
        """Create the audio mode tab - XP style."""
        widget = QWidget()
        widget.setStyleSheet(f"background-color: {COLORS['bg_card']};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        title = QLabel("Select Audio Mode")
        title.setStyleSheet(f"""
            color: {COLORS['xp_blue_dark']};
            font-size: 12px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
            margin-bottom: 8px;
        """)
        layout.addWidget(title)

        self.mode_toggle = ModeToggleWidget()
        self.mode_toggle.mode_changed.connect(self._on_mode_changed)
        layout.addWidget(self.mode_toggle)

        # XP-style info box
        info_frame = QFrame()
        info_frame.setStyleSheet(f"""
            background-color: #FFFFCC;
            border: 1px solid #CCCC99;
            padding: 10px;
        """)
        info_layout = QVBoxLayout(info_frame)

        info_title = QLabel("Information")
        info_title.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 12px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
        """)
        info_layout.addWidget(info_title)

        desc = QLabel(
            "<b>Full Duplex:</b> Audio flows both directions continuously. "
            "Customer and staff can speak simultaneously.<br><br>"
            "<b>Push-to-Talk:</b> Hold the PTT button at the bottom of the screen "
            "to transmit audio to the customer."
        )
        desc.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 11px;
            font-family: "Tahoma", sans-serif;
        """)
        desc.setWordWrap(True)
        info_layout.addWidget(desc)

        layout.addWidget(info_frame)
        layout.addStretch()
        return widget

    def _create_filters_tab(self) -> QWidget:
        """Create the audio filters tab - XP style."""
        widget = QWidget()
        widget.setStyleSheet(f"background-color: {COLORS['bg_card']};")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Audio Processing Filters")
        title.setStyleSheet(f"""
            color: {COLORS['xp_blue_dark']};
            font-size: 12px;
            font-weight: bold;
            font-family: "Tahoma", sans-serif;
            margin-bottom: 8px;
        """)
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 2px inset {COLORS['border']};
                background-color: {COLORS['bg_primary']};
            }}
        """)

        content = QWidget()
        content.setStyleSheet(f"background-color: {COLORS['bg_primary']};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 8, 8)

        # Apply button - XP green style
        apply_btn = QPushButton("Apply Filters & Process Audio")
        apply_btn.setFixedHeight(40)
        apply_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7FD37F, stop:0.4 #5ABF5A, stop:0.5 #3C9A36, stop:1 #2D7D2D);
                color: white;
                border: 2px outset #5ABF5A;
                font-size: 13px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8FE38F, stop:0.4 #6ACF6A, stop:0.5 #4CAA46, stop:1 #3D8D3D);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2D7D2D, stop:0.5 #3C9A36, stop:1 #5ABF5A);
                border: 2px inset #3C9A36;
            }
        """)
        apply_btn.clicked.connect(self._apply_filters)
        content_layout.addWidget(apply_btn)

        # Filter controls
        self.filter_hp = FilterControlWidget(
            "1. High-Pass Filter", "high_pass",
            [("Cutoff", "cutoff", 50, 500, 150, "Hz")]
        )
        content_layout.addWidget(self.filter_hp)

        self.filter_ng = FilterControlWidget(
            "2. Noise Gate", "noise_gate",
            [
                ("Threshold", "threshold", 0, 100, 15, "%"),
                ("Reduction", "reduction", 0, 100, 20, "%"),
            ]
        )
        content_layout.addWidget(self.filter_ng)

        self.filter_pb = FilterControlWidget(
            "3. Presence Boost", "presence_boost",
            [
                ("Low Freq", "low_freq", 500, 4000, 2000, "Hz"),
                ("High Freq", "high_freq", 2000, 8000, 4000, "Hz"),
                ("Gain", "gain", 0, 100, 30, "%"),
            ]
        )
        content_layout.addWidget(self.filter_pb)

        self.filter_comp = FilterControlWidget(
            "4. Compressor", "compressor",
            [
                ("Threshold", "threshold", 10, 80, 25, "%"),
                ("Ratio", "ratio", 10, 90, 40, "%"),
            ]
        )
        content_layout.addWidget(self.filter_comp)

        self.filter_norm = FilterControlWidget(
            "5. Normalize", "normalize",
            [("Target", "target", 50, 100, 85, "%")]
        )
        content_layout.addWidget(self.filter_norm)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return widget

    def _setup_timers(self):
        """Setup update timers."""
        # Fast timer for UI updates (10 Hz)
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self._update_ui)
        self.ui_timer.start(100)

        # Slow timer for stats (every 5s)
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_stats)
        self.stats_timer.start(5000)

        # Clock timer (every second)
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self._update_time)
        self.clock_timer.start(1000)

        # Initial updates
        self._update_stats()
        self._update_time()

    def _update_ui(self):
        """Update UI elements."""
        # Update lane timer
        self.lane_widget.update_timer()

        # Update sensor status
        if self.serial_listener:
            is_online = getattr(self.serial_listener, 'is_sensor_online', True)
            status = "online" if is_online else "offline"
            distance = getattr(self.serial_listener, 'last_distance', 0)
        else:
            status = "unknown"
            distance = 0

        # Get distance from presence filter if available
        if self.presence_filter:
            pf_distance = getattr(self.presence_filter, 'last_distance_cm', None)
            if pf_distance is not None:
                distance = pf_distance

            # Simulate distance changes in demo mode
            if self.demo_mode and hasattr(self.presence_filter, 'simulate_distance'):
                self.presence_filter.simulate_distance()

        self.sensor_widget.set_status(status, distance)

        # Simulate audio levels
        car_present = self.lane_widget.car_present
        ptt_active = self.ptt_button.is_active

        self.meter_outdoor_mic.set_level(
            random.uniform(0.05, 0.3) if car_present else random.uniform(0, 0.1)
        )
        self.meter_speaker.set_level(
            random.uniform(0.1, 0.4) if ptt_active else random.uniform(0, 0.05)
        )
        self.meter_headset.set_level(random.uniform(0.1, 0.3))

    def _update_stats(self):
        """Update statistics display."""
        try:
            if self.database:
                stats = self.database.get_stats()
                distance = 0
                if self.presence_filter:
                    distance = getattr(self.presence_filter, 'last_distance_cm', 0) or 0
                self.stats_widget.update_stats(
                    stats.cars_today,
                    stats.avg_service_time_sec,
                    distance
                )
        except Exception:
            pass

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _simulate_car_arrived(self):
        """Handle simulated car arrival."""
        if self.presence_filter:
            self.presence_filter.process_event("CAR_ARRIVED")

    def _simulate_car_left(self):
        """Handle simulated car departure."""
        if self.presence_filter:
            self.presence_filter.process_event("CAR_LEFT")

    def _on_volume_changed(self, device: str, volume: float):
        """Handle volume change."""
        if self.audio_controller:
            self.audio_controller.set_volume(device, volume)

    def _on_mute_changed(self, device: str, muted: bool):
        """Handle mute change."""
        if self.audio_controller:
            self.audio_controller.set_mute(device, muted)

    def _on_mode_changed(self, mode: str):
        """Handle audio mode change."""
        try:
            if self.audio_controller:
                if self.demo_mode:
                    self.audio_controller.set_mode(mode)
                else:
                    from server.models import AudioMode
                    audio_mode = AudioMode.PTT if mode == "ptt" else AudioMode.FULL_DUPLEX
                    self.audio_controller.set_mode(audio_mode)
            self.ptt_button.set_ptt_mode(mode == "ptt")
        except Exception:
            pass

    def _on_ptt_pressed(self):
        """Handle PTT button press."""
        if self.audio_controller:
            self.audio_controller.set_ptt(True)

    def _on_ptt_released(self):
        """Handle PTT button release."""
        if self.audio_controller:
            self.audio_controller.set_ptt(False)

    def _apply_filters(self):
        """Apply filter settings."""
        settings = {
            "high_pass": self.filter_hp.get_settings(),
            "noise_gate": self.filter_ng.get_settings(),
            "presence_boost": self.filter_pb.get_settings(),
            "compressor": self.filter_comp.get_settings(),
            "normalize": self.filter_norm.get_settings(),
        }

        if self.demo_mode:
            QMessageBox.information(
                self, "Demo Mode",
                "Filter settings captured:\n\n" +
                json.dumps(settings, indent=2)[:500]
            )
            return

        # Convert percentages to decimals
        settings["noise_gate"]["threshold"] = settings["noise_gate"].get("threshold", 15) / 1000
        settings["noise_gate"]["reduction"] = settings["noise_gate"].get("reduction", 20) / 100
        settings["presence_boost"]["gain"] = settings["presence_boost"].get("gain", 30) / 100
        settings["compressor"]["threshold"] = settings["compressor"].get("threshold", 25) / 100
        settings["compressor"]["ratio"] = settings["compressor"].get("ratio", 40) / 100
        settings["normalize"]["target"] = settings["normalize"].get("target", 85) / 100

        try:
            settings_json = json.dumps(settings)
            result = subprocess.run(
                ["python3", "scripts/process_recording.py", "--settings", settings_json],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent)
            )
            if result.returncode == 0:
                QMessageBox.information(self, "Success", "Audio processed successfully!")
            else:
                QMessageBox.warning(self, "Error", f"Processing failed:\n{result.stderr}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to process: {e}")

    def closeEvent(self, event):
        """Cleanup on close."""
        if self.serial_listener and hasattr(self.serial_listener, 'stop'):
            self.serial_listener.stop()
        event.accept()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Drive-Thru Intercom GUI")
    parser.add_argument(
        "--demo", "-d",
        action="store_true",
        help="Run in demo mode (no hardware required)"
    )
    parser.add_argument(
        "--fullscreen", "-f",
        action="store_true",
        help="Start in fullscreen mode"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Drive-Thru Intercom")

    # Set dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS['bg_primary']))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS['text_primary']))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS['bg_secondary']))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS['text_primary']))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS['bg_card']))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS['text_primary']))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS['accent_blue']))
    app.setPalette(palette)

    window = DriveThruApp(demo_mode=args.demo)

    if args.fullscreen:
        window.showFullScreen()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
