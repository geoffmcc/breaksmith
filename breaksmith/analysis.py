from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import librosa
import numpy as np

from .models import METER_44, AudioAnalysis, Meter, TempoCandidateDiagnostic, TempoScoreComponents


DurationFit = Literal["clean", "small_tail", "extra_beat", "partial_bar"]


@dataclass(frozen=True, slots=True)
class TempoScoringConfig:
    min_bpm: float = 45.0
    max_bpm: float = 240.0
    normal_min_bpm: float = 80.0
    normal_max_bpm: float = 180.0
    max_candidates: int = 5
    near_tie_threshold: float = 0.08
    duplicate_relative_tolerance: float = 0.001
    octave_shifts: tuple[int, ...] = (-1, 0, 1, 2, 3)
    weights: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.weights is None:
            object.__setattr__(
                self,
                "weights",
                {
                    "bpm_plausibility": 0.16,
                    "onset_spacing": 0.24,
                    "bar_fit": 0.18,
                    "beat_fit": 0.08,
                    "bar_count_plausibility": 0.10,
                    "beat_count_plausibility": 0.08,
                    "raw_proximity": 0.08,
                    "detector_confidence": 0.04,
                    "grid_fit": 0.04,
                },
            )


TEMPO_SCORING = TempoScoringConfig()


@dataclass(frozen=True, slots=True)
class TempoGridSelection:
    bpm: float
    grid_start_seconds: float
    grid_start_source: str
    score: float
    bar_fit_score: float
    onset_spacing_score: float
    beat_confidence: float
    expected_beat_count: int
    loop_fit: dict[str, float | int | str | list[str]]
    reason: str
    octave_shift: int
    octave_multiplier: float
    tempo_source: str
    ambiguous: bool
    tie_break: str


@dataclass(frozen=True, slots=True)
class TempoGridDiagnostics:
    raw_detected_bpm: float
    candidate_bpm_values: list[float]
    candidates: list[TempoCandidateDiagnostic]
    selection: TempoGridSelection


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


def _octave_multiplier(octave_shift: int) -> float:
    return float(2**octave_shift) if octave_shift >= 0 else 1.0 / float(2 ** abs(octave_shift))


def _tempo_candidate_specs(
    raw_bpm: float,
    bpm_override: float | None,
    config: TempoScoringConfig = TEMPO_SCORING,
) -> list[tuple[float, int, float, bool, str]]:
    if bpm_override is not None:
        return [(float(bpm_override), 0, 1.0, True, "")]
    if not math.isfinite(raw_bpm) or raw_bpm <= 0:
        return [(172.0, 0, 1.0, True, "detector did not return a finite positive BPM")]

    specs: list[tuple[float, int, float, bool, str]] = []
    accepted_bpms: list[float] = []
    for shift in config.octave_shifts:
        multiplier = _octave_multiplier(shift)
        bpm = raw_bpm * multiplier
        duplicate = any(
            math.isclose(bpm, existing, rel_tol=config.duplicate_relative_tolerance)
            for existing in accepted_bpms
        )
        if duplicate:
            specs.append((bpm, shift, multiplier, False, "duplicate octave candidate"))
            continue
        if bpm < config.min_bpm or bpm > config.max_bpm:
            specs.append((bpm, shift, multiplier, False, "outside supported BPM range"))
            continue
        if len(accepted_bpms) >= config.max_candidates:
            specs.append((bpm, shift, multiplier, False, "candidate limit reached"))
            continue
        accepted_bpms.append(bpm)
        specs.append((bpm, shift, multiplier, True, ""))
    return specs


def _plausible_bpm_score(bpm: float, config: TempoScoringConfig = TEMPO_SCORING) -> float:
    if config.normal_min_bpm <= bpm <= config.normal_max_bpm:
        return 1.0
    if 60.0 <= bpm <= 220.0:
        return 0.75
    if config.min_bpm <= bpm <= config.max_bpm:
        return 0.45
    return 0.0


