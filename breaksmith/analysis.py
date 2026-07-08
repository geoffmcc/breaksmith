from __future__ import annotations

import math
from pathlib import Path

import librosa
import numpy as np

from .models import AudioAnalysis


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.nan_to_num(np.asarray(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    if values.size == 0:
        return values
    lo = float(np.percentile(values, 5))
    hi = float(np.percentile(values, 95))
    if hi <= lo:
        maximum = float(values.max(initial=0.0))
        return values / maximum if maximum > 0 else np.zeros_like(values)
    return np.clip((values - lo) / (hi - lo), 0.0, 1.0)


def _sample_feature_at_times(
    feature: np.ndarray,
    frame_times: np.ndarray,
    sample_times: np.ndarray,
) -> np.ndarray:
    if feature.size == 0 or frame_times.size == 0:
        return np.zeros(sample_times.size, dtype=float)
    indexes = np.searchsorted(frame_times, sample_times, side="left")
    indexes = np.clip(indexes, 0, len(feature) - 1)
    return feature[indexes]


def _coerce_tempo(value: object) -> float:
    array = np.asarray(value, dtype=float).reshape(-1)
    return float(array[0]) if array.size else 0.0


def analyze_audio(
    audio_path: Path,
    *,
    steps_per_bar: int = 16,
    bpm_override: float | None = None,
) -> AudioAnalysis:
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
    if not audio_path.is_file():
        raise ValueError(f"Audio path is not a file: {audio_path}")
    if steps_per_bar <= 0 or steps_per_bar % 4 != 0:
        raise ValueError("steps_per_bar must be a positive multiple of four")

    try:
        y, sample_rate = librosa.load(audio_path, sr=None, mono=True)
    except Exception as exc:
        raise RuntimeError(
            f"Could not decode {audio_path}. Confirm the file is valid and FFmpeg is installed."
        ) from exc

    if y.size == 0:
        raise ValueError("The audio file contains no decodable samples")

    duration = float(librosa.get_duration(y=y, sr=sample_rate))
    if duration < 1.0:
        raise ValueError("The audio file is too short; use at least one second")

    hop_length = 512
    onset_envelope = librosa.onset.onset_strength(
        y=y,
        sr=sample_rate,
        hop_length=hop_length,
        aggregate=np.median,
    )

    estimated_tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_envelope,
        sr=sample_rate,
        hop_length=hop_length,
        units="frames",
        trim=False,
    )
    bpm = float(bpm_override) if bpm_override is not None else _coerce_tempo(estimated_tempo)
    warnings: list[str] = []

    if not math.isfinite(bpm) or bpm <= 0:
        bpm = 172.0
        warnings.append("Tempo could not be estimated; defaulted to 172 BPM.")

    # Keep likely half/double-time estimates in a useful DnB range.
    if bpm_override is None:
        while bpm < 120:
            bpm *= 2
        while bpm > 220:
            bpm /= 2

    beat_times_detected = librosa.frames_to_time(
        beat_frames,
        sr=sample_rate,
        hop_length=hop_length,
    ).astype(float)

    beat_duration = 60.0 / bpm
    if beat_times_detected.size >= 2:
        first_beat = float(beat_times_detected[0])
    else:
        first_beat = 0.0
        warnings.append("Few reliable beats were found; the grid begins at the audio start.")

    # Include the beginning when the first tracked beat is implausibly late.
    if first_beat > beat_duration * 1.5:
        first_beat = 0.0
        warnings.append("Tracked downbeat was late; the grid was anchored to 0 seconds.")

    beats_per_bar = 4
    step_duration = beat_duration * beats_per_bar / steps_per_bar
    usable_duration = max(0.0, duration - first_beat)
    total_steps = max(steps_per_bar, int(math.ceil(usable_duration / step_duration)))
    bar_count = max(1, int(math.ceil(total_steps / steps_per_bar)))
    total_steps = bar_count * steps_per_bar

    step_times = first_beat + np.arange(total_steps, dtype=float) * step_duration
    beat_times = first_beat + np.arange(bar_count * beats_per_bar, dtype=float) * beat_duration

    stft = np.abs(librosa.stft(y=y, n_fft=2048, hop_length=hop_length))
    frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
    frame_times = librosa.frames_to_time(
        np.arange(stft.shape[1]),
        sr=sample_rate,
        hop_length=hop_length,
    )

    low_mask = frequencies <= 180.0
    high_mask = frequencies >= 3000.0
    low_feature = stft[low_mask].mean(axis=0) if np.any(low_mask) else np.zeros(stft.shape[1])
    high_feature = stft[high_mask].mean(axis=0) if np.any(high_mask) else np.zeros(stft.shape[1])

    onset_steps = _normalize(
        _sample_feature_at_times(onset_envelope, frame_times[: len(onset_envelope)], step_times)
    )
    low_steps = _normalize(_sample_feature_at_times(low_feature, frame_times, step_times))
    high_steps = _normalize(_sample_feature_at_times(high_feature, frame_times, step_times))

    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]
    rms_times = librosa.frames_to_time(
        np.arange(len(rms)),
        sr=sample_rate,
        hop_length=hop_length,
    )
    rms_steps = _normalize(_sample_feature_at_times(rms, rms_times, step_times))
    bar_energy = [
        float(np.mean(rms_steps[index : index + steps_per_bar]))
        for index in range(0, total_steps, steps_per_bar)
    ]

    return AudioAnalysis(
        source=str(audio_path.resolve()),
        duration_seconds=round(duration, 6),
        sample_rate=int(sample_rate),
        bpm=round(bpm, 4),
        beat_times=[round(float(value), 6) for value in beat_times if value < duration],
        bar_count=bar_count,
        steps_per_bar=steps_per_bar,
        step_times=[round(float(value), 6) for value in step_times],
        onset_activity=[round(float(value), 6) for value in onset_steps],
        low_activity=[round(float(value), 6) for value in low_steps],
        high_activity=[round(float(value), 6) for value in high_steps],
        bar_energy=[round(float(value), 6) for value in bar_energy],
        warnings=warnings,
    )
