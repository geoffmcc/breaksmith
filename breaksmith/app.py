from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
import soundfile as sf

from .analysis import analyze_audio
from .click import render_click_tracks
from .exporters.json_export import write_analysis, write_feature_csv, write_pattern
from .exporters.midi import write_midi
from .exporters.strudel import write_strudel
from .generator import STYLE_CONFIG, generate_pattern
from .generator_shared import GenerationControls
from .models import (
    ALL_STYLES,
    ARRANGEMENT_PRESETS,
    DEFAULT_STYLE_PER_GENRE,
    GENRE_CONTROL_DEFAULTS,
    HIPHOP_STYLES,
    AudioAnalysis,
    DrumPattern,
    Meter,
    Section,
    arrangement_bar_count,
    ensure_output_dir,
    parse_time_signature,
    resolve_genre,
    validate_beat_grouping,
    validate_style_genre,
)
from .run import allocate_run_context, load_run_manifest
from .synth import render_preview, write_preview


ProgressStage = Literal[
    "validating",
    "metadata",
    "analyzing",
    "writing",
    "generating",
    "rendering_preview",
    "complete",
]


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: ProgressStage
    message: str
    current: int | None = None
    total: int | None = None


ProgressCallback = Callable[[ProgressEvent], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    path: Path
    filename: str
    duration_seconds: float
    sample_rate: int
    channels: int
    frames: int
    format: str
    subtype: str
    file_size: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


@dataclass(frozen=True, slots=True)
class WaveformPeaks:
    source: Path
    duration_seconds: float
    sample_rate: int
    peaks: list[tuple[float, float]]


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    audio: Path
    output: Path = Path("output")
    bpm: float | None = None
    steps_per_bar: int | None = None
    grid_start: float | None = None
    downbeat_start: float | None = None
    time_signature: str = "4/4"
    beat_grouping: str | None = None
    render_click: bool = False
    features_csv: Path | None = None


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    request: AnalysisRequest
    analysis: AudioAnalysis
    run_dir: Path
    manifest_path: Path
    artifacts: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    audio: Path
    output: Path = Path("output")
    style: str = "all"
    genre: str | None = None
    seed: int = 42
    variants: int = 1
    bpm: float | None = None
    steps_per_bar: int | None = None
    grid_start: float | None = None
    downbeat_start: float | None = None
    bars: int | None = None
    structure: str | None = None
    density: float | None = None
    swing: float | None = None
    humanize: float | None = None
    variation: float | None = None
    phrase_awareness: float = 0.3
    groove: str = "straight"
    preview: bool = False
    preview_bars: int | None = None
    preview_comparison: bool = False
    source_restraint: float | None = None
    kick_density: float | None = None
    snare_density: float | None = None
    hat_density: float | None = None
    open_hat_density: float | None = None
    percussion_density: float | None = None
    midi_velocity_curve: str = "linear"
    time_signature: str = "4/4"
    beat_grouping: str | None = None


@dataclass(frozen=True, slots=True)
class GeneratedPatternResult:
    label: str
    style: str
    variant: int
    seed: int
    pattern: DrumPattern
    directory: Path
    artifacts: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    request: GenerationRequest
    analysis: AudioAnalysis
    controls: GenerationControls
    run_dir: Path
    manifest_path: Path
    results: list[GeneratedPatternResult]
    artifacts: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)


def _emit(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    if callback is not None:
        callback(event)


def _check_cancel(check: CancelCheck | None) -> None:
    if check is not None and check():
        raise InterruptedError("Operation canceled")


def resolve_meter(time_signature: str, beat_grouping: str | None) -> Meter:
    meter = parse_time_signature(time_signature)
    return validate_beat_grouping(meter, beat_grouping) if beat_grouping is not None else meter


def read_source_metadata(audio: Path) -> SourceMetadata:
    if not audio.exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio}")
    if not audio.is_file():
        raise ValueError(f"Audio path is not a file: {audio}")
    try:
        info = sf.info(audio)
    except Exception as exc:
        raise RuntimeError(f"Could not read audio metadata for {audio}.") from exc
    return SourceMetadata(
        path=audio.resolve(),
        filename=audio.name,
        duration_seconds=round(float(info.duration), 6),
        sample_rate=int(info.samplerate),
        channels=int(info.channels),
        frames=int(info.frames),
        format=str(info.format),
        subtype=str(info.subtype),
        file_size=audio.stat().st_size,
    )


