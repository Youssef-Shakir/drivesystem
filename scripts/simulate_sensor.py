#!/usr/bin/env python3
"""
Drive-Thru Sensor Simulator

Creates a virtual serial port (PTY) that simulates ESP32 sensor output.
Use this to demo or test the system without hardware.

Usage:
    python scripts/simulate_sensor.py

The script will print the PTY path (e.g., /dev/pts/5) - use this in config.yaml
as the serial port. Then use keyboard commands to simulate events:
    a - Car arrives
    l - Car leaves
    q - Quit

Heartbeats are sent automatically every 5 seconds with simulated distance.
"""

import argparse
import os
import pty
import random
import select
import sys
import termios
import threading
import time
import tty
from datetime import datetime


class SensorSimulator:
    """Simulates ESP32 sensor output over a PTY."""

    def __init__(self, heartbeat_interval: float = 5.0):
        self.heartbeat_interval = heartbeat_interval
        self.master_fd: int = -1
        self.slave_fd: int = -1
        self.slave_path: str = ""
        self.running = False
        self.car_present = False
        self.base_distance = 300  # cm when no car
        self._heartbeat_thread: threading.Thread | None = None

    def start(self) -> str:
        """Start the simulator and return the PTY slave path."""
        # Create pseudo-terminal pair
        self.master_fd, self.slave_fd = pty.openpty()
        self.slave_path = os.ttyname(self.slave_fd)

        self.running = True

        # Send initial ready message
        self._write("SENSOR_READY\n")

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        return self.slave_path

    def stop(self) -> None:
        """Stop the simulator."""
        self.running = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2.0)
        if self.master_fd >= 0:
            os.close(self.master_fd)
        if self.slave_fd >= 0:
            os.close(self.slave_fd)

    def _write(self, data: str) -> None:
        """Write data to the PTY master (appears on slave as input)."""
        if self.master_fd >= 0:
            try:
                os.write(self.master_fd, data.encode("utf-8"))
            except OSError:
                pass

    def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self.running:
            time.sleep(self.heartbeat_interval)
            if self.running:
                distance = self._get_simulated_distance()
                self._write(f"HB {distance}\n")
                print(f"  [HB] Distance: {distance} cm")

    def _get_simulated_distance(self) -> int:
        """Get simulated distance reading."""
        if self.car_present:
            # Car at window: 50-120 cm with some noise
            return random.randint(50, 120)
        else:
            # No car: 200-400 cm
            return random.randint(200, 400)

    def car_arrive(self) -> None:
        """Simulate a car arriving."""
        if not self.car_present:
            self.car_present = True
            self._write("CAR_ARRIVED\n")
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"  [{timestamp}] CAR_ARRIVED")

    def car_leave(self) -> None:
        """Simulate a car leaving."""
        if self.car_present:
            self.car_present = False
            self._write("CAR_LEFT\n")
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"  [{timestamp}] CAR_LEFT")


def get_key() -> str:
    """Read a single keypress from stdin."""
    if not sys.stdin.isatty():
        time.sleep(0.1)
        return ""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # Check if input available
        rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
        if rlist:
            return sys.stdin.read(1)
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main():
    parser = argparse.ArgumentParser(
        description="Simulate ESP32 sensor for drive-thru testing"
    )
    parser.add_argument(
        "--heartbeat",
        type=float,
        default=5.0,
        help="Heartbeat interval in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-simulate random car arrivals/departures",
    )
    args = parser.parse_args()

    sim = SensorSimulator(heartbeat_interval=args.heartbeat)

    try:
        pty_path = sim.start()

        print("=" * 60)
        print("Drive-Thru Sensor Simulator")
        print("=" * 60)
        print()
        print(f"Virtual serial port: {pty_path}")
        print()
        print("Update your config.yaml:")
        print(f'  serial.port: "{pty_path}"')
        print()
        print("Controls:")
        print("  a - Car arrives")
        print("  l - Car leaves")
        print("  q - Quit")
        print()
        print("Heartbeats sent every {:.1f}s".format(args.heartbeat))
        print("-" * 60)

        if args.auto:
            print("Auto mode: Random arrivals/departures")
            auto_thread = threading.Thread(
                target=auto_simulate, args=(sim,), daemon=True
            )
            auto_thread.start()

        while sim.running:
            key = get_key()
            if key == "a":
                sim.car_arrive()
            elif key == "l":
                sim.car_leave()
            elif key == "q":
                print("\nQuitting...")
                break

    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        sim.stop()


def auto_simulate(sim: SensorSimulator) -> None:
    """Automatically simulate random car patterns."""
    while sim.running:
        # Wait for random time (10-60 seconds)
        wait_time = random.uniform(10, 60)
        time.sleep(wait_time)

        if not sim.running:
            break

        if not sim.car_present:
            sim.car_arrive()
            # Service time: 30-180 seconds
            service_time = random.uniform(30, 180)
            time.sleep(service_time)
            if sim.running and sim.car_present:
                sim.car_leave()


if __name__ == "__main__":
    main()
