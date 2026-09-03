"""
Drive-Thru Intercom GUI Package

A PyQt6-based dashboard for the drive-thru intercom system.

Quick Start:
    # Run in demo mode (no hardware required)
    python -m gui --demo

    # Run with real backend (Linux with PipeWire)
    python -m gui

    # Run fullscreen
    python -m gui --fullscreen

Package Structure:
    gui/
    ├── __init__.py      # This file
    ├── __main__.py      # Entry point for `python -m gui`
    ├── main.py          # Main application window
    ├── theme.py         # Colors and styling (edit to customize)
    ├── demo.py          # Demo mode backend (for previewing)
    └── widgets/         # Reusable UI components
        ├── __init__.py
        ├── lane_status.py   # Lane status indicator
        ├── sensor.py        # Sensor status display
        ├── stats.py         # Statistics display
        ├── audio.py         # Volume controls and meters
        ├── controls.py      # PTT, mode toggle, simulator
        └── filters.py       # Audio filter controls

Customization:
    - Edit theme.py to change colors
    - Edit individual widget files to modify components
    - The main.py file orchestrates everything
"""

from .main import DriveThruApp, main
from .theme import COLORS, get_stylesheet

__all__ = ['DriveThruApp', 'main', 'COLORS', 'get_stylesheet']
__version__ = '1.0.0'
