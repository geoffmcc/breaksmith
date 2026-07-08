from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .models import DrumPattern


def _envelope_decay(length: int, rate: float, sample_rate: int = 44100) -> np.ndarray:
    t = np.arange(length, dtype=float) / sample_rate
    return np.exp(-t * rate)


def _white_noise(length: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, length).astype(np.float32)


def render_kick(
    sample_rate: int, duration: float, amplitude: float = 1.0, seed: int = 0
) -> np.ndarray:
    length = max(1, round(sample_rate * duration))
    t = np.arange(length, dtype=float) / sample_rate
    freq = np.maximum(150.0 - t * 130.0, 40.0)
    phase = np.cumsum(2.0 * np.pi * freq / sample_rate)
    env = _envelope_decay(length, 35.0, sample_rate)
    return (np.sin(phase) * env * amplitude).astype(np.float32)


def render_snare(
    sample_rate: int, duration: float, amplitude: float = 1.0, seed: int = 0
) -> np.ndarray:
    length = max(1, round(sample_rate * duration))
    t = np.arange(length, dtype=float) / sample_rate
    tone = np.sin(2.0 * np.pi * 200.0 * t) * _envelope_decay(length, 30.0, sample_rate) * 0.4
    noise = _white_noise(length, seed) * _envelope_decay(length, 22.0, sample_rate) * 0.6
    return ((tone + noise) * amplitude).astype(np.float32)


def render_closed_hat(
    sample_rate: int, duration: float, amplitude: float = 1.0, seed: int = 0
) -> np.ndarray:
    length = max(1, round(sample_rate * duration))
    env = _envelope_decay(length, 55.0, sample_rate)
    return (_white_noise(length, seed) * env * amplitude).astype(np.float32)


def render_open_hat(
    sample_rate: int, duration: float, amplitude: float = 1.0, seed: int = 0
) -> np.ndarray:
    length = max(1, round(sample_rate * duration))
    env = _envelope_decay(length, 10.0, sample_rate)
    return (_white_noise(length, seed) * env * amplitude).astype(np.float32)


def render_percussion(
    sample_rate: int, duration: float, amplitude: float = 1.0, seed: int = 0
) -> np.ndarray:
    length = max(1, round(sample_rate * duration))
    t = np.arange(length, dtype=float) / sample_rate
    env = _envelope_decay(length, 28.0, sample_rate)
    return (np.sin(2.0 * np.pi * 350.0 * t) * env * amplitude).astype(np.float32)


INSTRUMENT_RENDERERS = {
    "kick": render_kick,
    "snare": render_snare,
    "closed_hat": render_closed_hat,
    "open_hat": render_open_hat,
    "percussion": render_percussion,
}

INSTRUMENT_DURATIONS = {
    "kick": 0.18,
    "snare": 0.14,
    "closed_hat": 0.05,
    "open_hat": 0.22,
    "percussion": 0.10,
}


def render_preview(pattern: DrumPattern, sample_rate: int = 44100, seed: int = 0) -> np.ndarray:
    step_duration = (60.0 / pattern.bpm) * pattern.meter.primary_beats_per_bar / pattern.steps_per_bar
    total_seconds = pattern.bars * pattern.steps_per_bar * step_duration
    padding = max(INSTRUMENT_DURATIONS.values()) * 1.2
    total_samples = max(1, round((total_seconds + padding) * sample_rate))
    audio = np.zeros(total_samples, dtype=np.float32)

    instrument_seed_offset = seed
    for instrument, hits in pattern.hits.items():
        renderer = INSTRUMENT_RENDERERS.get(instrument)
        duration = INSTRUMENT_DURATIONS.get(instrument, 0.1)
        if renderer is None:
            continue
        instrument_seed_offset += 1
        for hit in hits:
            offset_steps = hit.bar * pattern.steps_per_bar + hit.step + hit.timing_offset_steps
            start = round(offset_steps * step_duration * sample_rate)
            if start >= len(audio):
                continue
            sound = renderer(
                sample_rate,
                duration,
                amplitude=hit.velocity / 127.0,
                seed=instrument_seed_offset + hit.bar * 1000 + hit.step,
            )
            if start < 0:
                sound = sound[-start:]
                start = 0
            end = min(len(audio), start + len(sound))
            if end > start:
                audio[start:end] += sound[: end - start]

    peak = float(np.max(np.abs(audio), initial=0.0))
    if peak > 0.99:
        audio = audio * (0.99 / peak)

    return audio


def write_preview(
    pattern: DrumPattern, output_path: Path, sample_rate: int = 44100, seed: int = 0
) -> Path:
    audio = render_preview(pattern, sample_rate=sample_rate, seed=seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, audio, sample_rate)
    return output_path
