#!/usr/bin/env python3
"""
Generate simulated drive-thru customer audio.

Creates a realistic audio track with:
- Car engine idle noise (low rumble)
- Distant muffled voice (simulated speech patterns)
- Ambient outdoor noise
- Effects: low-pass filter, distance attenuation
"""

import math
import random
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 44100
DURATION = 12.0  # seconds


def generate_noise(num_samples: int, amplitude: float = 0.1) -> list[float]:
    """Generate white noise."""
    return [random.uniform(-amplitude, amplitude) for _ in range(num_samples)]


def generate_pink_noise(num_samples: int, amplitude: float = 0.1) -> list[float]:
    """Generate pink noise (1/f noise) - more natural sounding."""
    white = generate_noise(num_samples, 1.0)
    pink = []
    b = [0.0] * 7

    for w in white:
        b[0] = 0.99886 * b[0] + w * 0.0555179
        b[1] = 0.99332 * b[1] + w * 0.0750759
        b[2] = 0.96900 * b[2] + w * 0.1538520
        b[3] = 0.86650 * b[3] + w * 0.3104856
        b[4] = 0.55000 * b[4] + w * 0.5329522
        b[5] = -0.7616 * b[5] - w * 0.0168980
        pink_sample = (b[0] + b[1] + b[2] + b[3] + b[4] + b[5] + b[6] + w * 0.5362) * amplitude
        b[6] = w * 0.115926
        pink.append(pink_sample)

    return pink


def generate_engine_noise(num_samples: int, rpm: float = 800) -> list[float]:
    """Generate car engine idle noise."""
    samples = []

    # Engine fundamental frequency based on RPM (4-stroke = RPM/60/2)
    fundamental = rpm / 60 / 2

    for i in range(num_samples):
        t = i / SAMPLE_RATE

        # Engine harmonics
        engine = 0.0
        engine += 0.3 * math.sin(2 * math.pi * fundamental * t)
        engine += 0.2 * math.sin(2 * math.pi * fundamental * 2 * t)
        engine += 0.15 * math.sin(2 * math.pi * fundamental * 3 * t)
        engine += 0.1 * math.sin(2 * math.pi * fundamental * 4 * t)

        # Add some randomness for realism
        engine += random.uniform(-0.05, 0.05)

        # Slight RPM variation
        rpm_var = 1.0 + 0.02 * math.sin(2 * math.pi * 0.5 * t)
        engine *= rpm_var

        samples.append(engine * 0.15)

    return samples


def generate_voice_formants(num_samples: int, start_time: float, duration: float,
                           pitch: float = 120, amplitude: float = 0.3) -> list[float]:
    """Generate speech-like formants (vowel sounds)."""
    samples = [0.0] * num_samples

    start_sample = int(start_time * SAMPLE_RATE)
    end_sample = min(start_sample + int(duration * SAMPLE_RATE), num_samples)

    # Formant frequencies for different vowels
    formants = [
        (800, 1200, 2500),   # 'a'
        (300, 2300, 3000),   # 'i'
        (500, 1000, 2500),   # 'o'
        (640, 1200, 2400),   # 'e'
    ]

    chosen_formants = random.choice(formants)

    for i in range(start_sample, end_sample):
        t = (i - start_sample) / SAMPLE_RATE
        local_t = t / duration

        # Envelope (fade in/out)
        envelope = 1.0
        fade = 0.05
        if local_t < fade:
            envelope = local_t / fade
        elif local_t > 1 - fade:
            envelope = (1 - local_t) / fade

        # Glottal pulse (vocal cord vibration)
        glottal = 0.0
        for h in range(1, 8):
            glottal += (1.0 / h) * math.sin(2 * math.pi * pitch * h * t)

        # Apply formants
        voice = 0.0
        for f_idx, freq in enumerate(chosen_formants):
            bandwidth = 100 + f_idx * 50
            resonance = math.exp(-math.pi * bandwidth * t % (1/freq))
            voice += resonance * math.sin(2 * math.pi * freq * t) * (0.5 / (f_idx + 1))

        # Combine
        sample = glottal * 0.3 + voice * 0.7
        sample *= envelope * amplitude

        samples[i] = sample

    return samples


def generate_speech_pattern(num_samples: int) -> list[float]:
    """Generate a pattern of speech-like sounds (simulated talking)."""
    samples = [0.0] * num_samples

    # Speech segments: (start_time, duration, pitch, amplitude)
    # Simulating: "Hi, can I get a... large coffee... and a breakfast sandwich"
    segments = [
        # "Hi"
        (1.0, 0.3, 140, 0.25),
        # pause
        # "can I get a"
        (1.8, 0.15, 130, 0.2),
        (2.0, 0.12, 125, 0.22),
        (2.2, 0.18, 135, 0.2),
        (2.5, 0.12, 120, 0.18),
        # pause (thinking)
        # "large coffee"
        (3.5, 0.25, 125, 0.28),
        (3.9, 0.35, 130, 0.25),
        # pause
        # "and a"
        (5.0, 0.15, 120, 0.18),
        (5.2, 0.1, 115, 0.15),
        # "breakfast sandwich"
        (5.8, 0.3, 135, 0.25),
        (6.2, 0.25, 125, 0.22),
        (6.6, 0.35, 130, 0.24),
        # pause
        # "please"
        (8.0, 0.35, 140, 0.2),
        # "thank you"
        (9.5, 0.2, 135, 0.18),
        (9.8, 0.25, 125, 0.2),
    ]

    for start, dur, pitch, amp in segments:
        voice = generate_voice_formants(num_samples, start, dur, pitch, amp)
        for i in range(num_samples):
            samples[i] += voice[i]

    return samples