def build_waveform_peaks(audio: Path, *, target_points: int = 1600) -> WaveformPeaks:
    if target_points <= 0:
        raise ValueError("target_points must be positive")
    try:
        data, sample_rate = sf.read(audio, dtype="float32", always_2d=True)
    except Exception as exc:
        raise RuntimeError(f"Could not decode waveform for {audio}.") from exc
    if data.size == 0:
        raise ValueError("The audio file contains no decodable samples")
    mono = np.mean(data, axis=1)
    frames = len(mono)
    bucket = max(1, int(np.ceil(frames / target_points)))
    peaks: list[tuple[float, float]] = []
    for start in range(0, frames, bucket):
        chunk = mono[start : start + bucket]
        if chunk.size:
            peaks.append((round(float(np.min(chunk)), 6), round(float(np.max(chunk)), 6)))
    duration = frames / float(sample_rate)
    return WaveformPeaks(
        source=audio.resolve(),
        duration_seconds=round(duration, 6),
        sample_rate=int(sample_rate),
        peaks=peaks,
    )


def analyze_source(
    request: AnalysisRequest,
    *,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
    analyzer: Callable[..., AudioAnalysis] = analyze_audio,
) -> AnalysisResult:
    _emit(progress, ProgressEvent("validating", "Validating analysis request"))
    _check_cancel(cancel)
    meter = resolve_meter(request.time_signature, request.beat_grouping)
    _emit(progress, ProgressEvent("analyzing", "Analyzing source audio"))
    analysis = analyzer(
        request.audio,
        steps_per_bar=request.steps_per_bar,
        bpm_override=request.bpm,
        grid_start_override=request.grid_start,
        downbeat_override=request.downbeat_start,
        meter=meter,
    )
    _check_cancel(cancel)
    output_parent = request.output.parent if request.output.suffix else request.output
    analysis_filename = request.output.name if request.output.suffix else "analysis.json"
    run = allocate_run_context(command="analyze", source=request.audio, parent_dir=output_parent)
    analysis_path = run.path(analysis_filename)
    write_analysis(analysis, analysis_path)
    run.register("analysis", analysis_path, format="json")
    if request.features_csv:
        features_path = run.path(request.features_csv.name)
        write_feature_csv(analysis, features_path)
        run.register("features_csv", features_path, format="csv")
    if request.render_click:
        click_path, mixed_path = render_click_tracks(request.audio, analysis, run.run_dir)
        run.register("click", click_path, format="wav")
        run.register("source_with_click", mixed_path, format="wav")
    manifest_path = run.write_manifest(
        {
            "bpm": request.bpm,
            "steps_per_bar": request.steps_per_bar,
            "grid_start": request.grid_start,
            "downbeat_start": request.downbeat_start,
            "time_signature": request.time_signature,
            "beat_grouping": request.beat_grouping,
            "render_click": request.render_click,
            "features_csv": request.features_csv.name if request.features_csv else None,
            "raw_detected_bpm": analysis.raw_detected_bpm,
            "selected_bpm": analysis.bpm,
            "tempo_source": analysis.tempo_source,
        }
    )
    _emit(progress, ProgressEvent("complete", "Analysis complete"))
    return AnalysisResult(request, analysis, run.run_dir, manifest_path, [asdict(a) for a in run.artifacts])


def _source_sha256(audio: Path) -> str | None:
    try:
        return hashlib.sha256(audio.read_bytes()).hexdigest()
    except Exception:
        return None


