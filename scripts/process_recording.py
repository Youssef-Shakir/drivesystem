#!/usr/bin/env python3
"""
Process a recording through AEC simulation with adjustable filters.
"""

import argparse
import json
import math
import struct
import wave
import sys
from pathlib import Path


DEFAULT_SETTINGS = {
    "high_pass": {"enabled": True, "cutoff": 150},
    "noise_gate": {"enabled": True, "threshold": 0.015, "reduction": 0.2},
    "presence_boost": {"enabled": True, "low_freq": 2000, "high_freq": 4000, "gain": 0.3},
    "compressor": {"enabled": True, "threshold": 0.25, "ratio": 0.4},
    "normalize": {"enabled": True, "target": 0.85},
}


def read_wav(path: Path) -> tuple[list[float], int]:
    """Read WAV file and return normalized samples and sample rate."""
    with wave.open(str(path), 'rb') as wav:
        sample_rate = wav.getframerate()
        n_frames = wav.getnframes()
        n_channels = wav.getnchannels()
        sample_width = wav.getsampwidth()

        raw_data = wav.readframes(n_frames)

        if sample_width == 2:
            samples = struct.unpack(f'<{n_frames * n_channels}h', raw_data)
        elif sample_width == 1:
            samples = struct.unpack(f'{n_frames * n_channels}B', raw_data)
            samples = [s - 128 for s in samples]
        else:
            raise ValueError(f"Unsupported sample width: {sample_width}")

        # Convert to mono if stereo
        if n_channels == 2:
            samples = [(samples[i] + samples[i+1]) / 2 for i in range(0, len(samples), 2)]

        # Normalize to -1.0 to 1.0
        max_val = 32767 if sample_width == 2 else 127
        samples = [s / max_val for s in samples]

        return samples, sample_rate


def save_wav(samples: list[float], path: Path, sample_rate: int = 44100) -> None:
    """Save samples to WAV file."""
    int_samples = [int(max(-32768, min(32767, s * 32767))) for s in samples]

    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        data = struct.pack(f'<{len(int_samples)}h', *int_samples)
        wav.writeframes(data)

    print(f"Saved: {path} ({len(samples)/sample_rate:.1f}s)")


def high_pass_filter(samples: list[float], cutoff: float, sample_rate: int) -> list[float]:
    """High-pass filter to remove low frequency rumble."""
    rc = 1.0 / (2.0 * math.pi * cutoff)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)

    filtered = [0.0] * len(samples)
    filtered[0] = samples[0]

    for i in range(1, len(samples)):
        filtered[i] = alpha * (filtered[i-1] + samples[i] - samples[i-1])

    return filtered


def low_pass_filter(samples: list[float], cutoff: float, sample_rate: int) -> list[float]:
    """Low-pass filter."""
    rc = 1.0 / (2.0 * math.pi * cutoff)
    dt = 1.0 / sample_rate
    alpha = dt / (rc + dt)

    filtered = [0.0] * len(samples)
    filtered[0] = samples[0]

    for i in range(1, len(samples)):
        filtered[i] = filtered[i-1] + alpha * (samples[i] - filtered[i-1])

    return filtered


def noise_gate(samples: list[float], threshold: float = 0.02, reduction: float = 0.3) -> list[float]:
    """Apply noise gate to reduce quiet sections."""
    output = []
    for s in samples:
        if abs(s) < threshold:
            output.append(s * reduction)
        else:
            output.append(s)
    return output


def compressor(samples: list[float], threshold: float = 0.3, ratio: float = 0.5) -> list[float]:
    """Simple compressor to reduce dynamic range."""
    output = []
    for s in samples:
        if abs(s) > threshold:
            sign = 1 if s > 0 else -1
            output.append(sign * (threshold + (abs(s) - threshold) * ratio))
        else:
            output.append(s)
    return output


def normalize(samples: list[float], target_peak: float = 0.85) -> list[float]:
    """Normalize audio to target peak level."""
    peak = max(abs(s) for s in samples) if samples else 0
    if peak == 0:
        return samples
    scale = target_peak / peak
    return [s * scale for s in samples]


