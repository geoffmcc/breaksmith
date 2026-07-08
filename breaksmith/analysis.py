from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import librosa
import numpy as np

from .models import METER_44, AudioAnalysis, Meter


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
    meter: Meter | None = None,
) -> dict[str, float | int | str | list[str]]:
    if bpm <= 0:
        raise ValueError("bpm must be greater than zero")
    if steps_per_bar <= 0:
        raise ValueError("steps_per_bar must be greater than zero")

    m = meter or METER_44
    beat_duration = m.beat_duration(bpm)
    bar_duration = m.bar_duration(bpm)
    step_duration = m.step_duration(bpm)
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
        loop_warnings.append(
            f"Source length is not aligned to complete {m.display} bars."
        )

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


def _band_mean(stft: np.ndarray, frequencies: np.ndarray, low: float, high: float) -> np.ndarray:
    mask = (frequencies >= low) & (frequencies < high)
    if np.any(mask):
        return stft[mask].mean(axis=0)
    return np.zeros(stft.shape[1], dtype=float)


def _bar_means(values: np.ndarray, steps_per_bar: int) -> list[float]:
    return [
        round(float(np.mean(values[index : index + steps_per_bar])), 6)
        for index in range(0, len(values), steps_per_bar)
    ]


def extract_activity_maps(
    *,
    y: np.ndarray,
    sample_rate: int,
    step_times: np.ndarray,
    steps_per_bar: int,
    onset_envelope: np.ndarray,
    hop_length: int,
) -> dict[str, list[float]]:
    stft = np.abs(librosa.stft(y=y, n_fft=2048, hop_length=hop_length))
    frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
    frame_times = librosa.frames_to_time(
        np.arange(stft.shape[1]),
        sr=sample_rate,
        hop_length=hop_length,
    )

    low_feature = _band_mean(stft, frequencies, 0.0, 180.0)
    low_mid_feature = _band_mean(stft, frequencies, 180.0, 500.0)
    mid_feature = _band_mean(stft, frequencies, 500.0, 3000.0)
    high_feature = _band_mean(stft, frequencies, 3000.0, float(sample_rate) / 2.0)

    onset_steps = _normalize(
        _sample_feature_at_times(onset_envelope, frame_times[: len(onset_envelope)], step_times)
    )
    low_steps = _normalize(_sample_feature_at_times(low_feature, frame_times, step_times))
    low_mid_steps = _normalize(_sample_feature_at_times(low_mid_feature, frame_times, step_times))
    mid_steps = _normalize(_sample_feature_at_times(mid_feature, frame_times, step_times))
    high_steps = _normalize(_sample_feature_at_times(high_feature, frame_times, step_times))

    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length)[0]
    rms_times = librosa.frames_to_time(
        np.arange(len(rms)),
        sr=sample_rate,
        hop_length=hop_length,
    )
    rms_steps = _normalize(_sample_feature_at_times(rms, rms_times, step_times))

    centroid = librosa.feature.spectral_centroid(S=stft, sr=sample_rate)[0]
    centroid_norm = np.clip(centroid / max(1.0, sample_rate / 2.0), 0.0, 1.0)
    brightness_steps = _normalize(_sample_feature_at_times(centroid_norm, frame_times, step_times))

    flux = np.concatenate([[0.0], np.mean(np.maximum(0.0, np.diff(stft, axis=1)), axis=0)])
    flux_steps = _normalize(_sample_feature_at_times(flux, frame_times, step_times))

    transient_steps = _normalize(np.maximum(0.0, onset_steps - rms_steps * 0.35))
    sustain_steps = _normalize(np.maximum(0.0, rms_steps - onset_steps * 0.45))
    local_density = np.convolve(onset_steps, np.ones(3) / 3, mode="same")
    silence_steps = np.clip(1.0 - rms_steps, 0.0, 1.0)

    maps = {
        "onset_activity": onset_steps,
        "low_activity": low_steps,
        "low_mid_activity": low_mid_steps,
        "mid_activity": mid_steps,
        "high_activity": high_steps,
        "rms_activity": rms_steps,
        "transient_activity": transient_steps,
        "sustain_activity": sustain_steps,
        "local_density": np.clip(local_density, 0.0, 1.0),
        "silence_activity": silence_steps,
        "brightness_activity": brightness_steps,
        "spectral_flux": flux_steps,
    }
    rounded = {
        name: [round(float(value), 6) for value in np.nan_to_num(values)]
        for name, values in maps.items()
    }
    rounded["bar_energy"] = _bar_means(rms_steps, steps_per_bar)
    rounded["bar_density"] = _bar_means(np.asarray(rounded["local_density"]), steps_per_bar)
    rounded["bar_brightness"] = _bar_means(
        np.asarray(rounded["brightness_activity"]), steps_per_bar
    )
    rounded["bar_silence"] = _bar_means(np.asarray(rounded["silence_activity"]), steps_per_bar)
    return rounded


def _coerce_tempo(value: object) -> float:
    array = np.asarray(value, dtype=float).reshape(-1)
    return float(array[0]) if array.size else 0.0


