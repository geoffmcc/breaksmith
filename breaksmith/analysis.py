from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import librosa
import numpy as np

from .models import AudioAnalysis


DurationFit = Literal["clean", "small_tail", "extra_beat", "partial_bar"]


def _plural(value: float, singular: str, plural: str | None = None) -> str:
    if math.isclose(value, 1.0, abs_tol=0.005):
        return singular
    return plural or f"{singular}s"


def calculate_loop_fit(
    *,
    duration_seconds: float,
    bpm: float,
    steps_per_bar: int,
    grid_start_seconds: float = 0.0,
) -> dict[str, float | int | str | list[str]]:
    if bpm <= 0:
        raise ValueError("bpm must be greater than zero")
    if steps_per_bar <= 0:
        raise ValueError("steps_per_bar must be greater than zero")

    beats_per_bar = 4
    beat_duration = 60.0 / bpm
    bar_duration = beat_duration * beats_per_bar
    step_duration = bar_duration / steps_per_bar
    effective_duration = max(0.0, duration_seconds - grid_start_seconds)

    clean_tolerance = min(0.02, step_duration * 0.10)
    small_tail_tolerance = min(0.12, step_duration * 0.75)
    nearest_bar_count = max(0, round(effective_duration / bar_duration))
    nearest_bar_duration = nearest_bar_count * bar_duration
    nearest_delta = effective_duration - nearest_bar_duration

    if nearest_bar_count > 0 and abs(nearest_delta) <= clean_tolerance:
        complete_bar_count = nearest_bar_count
        remainder_seconds = 0.0
        duration_fit: DurationFit = "clean"
    else:
        complete_bar_count = max(0, int(math.floor(effective_duration / bar_duration)))
        remainder_seconds = max(0.0, effective_duration - complete_bar_count * bar_duration)
        remainder_beats = remainder_seconds / beat_duration if beat_duration else 0.0
        if remainder_seconds <= small_tail_tolerance:
            duration_fit = "small_tail"
        elif abs(remainder_beats - 1.0) <= 0.12:
            duration_fit = "extra_beat"
        else:
            duration_fit = "partial_bar"

    last_full_bar_duration = complete_bar_count * bar_duration
    remainder_beats = remainder_seconds / beat_duration if beat_duration else 0.0
    remainder_steps = remainder_seconds / step_duration if step_duration else 0.0
    suggested_bar_count = max(1, complete_bar_count)
    loop_warnings: list[str] = []

    if duration_fit == "small_tail":
        loop_warnings.append(
            f"Audio has a short {remainder_seconds:.2f}s tail beyond the "
            f"{complete_bar_count}-bar boundary."
        )
    elif duration_fit == "extra_beat":
        nearest_beat = max(1, round(remainder_beats))
        loop_warnings.append(
            f"Audio extends {remainder_seconds:.2f}s past a clean {complete_bar_count}-bar "
            f"boundary, approximately {nearest_beat} {_plural(nearest_beat, 'beat')}."
        )
    elif duration_fit == "partial_bar":
        loop_warnings.append("Source length is not aligned to complete 4/4 bars.")

    return {
        "grid_start_seconds": round(grid_start_seconds, 6),
        "effective_duration_seconds": round(effective_duration, 6),
        "beat_duration_seconds": round(beat_duration, 6),
        "bar_duration_seconds": round(bar_duration, 6),
        "step_duration_seconds": round(step_duration, 6),
        "complete_bar_count": complete_bar_count,
        "suggested_bar_count": suggested_bar_count,
        "last_full_bar_duration_seconds": round(last_full_bar_duration, 6),
        "duration_remainder_seconds": round(remainder_seconds, 6),
        "duration_remainder_beats": round(remainder_beats, 6),
        "duration_remainder_steps": round(remainder_steps, 6),
        "duration_fit": duration_fit,
        "loop_warnings": loop_warnings,
    }


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
    loop_fit = calculate_loop_fit(
        duration_seconds=duration,
        bpm=bpm,
        steps_per_bar=steps_per_bar,
        grid_start_seconds=first_beat,
    )
    if loop_fit["duration_fit"] == "clean":
        bar_count = max(1, int(loop_fit["complete_bar_count"]))
        total_steps = bar_count * steps_per_bar
    else:
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
        grid_start_seconds=float(loop_fit["grid_start_seconds"]),
        effective_duration_seconds=float(loop_fit["effective_duration_seconds"]),
        beat_duration_seconds=float(loop_fit["beat_duration_seconds"]),
        bar_duration_seconds=float(loop_fit["bar_duration_seconds"]),
        step_duration_seconds=float(loop_fit["step_duration_seconds"]),
        complete_bar_count=int(loop_fit["complete_bar_count"]),
        suggested_bar_count=int(loop_fit["suggested_bar_count"]),
        last_full_bar_duration_seconds=float(loop_fit["last_full_bar_duration_seconds"]),
        duration_remainder_seconds=float(loop_fit["duration_remainder_seconds"]),
        duration_remainder_beats=float(loop_fit["duration_remainder_beats"]),
        duration_remainder_steps=float(loop_fit["duration_remainder_steps"]),
        duration_fit=str(loop_fit["duration_fit"]),
        loop_warnings=list(loop_fit["loop_warnings"]),
        warnings=warnings,
    )