def _bar_fit_score(loop_fit: dict[str, float | int | str | list[str]]) -> float:
    fit = loop_fit["duration_fit"]
    if fit == "clean":
        return 1.0
    if fit == "small_tail":
        return 0.85
    if fit == "extra_beat":
        return 0.45

    bar_duration = float(loop_fit["bar_duration_seconds"])
    remainder = float(loop_fit["duration_remainder_seconds"])
    if bar_duration <= 0:
        return 0.0
    nearest_boundary = min(remainder, max(0.0, bar_duration - remainder))
    return max(0.0, 1.0 - nearest_boundary / (bar_duration * 0.5))


def _beat_fit_score(error_seconds: float, beat_duration: float) -> float:
    if beat_duration <= 0:
        return 0.0
    return max(0.0, 1.0 - error_seconds / (beat_duration * 0.5))


def _count_plausibility(count: float, *, ideal_min: int, ideal_max: int) -> float:
    if count <= 0:
        return 0.0
    if ideal_min <= count <= ideal_max:
        return 1.0
    if count < ideal_min:
        return max(0.35, count / ideal_min)
    return max(0.35, 1.0 - (count - ideal_max) / ideal_max)


def _onset_spacing_score(beat_times: np.ndarray, bpm: float, meter: Meter) -> float:
    if beat_times.size < 2 or bpm <= 0:
        return 0.5
    intervals = np.diff(beat_times)
    intervals = intervals[intervals > 0.02]
    if intervals.size == 0:
        return 0.5

    median_interval = float(np.median(intervals))
    beat_duration = meter.beat_duration(bpm)
    multipliers = (
        (1.0, 1.0),
        (2.0, 0.9),
        (float(meter.primary_beats_per_bar), 0.95),
        (float(meter.primary_beats_per_bar * 2), 0.65),
    )
    best = 0.0
    for multiplier, weight in multipliers:
        expected = beat_duration * multiplier
        if expected <= 0:
            continue
        relative_error = abs(median_interval - expected) / expected
        best = max(best, weight * max(0.0, 1.0 - relative_error))
    return min(1.0, best)


def _onset_evidence_label(beat_times: np.ndarray, bpm: float, meter: Meter) -> str:
    if beat_times.size < 2 or bpm <= 0:
        return "unavailable"
    intervals = np.diff(beat_times)
    intervals = intervals[intervals > 0.02]
    if intervals.size == 0:
        return "unavailable"
    median_interval = float(np.median(intervals))
    beat_duration = meter.beat_duration(bpm)
    if beat_duration <= 0:
        return "unavailable"
    ratio = median_interval / beat_duration
    if abs(ratio - 1.0) <= 0.15:
        return "primary-beat spacing"
    if abs(ratio - 2.0) <= 0.20:
        return "half-time beat spacing"
    if abs(ratio - meter.primary_beats_per_bar) <= 0.35:
        return "bar/downbeat spacing"
    return f"spacing ratio {ratio:.2f} beats"


def _grid_alignment_score(beat_times: np.ndarray, bpm: float, grid_start: float, meter: Meter) -> float:
    if beat_times.size == 0 or bpm <= 0:
        return 0.75 if math.isclose(grid_start, 0.0, abs_tol=0.001) else 0.5
    beat_duration = meter.beat_duration(bpm)
    if beat_duration <= 0:
        return 0.0
    usable = beat_times[beat_times >= grid_start - beat_duration * 0.25]
    if usable.size == 0:
        return 0.5
    offsets = np.mod(usable - grid_start, beat_duration)
    distances = np.minimum(offsets, beat_duration - offsets) / beat_duration
    return max(0.0, 1.0 - float(np.mean(np.clip(distances, 0.0, 0.5))) * 2.0)


def _detector_confidence_for_candidate(
    *,
    beat_times: np.ndarray,
    duration: float,
    grid_start: float,
    bpm: float,
    meter: Meter,
) -> tuple[float, int]:
    beat_duration = meter.beat_duration(bpm)
    if beat_duration <= 0:
        return 0.0, 1
    expected_beats = max(1, round(max(0.0, duration - grid_start) / beat_duration))
    confidence = min(1.0, int(beat_times.size) / expected_beats)
    return confidence, expected_beats


