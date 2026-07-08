from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf

from .analysis import analyze_audio
from .click import render_click_tracks
from .exporters.json_export import write_analysis, write_feature_csv, write_pattern
from .exporters.midi import write_midi
from .exporters.strudel import write_strudel
from .generator import STYLE_CONFIG, GenerationControls, generate_pattern
from .models import (
    ALL_STYLES,
    ARRANGEMENT_PRESETS,
    AudioAnalysis,
    DEFAULT_STYLE_PER_GENRE,
    GENRE_CONTROL_DEFAULTS,
    GENRES,
    GROOVE_PRESETS,
    HIPHOP_STYLES,
    METER_PRESETS,
    Section,
    arrangement_bar_count,
    ensure_output_dir,
    parse_time_signature,
    resolve_genre,
    validate_beat_grouping,
    validate_style_genre,
)
from .synth import write_preview


def _positive_bpm(value: str) -> float:
    bpm = float(value)
    if bpm <= 0:
        raise argparse.ArgumentTypeError("BPM must be greater than zero")
    return bpm


def _non_negative_float(name: str):
    def parse(value: str) -> float:
        parsed = float(value)
        if parsed < 0:
            raise argparse.ArgumentTypeError(f"{name} must be greater than or equal to zero")
        return parsed

    return parse


def _bounded_float(name: str, minimum: float, maximum: float):
    def parse(value: str) -> float:
        parsed = float(value)
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
        return parsed

    return parse


def _positive_int(name: str):
    def parse(value: str) -> int:
        parsed = int(value)
        if parsed <= 0:
            raise argparse.ArgumentTypeError(f"{name} must be a positive integer")
        return parsed

    return parse


def _format_beats(value: float) -> str:
    label = "beat" if abs(value - 1.0) < 0.005 else "beats"
    return f"{value:.2f} {label}"


def _format_grid_fit(analysis: AudioAnalysis) -> str:
    if analysis.duration_fit == "clean":
        return f"clean {analysis.complete_bar_count}-bar loop"
    return f"{analysis.complete_bar_count} complete bars + {_format_beats(analysis.duration_remainder_beats)}"


def _print_loop_diagnostics(analysis: AudioAnalysis) -> None:
    print(f"Grid fit: {_format_grid_fit(analysis)}")
    print(
        "Timing confidence: "
        f"tempo={analysis.tempo_confidence:.2f}, beat={analysis.beat_confidence:.2f} "
        f"({analysis.detected_beat_count}/{analysis.expected_beat_count} beats)"
    )
    print(
        f"Grid start: {analysis.grid_start_seconds:.3f}s "
        f"({analysis.grid_start_source}); downbeat: {analysis.downbeat_seconds:.3f}s"
    )
    for warning in analysis.loop_warnings:
        prefix = "Notice" if analysis.duration_fit == "small_tail" else "Warning"
        print(f"{prefix}: {warning}")
    if analysis.duration_fit in {"small_tail", "extra_beat"}:
        print(
            "Suggestion: trim the source or pass "
            f"--bars {analysis.suggested_bar_count} when generating."
        )
    elif analysis.duration_fit == "partial_bar":
        print("Suggestion: confirm the intended length or pass --bars explicitly.")