def process_aec(samples: list[float], sample_rate: int, settings: dict) -> list[float]:
    """
    Process audio with configurable filters.
    """
    processed = samples.copy()

    # 1. High-pass filter
    hp = settings.get("high_pass", {})
    if hp.get("enabled", True):
        cutoff = hp.get("cutoff", 150)
        print(f"  [1] High-pass filter: {cutoff}Hz")
        processed = high_pass_filter(processed, cutoff=cutoff, sample_rate=sample_rate)
    else:
        print("  [1] High-pass filter: DISABLED")

    # 2. Noise gate
    ng = settings.get("noise_gate", {})
    if ng.get("enabled", True):
        threshold = ng.get("threshold", 0.015)
        reduction = ng.get("reduction", 0.2)
        print(f"  [2] Noise gate: threshold={threshold}, reduction={reduction}")
        processed = noise_gate(processed, threshold=threshold, reduction=reduction)
    else:
        print("  [2] Noise gate: DISABLED")

    # 3. Presence boost
    pb = settings.get("presence_boost", {})
    if pb.get("enabled", True):
        low_freq = pb.get("low_freq", 2000)
        high_freq = pb.get("high_freq", 4000)
        gain = pb.get("gain", 0.3)
        print(f"  [3] Presence boost: {low_freq}-{high_freq}Hz, gain={gain}")
        voice_band = high_pass_filter(processed, cutoff=low_freq, sample_rate=sample_rate)
        voice_band = low_pass_filter(voice_band, cutoff=high_freq, sample_rate=sample_rate)
        processed = [p + v * gain for p, v in zip(processed, voice_band)]
    else:
        print("  [3] Presence boost: DISABLED")

    # 4. Compressor
    comp = settings.get("compressor", {})
    if comp.get("enabled", True):
        threshold = comp.get("threshold", 0.25)
        ratio = comp.get("ratio", 0.4)
        print(f"  [4] Compressor: threshold={threshold}, ratio={ratio}")
        processed = compressor(processed, threshold=threshold, ratio=ratio)
    else:
        print("  [4] Compressor: DISABLED")

    # 5. Normalize
    norm = settings.get("normalize", {})
    if norm.get("enabled", True):
        target = norm.get("target", 0.85)
        print(f"  [5] Normalize: target={target}")
        processed = normalize(processed, target_peak=target)
    else:
        print("  [5] Normalize: DISABLED")

    return processed


def main():
    parser = argparse.ArgumentParser(description="Process audio with AEC filters")
    parser.add_argument("--settings", type=str, help="JSON string of filter settings")
    parser.add_argument("--input", type=str, help="Input WAV file path")
    parser.add_argument("--output", type=str, help="Output WAV file path")
    args = parser.parse_args()

    # Parse settings
    if args.settings:
        try:
            settings = json.loads(args.settings)
        except json.JSONDecodeError:
            # Try eval for Python dict syntax
            settings = eval(args.settings)
    else:
        settings = DEFAULT_SETTINGS

    # File paths
    assets_dir = Path(__file__).parent.parent / "server" / "assets"

    input_file = Path(args.input) if args.input else assets_dir / "recording_input.wav"
    output_file = Path(args.output) if args.output else assets_dir / "recording_processed.wav"

    if not input_file.exists():
        print(f"Error: {input_file} not found")
        sys.exit(1)

    print(f"\n=== Processing: {input_file.name} ===")
    print(f"Settings: {json.dumps(settings, indent=2)}")

    print("\nReading input file...")
    samples, sample_rate = read_wav(input_file)
    print(f"  Duration: {len(samples)/sample_rate:.1f}s, Sample rate: {sample_rate}Hz")

    print("\nApplying filters...")
    processed = process_aec(samples, sample_rate, settings)

    print("\nSaving output...")
    save_wav(processed, output_file, sample_rate)

    print(f"\n=== Done! ===")


if __name__ == "__main__":
    main()