def _candidate_score(components: TempoScoreComponents, config: TempoScoringConfig) -> float:
    weights = config.weights or {}
    return sum(
        getattr(components, name) * weight
        for name, weight in weights.items()
    )


def _grid_start_candidates(
    *,
    beat_times: np.ndarray,
    duration: float,
    grid_start_override: float | None,
    downbeat_override: float | None,
) -> list[tuple[float, str]]:
    if downbeat_override is not None:
        return [(float(downbeat_override), "manual_downbeat")]
    if grid_start_override is not None:
        return [(float(grid_start_override), "manual_grid_start")]
    candidates: list[tuple[float, str]] = [(0.0, "audio_start")]
    if beat_times.size >= 2:
        first = float(beat_times[0])
        if 0.0 <= first < duration and not math.isclose(first, 0.0, abs_tol=0.001):
            candidates.append((first, "detected"))
    return candidates


def select_tempo_grid(
    *,
    raw_detected_bpm: float,
    beat_times_detected: np.ndarray,
    duration: float,
    steps_per_bar: int,
    meter: Meter,
    bpm_override: float | None = None,
    grid_start_override: float | None = None,
    downbeat_override: float | None = None,
) -> TempoGridDiagnostics:
    """Score bounded tempo-octave and grid-start pairs as one conservative decision."""
    config = TEMPO_SCORING
    grid_values = _grid_start_candidates(
        beat_times=beat_times_detected,
        duration=duration,
        grid_start_override=grid_start_override,
        downbeat_override=downbeat_override,
    )
    selections: list[TempoGridSelection] = []
    diagnostics: list[TempoCandidateDiagnostic] = []

    for bpm, octave_shift, octave_multiplier, valid, rejection_reason in _tempo_candidate_specs(
        raw_detected_bpm,
        bpm_override,
        config,
    ):
        if not valid:
            diagnostics.append(
                TempoCandidateDiagnostic(
                    bpm=round(float(bpm), 4),
                    valid=False,
                    octave_shift=octave_shift,
                    octave_multiplier=round(float(octave_multiplier), 6),
                    rejection_reason=rejection_reason,
                    rationale=rejection_reason,
                )
            )
            continue
        beat_duration = meter.beat_duration(bpm)
        bar_duration = meter.bar_duration(bpm)
        if beat_duration <= 0 or bar_duration <= 0:
            diagnostics.append(
                TempoCandidateDiagnostic(
                    bpm=round(float(bpm), 4),
                    valid=False,
                    octave_shift=octave_shift,
                    octave_multiplier=round(float(octave_multiplier), 6),
                    rejection_reason="invalid beat or bar duration",
                    rationale="invalid beat or bar duration",
                )
            )
            continue

        spacing_score = _onset_spacing_score(beat_times_detected, bpm, meter)
        plausible_score = _plausible_bpm_score(bpm, config)
        raw_proximity = max(0.0, 1.0 - abs(octave_shift) / max(1, max(abs(s) for s in config.octave_shifts)))
        for grid_start, source in grid_values:
            if grid_start >= duration:
                diagnostics.append(
                    TempoCandidateDiagnostic(
                        bpm=round(float(bpm), 4),
                        valid=False,
                        octave_shift=octave_shift,
                        octave_multiplier=round(float(octave_multiplier), 6),
                        grid_start_seconds=round(float(grid_start), 6),
                        grid_start_source=source,
                        rejection_reason="grid start is outside source duration",
                        rationale="grid start is outside source duration",
                    )
                )
                continue
            loop_fit = calculate_loop_fit(
                duration_seconds=duration,
                bpm=bpm,
                steps_per_bar=steps_per_bar,
                grid_start_seconds=grid_start,
                meter=meter,
            )
            effective_duration = max(0.0, duration - grid_start)
            inferred_beats = effective_duration / beat_duration
            inferred_bars = effective_duration / bar_duration
            nearest_beats = max(1, round(inferred_beats))
            nearest_bars = max(1, round(inferred_bars))
            beat_fit_error = abs(effective_duration - nearest_beats * beat_duration)
            bar_fit_error = abs(effective_duration - nearest_bars * bar_duration)
            beat_confidence, expected_beats = _detector_confidence_for_candidate(
                beat_times=beat_times_detected,
                duration=duration,
                grid_start=grid_start,
                bpm=bpm,
                meter=meter,
            )
            bar_score = _bar_fit_score(loop_fit)
            beat_score = _beat_fit_score(beat_fit_error, beat_duration)
            grid_score = _grid_alignment_score(beat_times_detected, bpm, grid_start, meter)
            bar_count_score = _count_plausibility(inferred_bars, ideal_min=2, ideal_max=64)
            beat_count_score = _count_plausibility(inferred_beats, ideal_min=meter.primary_beats_per_bar * 2, ideal_max=256)
            components = TempoScoreComponents(
                bpm_plausibility=plausible_score,
                onset_spacing=spacing_score,
                bar_fit=bar_score,
                beat_fit=beat_score,
                bar_count_plausibility=bar_count_score,
                beat_count_plausibility=beat_count_score,
                raw_proximity=raw_proximity,
                detector_confidence=beat_confidence,
                grid_fit=grid_score,
            )
            score = _candidate_score(components, config)
            onset_label = _onset_evidence_label(beat_times_detected, bpm, meter)
            rationale = (
                f"bar_fit={bar_score:.2f}, beat_fit={beat_score:.2f}, "
                f"onset_spacing={spacing_score:.2f}, bpm_plausibility={plausible_score:.2f}"
            )
            diagnostic = TempoCandidateDiagnostic(
                bpm=round(float(bpm), 4),
                valid=True,
                octave_shift=octave_shift,
                octave_multiplier=round(float(octave_multiplier), 6),
                grid_start_seconds=round(float(grid_start), 6),
                grid_start_source=source,
                total_score=round(float(score), 6),
                score_components=components,
                inferred_beats=round(float(inferred_beats), 6),
                inferred_bars=round(float(inferred_bars), 6),
                nearest_whole_beats=nearest_beats,
                nearest_whole_bars=nearest_bars,
                beat_fit_error_seconds=round(float(beat_fit_error), 6),
                bar_fit_error_seconds=round(float(bar_fit_error), 6),
                fit_classification=str(loop_fit["duration_fit"]),
                onset_evidence=onset_label,
                confidence_contribution=round(float(beat_confidence), 6),
                rationale=rationale,
            )
            diagnostics.append(diagnostic)
            selections.append(
                TempoGridSelection(
                    bpm=bpm,
                    grid_start_seconds=grid_start,
                    grid_start_source=source,
                    score=score,
                    bar_fit_score=bar_score,
                    onset_spacing_score=spacing_score,
                    beat_confidence=beat_confidence,
                    expected_beat_count=expected_beats,
                    loop_fit=loop_fit,
                    reason=rationale,
                    octave_shift=octave_shift,
                    octave_multiplier=octave_multiplier,
                    tempo_source="user-supplied" if bpm_override is not None else "detected",
                    ambiguous=False,
                    tie_break="highest score",
                )
            )

    if not selections:
        raise ValueError("No valid tempo/grid candidates were available")

    best = max(selections, key=lambda candidate: candidate.score)
    original_candidates = [candidate for candidate in selections if candidate.octave_shift == 0]
    original = max(original_candidates, key=lambda candidate: candidate.score) if original_candidates else None
    ambiguous = False
    tie_break = "highest score"
    if bpm_override is None and original is not None and best.octave_shift != 0:
        improvement = best.score - original.score
        if improvement < config.near_tie_threshold:
            best = original
            ambiguous = True
            tie_break = (
                f"retained original tempo; best octave improvement {improvement:.3f} "
                f"below {config.near_tie_threshold:.3f} threshold"
            )
        else:
            tie_break = f"octave candidate improved score by {improvement:.3f}"
    else:
        near = [
            candidate for candidate in selections
            if abs(candidate.score - best.score) < config.near_tie_threshold
        ]
        ambiguous = len(near) > 1
        if ambiguous and bpm_override is None:
            tie_break = "near-tie resolved by original/fewer octave shifts/deterministic ordering"

    tempo_source = "user-supplied" if bpm_override is not None else (
        "octave-corrected" if best.octave_shift != 0 else "detected"
    )
    selection = TempoGridSelection(
        bpm=best.bpm,
        grid_start_seconds=best.grid_start_seconds,
        grid_start_source=best.grid_start_source,
        score=best.score,
        bar_fit_score=best.bar_fit_score,
        onset_spacing_score=best.onset_spacing_score,
        beat_confidence=best.beat_confidence,
        expected_beat_count=best.expected_beat_count,
        loop_fit=best.loop_fit,
        reason=best.reason,
        octave_shift=best.octave_shift,
        octave_multiplier=best.octave_multiplier,
        tempo_source=tempo_source,
        ambiguous=ambiguous,
        tie_break=tie_break,
    )
    for diagnostic in diagnostics:
        if diagnostic.valid and math.isclose(diagnostic.bpm, selection.bpm, rel_tol=0.0001) and math.isclose(
            diagnostic.grid_start_seconds,
            selection.grid_start_seconds,
            abs_tol=0.000001,
        ):
            diagnostic.tie_break_outcome = "selected"
        elif diagnostic.valid and diagnostic.octave_shift == 0 and ambiguous:
            diagnostic.tie_break_outcome = "retained by ambiguity policy"
    return TempoGridDiagnostics(
        raw_detected_bpm=raw_detected_bpm,
        candidate_bpm_values=sorted({candidate.bpm for candidate in diagnostics if candidate.valid}),
        candidates=diagnostics,
        selection=selection,
    )


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
    raw_detected_bpm = _coerce_tempo(estimated_tempo)
    warnings: list[str] = []

    if bpm_override is None and (not math.isfinite(raw_detected_bpm) or raw_detected_bpm <= 0):
        raw_detected_bpm = 172.0
        warnings.append("Tempo could not be estimated; defaulted to 172 BPM.")

    beat_times_detected = librosa.frames_to_time(
        beat_frames,
        sr=sample_rate,
        hop_length=hop_length,
    ).astype(float)

    tempo_grid = select_tempo_grid(
        raw_detected_bpm=raw_detected_bpm,
        beat_times_detected=beat_times_detected,
        duration=duration,
        steps_per_bar=steps_per_bar,
        meter=m,
        bpm_override=bpm_override,
        grid_start_override=grid_start_override,
        downbeat_override=downbeat_override,
    )
    selection = tempo_grid.selection
    bpm = selection.bpm
    first_beat = selection.grid_start_seconds
    grid_start_source = selection.grid_start_source
    loop_fit = selection.loop_fit

    beat_duration = m.beat_duration(bpm)
    step_duration = m.step_duration(bpm)
    if downbeat_override is not None:
        warnings.append(f"Manual downbeat start override applied at {selection.grid_start_seconds:.3f}s.")
    elif grid_start_override is not None:
        warnings.append(f"Manual grid start override applied at {selection.grid_start_seconds:.3f}s.")
    elif beat_times_detected.size < 2:
        warnings.append("Few reliable beats were found; the grid begins at the audio start.")

    usable_duration = max(0.0, duration - first_beat)
    detected_beat_count = int(beat_times_detected.size)
    expected_beat_count = selection.expected_beat_count
    beat_confidence = selection.beat_confidence
    tempo_confidence = 1.0 if bpm_override is not None else min(1.0, selection.score)
    if beat_confidence < 0.35:
        warnings.append(
            f"Beat confidence is low ({beat_confidence:.2f}); verify the grid with a click render."
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
        raw_detected_bpm=round(float(tempo_grid.raw_detected_bpm), 4),
        candidate_bpm_values=tempo_grid.candidate_bpm_values,
        tempo_selection_score=round(float(selection.score), 6),
        tempo_selection_reason=selection.reason,
        bar_fit_score=round(float(selection.bar_fit_score), 6),
        tempo_source=selection.tempo_source,
        octave_correction_applied=selection.octave_shift != 0 and bpm_override is None,
        octave_multiplier=round(float(selection.octave_multiplier), 6),
        octave_shift=selection.octave_shift,
        tempo_ambiguous=selection.ambiguous,
        tempo_tie_break=selection.tie_break,
        tempo_candidates=tempo_grid.candidates,
    )