def _print_feature_summary(analysis: AudioAnalysis) -> None:
    if not analysis.rms_activity:
        return
    density = sum(analysis.local_density) / max(1, len(analysis.local_density))
    brightness = sum(analysis.brightness_activity) / max(1, len(analysis.brightness_activity))
    silence = sum(analysis.silence_activity) / max(1, len(analysis.silence_activity))
    sustain = sum(analysis.sustain_activity) / max(1, len(analysis.sustain_activity))
    print(
        "Source features: "
        f"density={density:.2f}, brightness={brightness:.2f}, "
        f"sustain={sustain:.2f}, silence={silence:.2f}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="breaksmith",
        description="Analyze audio and generate editable breakbeat and drum-and-bass patterns.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze an audio file")
    analyze_parser.add_argument("audio", type=Path)
    analyze_parser.add_argument("--output", type=Path, default=Path("analysis.json"))
    analyze_parser.add_argument("--bpm", type=_positive_bpm, help="Override tempo estimation")
    analyze_parser.add_argument("--steps-per-bar", type=int, default=None)
    analyze_parser.add_argument(
        "--grid-start",
        type=_non_negative_float("grid-start"),
        help="Manual grid start in seconds",
    )
    analyze_parser.add_argument(
        "--downbeat-start",
        type=_non_negative_float("downbeat-start"),
        help="Manual first downbeat in seconds; overrides --grid-start when both are provided",
    )
    analyze_parser.add_argument(
        "--render-click",
        action="store_true",
        help="Render analysis-click.wav and source-with-click.wav next to the analysis output",
    )
    analyze_parser.add_argument(
        "--features-csv",
        type=Path,
        help="Write step-level source activity maps as CSV",
    )
    analyze_parser.add_argument(
        "--time-signature",
        type=str,
        default="4/4",
        choices=sorted(METER_PRESETS),
        help="Time signature / meter (default: 4/4)",
    )
    analyze_parser.add_argument(
        "--beat-grouping",
        type=str,
        default=None,
        help="Beat grouping override (e.g. '3+3' for 6/8, '2+2+3' for 7/8). Default follows meter.",
    )

    generate_parser = subparsers.add_parser(
        "generate",
        help="Analyze audio and generate DnB patterns",
    )
    generate_parser.add_argument("audio", type=Path)
    generate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory",
    )
    generate_parser.add_argument(
        "--style",
        choices=[*ALL_STYLES, "all"],
        default="all",
    )
    generate_parser.add_argument(
        "--genre",
        choices=[*GENRES],
        help="Music genre (inferred from style if omitted)",
    )
    generate_parser.add_argument("--seed", type=int, default=42)
    generate_parser.add_argument(
        "--variants",
        type=_positive_int("variants"),
        default=1,
        help="Number of variant patterns to generate (each gets seed + variant index)",
    )
    generate_parser.add_argument("--bpm", type=_positive_bpm, help="Override tempo estimation")
    generate_parser.add_argument("--steps-per-bar", type=int, default=None)
    generate_parser.add_argument(
        "--grid-start",
        type=_non_negative_float("grid-start"),
        help="Manual grid start in seconds",
    )
    generate_parser.add_argument(
        "--downbeat-start",
        type=_non_negative_float("downbeat-start"),
        help="Manual first downbeat in seconds; overrides --grid-start when both are provided",
    )
    generate_parser.add_argument("--bars", type=_positive_int("bars"), help="Generated bar count")
    generate_parser.add_argument(
        "--structure",
        choices=[*ARRANGEMENT_PRESETS],
        help="Phrase arrangement preset (overrides --bars with the preset's total bar count)",
    )
    generate_parser.add_argument(
        "--density",
        type=_bounded_float("density", 0.0, 1.0),
        default=None,
        help="Overall hit density from 0.0 to 1.0 (genre-dependent default)",
    )
    generate_parser.add_argument(
        "--swing",
        type=_bounded_float("swing", 0.0, 0.5),
        default=None,
        help="Additional off-grid swing delay in steps from 0.0 to 0.5 (genre-dependent default)",
    )
    generate_parser.add_argument(
        "--humanize",
        type=_bounded_float("humanize", 0.0, 1.0),
        default=None,
        help="Random timing and velocity looseness from 0.0 to 1.0 (genre-dependent default)",
    )
    generate_parser.add_argument(
        "--variation",
        type=_bounded_float("variation", 0.0, 1.0),
        default=None,
        help="Bar-to-bar/random variation from 0.0 to 1.0 (genre-dependent default)",
    )
    generate_parser.add_argument(
        "--phrase-awareness",
        type=_bounded_float("phrase-awareness", 0.0, 1.0),
        default=0.3,
        help="How strongly phrase position modulates density from 0.0 (off) to 1.0 (full curve)",
    )
    generate_parser.add_argument(
        "--groove",
        choices=[*GROOVE_PRESETS],
        default="straight",
        help="Structured timing groove template for consistent per-step feel",
    )
    generate_parser.add_argument(
        "--preview",
        action="store_true",
        help="Render a WAV audio preview of each generated pattern",
    )
    generate_parser.add_argument(
        "--preview-bars",
        type=_positive_int("preview-bars"),
        default=None,
        help="Number of bars for audio preview (default: full pattern bar count; shorter = faster)",
    )
    generate_parser.add_argument(
        "--preview-comparison",
        action="store_true",
        help="Generate a single WAV with all style previews concatenated for A/B comparison",
    )
    generate_parser.add_argument(
        "--source-restraint",
        type=_bounded_float("source-restraint", 0.0, 1.0),
        default=None,
        help="Modulate density by source bar energy from 0.0 to 1.0 (0=ignore source, 1=fully follow source)",
    )
    generate_parser.add_argument(
        "--kick-density",
        type=_bounded_float("kick-density", 0.0, 1.0),
        default=None,
        help="Per-layer density multiplier for kick from 0.0 to 1.0",
    )
    generate_parser.add_argument(
        "--snare-density",
        type=_bounded_float("snare-density", 0.0, 1.0),
        default=None,
        help="Per-layer density multiplier for snare from 0.0 to 1.0",
    )
    generate_parser.add_argument(
        "--hat-density",
        type=_bounded_float("hat-density", 0.0, 1.0),
        default=None,
        help="Per-layer density multiplier for closed hat from 0.0 to 1.0",
    )
    generate_parser.add_argument(
        "--open-hat-density",
        type=_bounded_float("open-hat-density", 0.0, 1.0),
        default=None,
        help="Per-layer density multiplier for open hat from 0.0 to 1.0",
    )
    generate_parser.add_argument(
        "--percussion-density",
        type=_bounded_float("percussion-density", 0.0, 1.0),
        default=None,
        help="Per-layer density multiplier for percussion from 0.0 to 1.0",
    )
    generate_parser.add_argument(
        "--midi-velocity-curve",
        choices=["linear", "exponential", "compressed", "hard"],
        default="linear",
        help="Velocity curve shape for MIDI note velocities",
    )
    generate_parser.add_argument(
        "--time-signature",
        type=str,
        default="4/4",
        choices=sorted(METER_PRESETS),
        help="Time signature / meter (default: 4/4)",
    )
    generate_parser.add_argument(
        "--beat-grouping",
        type=str,
        default=None,
        help="Beat grouping override (e.g. '3+3' for 6/8, '2+2+3' for 7/8). Default follows meter.",
    )

    return parser


