#!/usr/bin/env python3
"""
Generate a simple chime WAV file for car arrival notification.

Usage:
    python scripts/generate_chime.py

Creates server/assets/chime.wav - a pleasant two-tone chime sound.
"""

import math
import struct
import wave
from pathlib import Path


def generate_sine_wave(
    frequency: float,
    duration: float,
    sample_rate: int = 44100,
    amplitude: float = 0.5,
) -> list[int]:
    """Generate a sine wave as 16-bit samples."""
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Apply envelope (fade in/out)
        envelope = 1.0
        fade_time = 0.02  # 20ms fade
        if t < fade_time:
            envelope = t / fade_time
        elif t > duration - fade_time:
            envelope = (duration - t) / fade_time

        value = amplitude * envelope * math.sin(2 * math.pi * frequency * t)
        # Convert to 16-bit integer
        samples.append(int(value * 32767))

    return samples


def generate_chime(output_path: Path) -> None:
    """Generate a pleasant two-tone chime."""
    sample_rate = 44100

    # First tone: E5 (659 Hz) for 150ms
    tone1 = generate_sine_wave(659, 0.15, sample_rate, 0.4)

    # Short gap (50ms silence)
    gap = [0] * int(sample_rate * 0.05)

    # Second tone: G5 (784 Hz) for 200ms
    tone2 = generate_sine_wave(784, 0.20, sample_rate, 0.4)

    # Combine
    samples = tone1 + gap + tone2

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write WAV file
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)

        # Pack samples as little-endian 16-bit integers
        data = struct.pack(f"<{len(samples)}h", *samples)
        wav.writeframes(data)

    print(f"Generated chime: {output_path}")
    print(f"Duration: {len(samples) / sample_rate:.2f}s")


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_path = project_root / "server" / "assets" / "chime.wav"

    generate_chime(output_path)


if __name__ == "__main__":
    main()
