from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .models import AudioAnalysis


def _click_pulse(
    sample_rate: int, frequency: float, duration: float, amplitude: float
) -> np.ndarray:
    length = max(1, round(sample_rate * duration))
    t = np.arange(length, dtype=float) / sample_rate
    envelope = np.exp(-t * 70.0)
    return (np.sin(2 * np.pi * frequency * t) * envelope * amplitude).astype(np.float32)


def _add_click(target: np.ndarray, start: int, pulse: np.ndarray) -> None:
    if start >= len(target):
        return
    if start < 0:
        pulse = pulse[-start:]
        start = 0
    end = min(len(target), start + len(pulse))
    if end > start:
        target[start:end] += pulse[: end - start]


def render_click_tracks(
    audio_path: Path,
    analysis: AudioAnalysis,
    output_dir: Path,
    *,
    click_filename: str = "analysis-click.wav",
    mixed_filename: str = "source-with-click.wav",
) -> tuple[Path, Path]:
    source, sample_rate = sf.read(audio_path, always_2d=True, dtype="float32")
    mono_source = source.mean(axis=1)
    click = np.zeros_like(mono_source)

    downbeat = _click_pulse(sample_rate, frequency=1760.0, duration=0.055, amplitude=0.85)
    beat = _click_pulse(sample_rate, frequency=1100.0, duration=0.035, amplitude=0.55)

    beat_index = 0
    time = analysis.grid_start_seconds
    while time < analysis.duration_seconds:
        start = round(time * sample_rate)
        _add_click(click, start, downbeat if beat_index % analysis.meter.primary_beats_per_bar == 0 else beat)
        beat_index += 1
        time = analysis.grid_start_seconds + beat_index * analysis.beat_duration_seconds

    output_dir.mkdir(parents=True, exist_ok=True)
    click_path = output_dir / click_filename
    mixed_path = output_dir / mixed_filename

    sf.write(click_path, click, sample_rate)

    mixed = source * 0.85 + click[:, np.newaxis]
    peak = float(np.max(np.abs(mixed), initial=0.0))
    if peak > 0.99:
        mixed = mixed * (0.99 / peak)
    sf.write(mixed_path, mixed, sample_rate)

    return click_path, mixed_path