def _run_analyze(args: argparse.Namespace) -> int:
    meter = parse_time_signature(args.time_signature)
    if args.beat_grouping is not None:
        meter = validate_beat_grouping(meter, args.beat_grouping)
    analysis = analyze_audio(
        args.audio,
        steps_per_bar=args.steps_per_bar,
        bpm_override=args.bpm,
        grid_start_override=args.grid_start,
        downbeat_override=args.downbeat_start,
        meter=meter,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_analysis(analysis, args.output)
    print(f"Source: {args.audio}")
    print(f"BPM: {analysis.bpm:.2f}")
    print(f"Duration: {analysis.duration_seconds:.2f}s")
    _print_loop_diagnostics(analysis)
    _print_feature_summary(analysis)
    print(f"Detected output grid: {analysis.bar_count} bars")
    print(f"Wrote: {args.output}")
    if args.features_csv:
        args.features_csv.parent.mkdir(parents=True, exist_ok=True)
        write_feature_csv(analysis, args.features_csv)
        print(f"Wrote feature CSV: {args.features_csv}")
    if args.render_click:
        click_path, mixed_path = render_click_tracks(args.audio, analysis, args.output.parent)
        print(f"Wrote click: {click_path}")
        print(f"Wrote source with click: {mixed_path}")
    for warning in analysis.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _run_generate(args: argparse.Namespace) -> int:
    output_dir = ensure_output_dir(args.output)
    meter = parse_time_signature(args.time_signature)
    if args.beat_grouping is not None:
        meter = validate_beat_grouping(meter, args.beat_grouping)
    analysis = analyze_audio(
        args.audio,
        steps_per_bar=args.steps_per_bar or meter.steps_per_bar,
        bpm_override=args.bpm,
        grid_start_override=args.grid_start,
        downbeat_override=args.downbeat_start,
        meter=meter,
    )
    analysis_path = output_dir / "analysis.json"
    write_analysis(analysis, analysis_path)

    arrangement: tuple[Section, ...] | None = None
    bars_explicit = args.bars is not None
    if args.structure:
        if args.bars is not None:
            print("Warning: --structure overrides --bars; ignoring --bars.", file=sys.stderr)
        arrangement = ARRANGEMENT_PRESETS[args.structure]
        effective_bars = arrangement_bar_count(arrangement)
        bars_explicit = True
    else:
        effective_bars = args.bars or analysis.bar_count

    fallback_style = DEFAULT_STYLE_PER_GENRE.get(args.genre) if args.genre else "minimal"
    genre = resolve_genre(style=args.style if args.style != "all" else fallback_style, genre=args.genre)
    if args.style != "all":
        validate_style_genre(args.style, genre)

    genre_defaults = GENRE_CONTROL_DEFAULTS.get(genre, {})
    controls = GenerationControls(
        density=args.density if args.density is not None else genre_defaults.get("density", 0.5),
        swing=args.swing if args.swing is not None else genre_defaults.get("swing", 0.0),
        humanize=args.humanize if args.humanize is not None else genre_defaults.get("humanize", 0.0),
        variation=args.variation if args.variation is not None else genre_defaults.get("variation", 0.25),
        source_restraint=args.source_restraint if args.source_restraint is not None else genre_defaults.get("source_restraint", 0.0),
        phrase_awareness=args.phrase_awareness,
        groove=args.groove,
        bars=effective_bars,
        genre=genre,
        kick_density=args.kick_density,
        snare_density=args.snare_density,
        hat_density=args.hat_density,
        open_hat_density=args.open_hat_density,
        percussion_density=args.percussion_density,
        meter=meter,
    )
    controls.validate()
    generation_bar_count = effective_bars
    if args.style == "all":
        if genre == "hiphop":
            styles = list(HIPHOP_STYLES)
        else:
            styles = list(STYLE_CONFIG)
    else:
        styles = [args.style]
    print(f"Source: {args.audio}")
    print(f"Detected BPM: {analysis.bpm:.2f}")
    print(f"Duration: {analysis.duration_seconds:.2f}s")
    print(f"Detected source fit: {_format_grid_fit(analysis)}")
    print(
        "Timing confidence: "
        f"tempo={analysis.tempo_confidence:.2f}, beat={analysis.beat_confidence:.2f} "
        f"({analysis.detected_beat_count}/{analysis.expected_beat_count} beats)"
    )
    print(
        f"Grid start: {analysis.grid_start_seconds:.3f}s "
        f"({analysis.grid_start_source}); downbeat: {analysis.downbeat_seconds:.3f}s"
    )
    print(f"Grid: {analysis.bar_count} analyzed bars × {analysis.steps_per_bar} steps")
    if arrangement is not None:
        sections_desc = " → ".join(f"{s.name}({s.bar_count}b)" for s in arrangement)
        print(f"Arrangement: {sections_desc} ({generation_bar_count} total bars)")
    elif not bars_explicit:
        print(f"Generating {generation_bar_count} bars because --bars was not specified.")
        if analysis.duration_fit in {"small_tail", "extra_beat"}:
            print(
                "Suggestion: pass "
                f"--bars {analysis.suggested_bar_count} to ignore the trailing partial bar."
            )
        elif analysis.duration_fit == "partial_bar":
            print("Suggestion: pass --bars explicitly if the source has a known intended length.")
    else:
        requested_duration = controls.bars * analysis.bar_duration_seconds
        remainder = analysis.effective_duration_seconds - requested_duration
        print(f"Requested grid: {controls.bars} bars")
        if remainder > analysis.step_duration_seconds * 0.25:
            print(f"Ignoring {remainder:.2f}s of source audio beyond the requested grid boundary.")
        elif remainder < -analysis.step_duration_seconds * 0.25:
            print(
                f"Requested grid extends {abs(remainder):.2f}s beyond the analyzed source audio; "
                "source activity will repeat cyclically."
            )
        else:
            print("Requested grid aligns with the analyzed source duration.")
    print(
        "Controls: "
        f"bars={generation_bar_count}, density={controls.density}, "
        f"swing={controls.swing}, humanize={controls.humanize}, variation={controls.variation}"
    )

    try:
        source_bytes = Path(args.audio).read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    except Exception:
        source_sha256 = None

    preview_arrays: list[tuple[str, np.ndarray]] = []

    for style in styles:
        for variant in range(args.variants):
            variant_seed = args.seed + variant
            pattern = generate_pattern(
                analysis, style, seed=variant_seed, controls=controls, arrangement=arrangement
            )
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
            pattern_sha256 = hashlib.sha256(pattern_json.encode()).hexdigest()
            pattern.metadata["pattern_sha256"] = pattern_sha256
            if args.variants > 1:
                style_dir = ensure_output_dir(output_dir / style / f"variant_{variant}")
            else:
                style_dir = ensure_output_dir(output_dir / style)
            write_pattern(pattern, style_dir / "pattern.json")
            write_midi(pattern, style_dir / "pattern.mid", velocity_curve=args.midi_velocity_curve)
            write_strudel(pattern, style_dir / "pattern.strudel.js")
            hit_count = sum(len(value) for value in pattern.hits.values())
            label = f"{style} variant {variant}" if args.variants > 1 else style
            print(f"Generated {label}: {hit_count} hits → {style_dir}")
            if args.preview or args.preview_comparison:
                if args.preview_bars is not None and args.preview_bars < pattern.bars:
                    preview_controls = GenerationControls(
                        density=controls.density,
                        swing=controls.swing,
                        humanize=controls.humanize,
                        variation=controls.variation,
                        source_restraint=controls.source_restraint,
                        phrase_awareness=controls.phrase_awareness,
                        groove=controls.groove,
                        bars=args.preview_bars,
                        genre=controls.genre,
                        kick_density=controls.kick_density,
                        snare_density=controls.snare_density,
                        hat_density=controls.hat_density,
                        open_hat_density=controls.open_hat_density,
                        percussion_density=controls.percussion_density,
                    )
                    preview_pattern = generate_pattern(
                        analysis, style, seed=variant_seed, controls=preview_controls, arrangement=None
                    )
                else:
                    preview_pattern = pattern
                from .synth import render_preview
                preview_audio = render_preview(preview_pattern, seed=variant_seed)
                if args.preview:
                    preview_path = write_preview(preview_pattern, style_dir / "pattern-preview.wav", seed=variant_seed)
                    print(f"  Preview: {preview_path}")
                if args.preview_comparison:
                    preview_arrays.append((f"{label}", preview_audio))

    if args.preview_comparison and preview_arrays:
        gap = int(0.5 * 44100)
        segments: list[np.ndarray] = []
        for _name, audio in preview_arrays:
            segments.append(audio)
            segments.append(np.zeros(gap, dtype=np.float32))
        if segments:
            combined = np.concatenate(segments)
            comparison_path = output_dir / "comparison.wav"
            sf.write(comparison_path, combined, 44100)
            print(f"Comparison preview ({len(preview_arrays)} styles): {comparison_path}")

    if arrangement is not None:
        print(f"Generated {generation_bar_count} bars ({args.structure} arrangement).")
    elif bars_explicit:
        print(f"Generated exactly {generation_bar_count} bars.")

    for warning in analysis.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "analyze":
            result = _run_analyze(args)
        else:
            result = _run_generate(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Interrupted.\n")
    raise SystemExit(result)


if __name__ == "__main__":
    main()
