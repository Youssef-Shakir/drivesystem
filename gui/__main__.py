#!/usr/bin/env python3
"""
Entry point for running the GUI as a module.

Usage:
    python -m gui              # Run with real backend
    python -m gui --demo       # Run in demo mode (Windows compatible)
    python -m gui --fullscreen # Start fullscreen
    python -m gui -d -f        # Demo mode + fullscreen
"""

from .main import main

if __name__ == "__main__":
    main()