def low_pass_filter(samples: list[float], cutoff: float = 3000) -> list[float]:
    """Simple low-pass filter to simulate distance/muffling."""
    rc = 1.0 / (2.0 * math.pi * cutoff)
    dt = 1.0 / SAMPLE_RATE
    alpha = dt / (rc + dt)

    filtered = [0.0] * len(samples)
    filtered[0] = samples[0]

    for i in range(1, len(samples)):
        filtered[i] = filtered[i-1] + alpha * (samples[i] - filtered[i-1])

    return filtered


def add_reverb(samples: list[float], delay_ms: float = 50, decay: float = 0.3) -> list[float]:
    """Add simple reverb/echo for distance effect."""
    delay_samples = int(delay_ms * SAMPLE_RATE / 1000)
    output = samples.copy()

    for i in range(delay_samples, len(samples)):
        output[i] += samples[i - delay_samples] * decay

    # Second reflection
    delay_samples2 = int(delay_ms * 1.7 * SAMPLE_RATE / 1000)
    for i in range(delay_samples2, len(samples)):
        output[i] += samples[i - delay_samples2] * decay * 0.5

    return output


def normalize(samples: list[float], target_peak: float = 0.8) -> list[float]:
    """Normalize audio to target peak level."""
    peak = max(abs(s) for s in samples)
    if peak == 0:
        return samples
    scale = target_peak / peak
    return [s * scale for s in samples]


def mix_tracks(*tracks: list[float]) -> list[float]:
    """Mix multiple audio tracks together."""
    length = max(len(t) for t in tracks)
    mixed = [0.0] * length

    for track in tracks:
        for i in range(len(track)):
            mixed[i] += track[i]

    return mixed


def generate_customer_audio() -> list[float]:
    """Generate complete customer audio simulation."""
    num_samples = int(DURATION * SAMPLE_RATE)

    print("Generating engine noise...")
    engine = generate_engine_noise(num_samples, rpm=750)

    print("Generating ambient noise...")
    ambient = generate_pink_noise(num_samples, amplitude=0.03)

    print("Generating speech...")
    speech = generate_speech_pattern(num_samples)

    # Apply distance effects to speech (customer is ~1-2m from mic)
    print("Applying distance effects...")
    speech = low_pass_filter(speech, cutoff=2500)  # Muffle high frequencies
    speech = add_reverb(speech, delay_ms=30, decay=0.2)  # Slight room echo
    speech = [s * 0.6 for s in speech]  # Reduce volume (distance)

    # Apply low-pass to engine (mostly low frequencies anyway)
    engine = low_pass_filter(engine, cutoff=400)

    print("Mixing tracks...")
    mixed = mix_tracks(engine, ambient, speech)

    # Normalize
    mixed = normalize(mixed, target_peak=0.7)

    return mixed


def apply_aec_simulation(samples: list[float]) -> list[float]:
    """Simulate what AEC processing would do to clean up the audio."""
    print("Simulating AEC processing...")

    # High-pass filter (remove low rumble)
    # Simple high-pass by subtracting low-passed version
    low = low_pass_filter(samples, cutoff=150)
    high_passed = [s - l * 0.7 for s, l in zip(samples, low)]

    # Noise gate (reduce very quiet parts)
    threshold = 0.02
    gated = []
    for s in high_passed:
        if abs(s) < threshold:
            gated.append(s * 0.3)  # Reduce noise floor
        else:
            gated.append(s)

    # Slight compression (reduce dynamic range)
    compressed = []
    for s in gated:
        if abs(s) > 0.3:
            sign = 1 if s > 0 else -1
            compressed.append(sign * (0.3 + (abs(s) - 0.3) * 0.5))
        else:
            compressed.append(s)

    # Normalize
    return normalize(compressed, target_peak=0.75)


def save_wav(samples: list[float], path: Path) -> None:
    """Save samples to WAV file."""
    # Convert to 16-bit integers
    int_samples = [int(s * 32767) for s in samples]
    int_samples = [max(-32768, min(32767, s)) for s in int_samples]

    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        data = struct.pack(f'<{len(int_samples)}h', *int_samples)
        wav.writeframes(data)

    print(f"Saved: {path} ({len(samples)/SAMPLE_RATE:.1f}s)")


def main():
    output_dir = Path(__file__).parent.parent / "server" / "assets"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate raw customer audio (what the outdoor mic picks up)
    print("\n=== Generating Raw Customer Audio ===")
    raw_audio = generate_customer_audio()
    raw_path = output_dir / "customer_raw.wav"
    save_wav(raw_audio, raw_path)

    # Generate processed audio (after AEC - what headset hears)
    print("\n=== Generating Processed Audio (After AEC) ===")
    processed = apply_aec_simulation(raw_audio)
    processed_path = output_dir / "customer_processed.wav"
    save_wav(processed, processed_path)

    print("\n=== Generated Files ===")
    print(f"1. Raw (outdoor mic):     {raw_path}")
    print(f"2. Processed (headset):   {processed_path}")
    print("\nPlay with: pw-play server/assets/customer_processed.wav")


if __name__ == "__main__":
    main()