def analyze_audio(
    audio_path: Path,
    *,
    steps_per_bar: int | None = None,
    bpm_override: float | None = None,
    grid_start_override: float | None = None,
    downbeat_override: float | None = None,
    meter: Meter | None = None,
) -> AudioAnalysis:
    m = meter or METER_44
    if steps_per_bar is None:
        steps_per_bar = m.steps_per_bar
    if steps_per_bar <= 0 or steps_per_bar < m.primary_beats_per_bar:
        raise ValueError(f"steps_per_bar must be positive and at least {m.primary_beats_per_bar}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
    if not audio_path.is_file():
        raise ValueError(f"Audio path is not a file: {audio_path}")
    if grid_start_override is not None and grid_start_override < 0:
        raise ValueError("grid_start must be greater than or equal to zero")
    if downbeat_override is not None and downbeat_override < 0:
        raise ValueError("downbeat_start must be greater than or equal to zero")

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
    if grid_start_override is not None and grid_start_override >= duration:
        raise ValueError("grid_start must be earlier than the end of the audio")
    if downbeat_override is not None and downbeat_override >= duration:
        raise ValueError("downbeat_start must be earlier than the end of the audio")

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

    beat_duration = m.beat_duration(bpm)
    step_duration = m.step_duration(bpm)
    grid_start_source = "detected"
    if downbeat_override is not None:
        first_beat = float(downbeat_override)
        grid_start_source = "manual_downbeat"
        warnings.append(f"Manual downbeat start override applied at {first_beat:.3f}s.")
    elif grid_start_override is not None:
        first_beat = float(grid_start_override)
        grid_start_source = "manual_grid_start"
        warnings.append(f"Manual grid start override applied at {first_beat:.3f}s.")
    elif beat_times_detected.size >= 2:
        first_beat = float(beat_times_detected[0])
    else:
        first_beat = 0.0
        grid_start_source = "audio_start"
        warnings.append("Few reliable beats were found; the grid begins at the audio start.")

    # Include the beginning when the first tracked beat is implausibly late.
    if grid_start_source == "detected" and first_beat > beat_duration * 1.5:
        first_beat = 0.0
        grid_start_source = "audio_start"
        warnings.append("Tracked downbeat was late; the grid was anchored to 0 seconds.")

    usable_duration = max(0.0, duration - first_beat)
    detected_beat_count = int(beat_times_detected.size)
    expected_beat_count = max(1, round(usable_duration / beat_duration))
    beat_confidence = min(1.0, detected_beat_count / expected_beat_count)
    tempo_confidence = 1.0 if bpm_override is not None else beat_confidence
    if beat_confidence < 0.35:
        warnings.append(
            f"Beat confidence is low ({beat_confidence:.2f}); verify the grid with a click render."
        )
    loop_fit = calculate_loop_fit(
        duration_seconds=duration,
        bpm=bpm,
        steps_per_bar=steps_per_bar,
        grid_start_seconds=first_beat,
        meter=m,
    )
    if loop_fit["duration_fit"] == "clean":
        bar_count = max(1, int(loop_fit["complete_bar_count"]))
        total_steps = bar_count * steps_per_bar
    else:
        total_steps = max(steps_per_bar, int(math.ceil(usable_duration / step_duration)))
        bar_count = max(1, int(math.ceil(total_steps / steps_per_bar)))
        total_steps = bar_count * steps_per_bar

    step_times = first_beat + np.arange(total_steps, dtype=float) * step_duration
    beat_times = first_beat + np.arange(
        bar_count * m.primary_beats_per_bar, dtype=float
    ) * beat_duration

    activity_maps = extract_activity_maps(
        y=y,
        sample_rate=sample_rate,
        step_times=step_times,
        steps_per_bar=steps_per_bar,
        onset_envelope=onset_envelope,
        hop_length=hop_length,
    )

    return AudioAnalysis(
        source=str(audio_path.resolve()),
        duration_seconds=round(duration, 6),
        sample_rate=int(sample_rate),
        bpm=round(bpm, 4),
        beat_times=[round(float(value), 6) for value in beat_times if value < duration],
        bar_count=bar_count,
        steps_per_bar=steps_per_bar,
        step_times=[round(float(value), 6) for value in step_times],
        onset_activity=activity_maps["onset_activity"],
        low_activity=activity_maps["low_activity"],
        high_activity=activity_maps["high_activity"],
        bar_energy=activity_maps["bar_energy"],
        low_mid_activity=activity_maps["low_mid_activity"],
        mid_activity=activity_maps["mid_activity"],
        rms_activity=activity_maps["rms_activity"],
        transient_activity=activity_maps["transient_activity"],
        sustain_activity=activity_maps["sustain_activity"],
        local_density=activity_maps["local_density"],
        silence_activity=activity_maps["silence_activity"],
        brightness_activity=activity_maps["brightness_activity"],
        spectral_flux=activity_maps["spectral_flux"],
        bar_density=activity_maps["bar_density"],
        bar_brightness=activity_maps["bar_brightness"],
        bar_silence=activity_maps["bar_silence"],
        meter=m,
        grid_start_seconds=float(loop_fit["grid_start_seconds"]),
        downbeat_seconds=float(loop_fit["grid_start_seconds"]),
        grid_start_source=grid_start_source,
        tempo_confidence=round(float(tempo_confidence), 6),
        beat_confidence=round(float(beat_confidence), 6),
        detected_beat_count=detected_beat_count,
        expected_beat_count=expected_beat_count,
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