def _resolve_generation_options(request: GenerationRequest, analysis: AudioAnalysis) -> tuple[Meter, str, tuple[Section, ...] | None, GenerationControls, list[str], int]:
    meter = resolve_meter(request.time_signature, request.beat_grouping)
    arrangement: tuple[Section, ...] | None = None
    effective_bars = request.bars or analysis.bar_count
    if request.structure:
        arrangement = ARRANGEMENT_PRESETS[request.structure]
        effective_bars = arrangement_bar_count(arrangement)
    fallback_style = DEFAULT_STYLE_PER_GENRE.get(request.genre) if request.genre else "minimal"
    genre = resolve_genre(style=request.style if request.style != "all" else fallback_style, genre=request.genre)
    if request.style != "all":
        validate_style_genre(request.style, genre)
    genre_defaults = GENRE_CONTROL_DEFAULTS.get(genre, {})
    controls = GenerationControls(
        density=request.density if request.density is not None else genre_defaults.get("density", 0.5),
        swing=request.swing if request.swing is not None else genre_defaults.get("swing", 0.0),
        humanize=request.humanize if request.humanize is not None else genre_defaults.get("humanize", 0.0),
        variation=request.variation if request.variation is not None else genre_defaults.get("variation", 0.25),
        source_restraint=request.source_restraint if request.source_restraint is not None else genre_defaults.get("source_restraint", 0.0),
        phrase_awareness=request.phrase_awareness,
        groove=request.groove,
        bars=effective_bars,
        genre=genre,
        kick_density=request.kick_density,
        snare_density=request.snare_density,
        hat_density=request.hat_density,
        open_hat_density=request.open_hat_density,
        percussion_density=request.percussion_density,
        meter=meter,
    )
    controls.validate()
    if request.style == "all":
        styles = list(HIPHOP_STYLES) if genre == "hiphop" else list(STYLE_CONFIG)
    else:
        styles = [request.style]
    return meter, genre, arrangement, controls, styles, effective_bars


def generate_patterns(
    request: GenerationRequest,
    *,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
    analyzer: Callable[..., AudioAnalysis] = analyze_audio,
) -> GenerationResult:
    if request.variants <= 0:
        raise ValueError("variants must be a positive integer")
    _emit(progress, ProgressEvent("validating", "Validating generation request"))
    meter = resolve_meter(request.time_signature, request.beat_grouping)
    run_style = request.style if request.style != "all" else request.genre or "all"
    run = allocate_run_context(command="generate", source=request.audio, parent_dir=request.output, style=run_style)
    _check_cancel(cancel)
    _emit(progress, ProgressEvent("analyzing", "Analyzing source audio"))
    analysis = analyzer(
        request.audio,
        steps_per_bar=request.steps_per_bar or meter.steps_per_bar,
        bpm_override=request.bpm,
        grid_start_override=request.grid_start,
        downbeat_override=request.downbeat_start,
        meter=meter,
    )
    analysis_path = run.run_dir / "analysis.json"
    write_analysis(analysis, analysis_path)
    run.register("analysis", analysis_path, format="json")
    meter, genre, arrangement, controls, styles, generation_bar_count = _resolve_generation_options(request, analysis)
    source_sha256 = _source_sha256(request.audio)
    preview_arrays: list[tuple[str, np.ndarray]] = []
    results: list[GeneratedPatternResult] = []
    total = len(styles) * request.variants
    index = 0
    for style in styles:
        for variant in range(request.variants):
            _check_cancel(cancel)
            index += 1
            variant_seed = request.seed + variant
            _emit(progress, ProgressEvent("generating", f"Generating {style} variant {variant}", index, total))
            pattern = generate_pattern(analysis, style, seed=variant_seed, controls=controls, arrangement=arrangement)
            pattern.metadata["source_sha256"] = source_sha256
            pattern.metadata["input_manifest"] = {
                "seed": variant_seed,
                "style": style,
                "genre": genre,
                "controls": asdict(controls),
                "generator_version": pattern.metadata.get("generator_version", "0.1.0"),
            }
            pattern_dict = pattern.to_dict()
            pattern_json = json.dumps(pattern_dict, default=str, indent=2)
            pattern.metadata["pattern_sha256"] = hashlib.sha256(pattern_json.encode()).hexdigest()
            if request.variants > 1:
                style_dir = ensure_output_dir(run.run_dir / style / f"variant_{variant}")
            else:
                style_dir = ensure_output_dir(run.run_dir / style)
            artifacts: dict[str, Path] = {}
            json_path = style_dir / "pattern.json"
            write_pattern(pattern, json_path)
            artifacts["json"] = json_path
            run.register("pattern_json", json_path, style=style, variant=variant)
            midi_path = style_dir / "pattern.mid"
            write_midi(pattern, midi_path, velocity_curve=request.midi_velocity_curve)
            artifacts["midi"] = midi_path
            run.register("pattern_midi", midi_path, style=style, variant=variant)
            strudel_path = style_dir / "pattern.strudel.js"
            write_strudel(pattern, strudel_path)
            artifacts["strudel"] = strudel_path
            run.register("pattern_strudel", strudel_path, style=style, variant=variant)
            label = f"{style} variant {variant}" if request.variants > 1 else style
            if request.preview or request.preview_comparison:
                _emit(progress, ProgressEvent("rendering_preview", f"Rendering preview for {label}", index, total))
                preview_pattern = pattern
                if request.preview_bars is not None and request.preview_bars < pattern.bars:
                    preview_controls = replace(controls, bars=request.preview_bars)
                    preview_pattern = generate_pattern(analysis, style, seed=variant_seed, controls=preview_controls)
                preview_audio = render_preview(preview_pattern, seed=variant_seed)
                if request.preview:
                    preview_path = write_preview(preview_pattern, style_dir / "pattern-preview.wav", seed=variant_seed)
                    artifacts["preview"] = preview_path
                    run.register("preview", preview_path, style=style, variant=variant, format="wav")
                if request.preview_comparison:
                    preview_arrays.append((label, preview_audio))
            results.append(GeneratedPatternResult(label, style, variant, variant_seed, pattern, style_dir, artifacts))
    if request.preview_comparison and preview_arrays:
        gap = int(0.5 * 44100)
        segments: list[np.ndarray] = []
        for _name, audio in preview_arrays:
            segments.append(audio)
            segments.append(np.zeros(gap, dtype=np.float32))
        comparison_path = run.run_dir / "comparison.wav"
        sf.write(comparison_path, np.concatenate(segments), 44100)
        run.register("preview_comparison", comparison_path, format="wav")
    manifest_path = run.write_manifest(
        {
            "bpm": request.bpm,
            "selected_bpm": analysis.bpm,
            "raw_detected_bpm": analysis.raw_detected_bpm,
            "tempo_source": analysis.tempo_source,
            "time_signature": request.time_signature,
            "beat_grouping": request.beat_grouping,
            "bars": request.bars,
            "genre": genre,
            "style": request.style,
            "seed": request.seed,
            "variants": request.variants,
            "structure": request.structure,
            "generation_bar_count": generation_bar_count,
        }
    )
    _emit(progress, ProgressEvent("complete", "Generation complete"))
    return GenerationResult(
        request=request,
        analysis=analysis,
        controls=controls,
        run_dir=run.run_dir,
        manifest_path=manifest_path,
        results=results,
        artifacts=[asdict(a) for a in run.artifacts],
        warnings=list(analysis.warnings),
    )


def list_run_manifests(parent: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    if not parent.exists():
        return []
    manifests = sorted(parent.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    runs: list[dict[str, Any]] = []
    for manifest in manifests[:limit]:
        try:
            data = load_run_manifest(manifest.parent)
        except Exception as exc:
            data = {"run_directory": str(manifest.parent), "error": str(exc), "artifacts": []}
        runs.append(data)
    return runs


def pattern_summary(pattern: DrumPattern) -> dict[str, Any]:
    return {
        "name": pattern.name,
        "bpm": pattern.bpm,
        "bars": pattern.bars,
        "steps_per_bar": pattern.steps_per_bar,
        "seed": pattern.seed,
        "hit_count": sum(len(hits) for hits in pattern.hits.values()),
        "hits_by_instrument": {instrument: len(hits) for instrument, hits in pattern.hits.items()},
    }


def available_styles() -> Iterable[str]:
    return ALL_STYLES
