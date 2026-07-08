from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    HIPHOP_STYLES,
    Section,
    arrangement_bar_count,
    ensure_output_dir,
    resolve_genre,
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
    analyze_parser.add_argument("--steps-per-bar", type=int, default=16)
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
    generate_parser.add_argument("--bpm", type=_positive_bpm, help="Override tempo estimation")
    generate_parser.add_argument("--steps-per-bar", type=int, default=16)
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
        "--preview",
        action="store_true",
        help="Render a WAV audio preview of each generated pattern",
    )
    generate_parser.add_argument(
        "--midi-velocity-curve",
        choices=["linear", "exponential", "compressed", "hard"],
        default="linear",
        help="Velocity curve shape for MIDI note velocities",
    )

    return parser


def _run_analyze(args: argparse.Namespace) -> int:
    analysis = analyze_audio(
        args.audio,
        steps_per_bar=args.steps_per_bar,
        bpm_override=args.bpm,
        grid_start_override=args.grid_start,
        downbeat_override=args.downbeat_start,
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
    analysis = analyze_audio(
        args.audio,
        steps_per_bar=args.steps_per_bar,
        bpm_override=args.bpm,
        grid_start_override=args.grid_start,
        downbeat_override=args.downbeat_start,
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
        bars=effective_bars,
        genre=genre,
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

    for style in styles:
        pattern = generate_pattern(
            analysis, style, seed=args.seed, controls=controls, arrangement=arrangement
        )
        style_dir = ensure_output_dir(output_dir / style)
        write_pattern(pattern, style_dir / "pattern.json")
        write_midi(pattern, style_dir / "pattern.mid", velocity_curve=args.midi_velocity_curve)
        write_strudel(pattern, style_dir / "pattern.strudel.js")
        hit_count = sum(len(value) for value in pattern.hits.values())
        print(f"Generated {style}: {hit_count} hits → {style_dir}")
        if args.preview:
            preview_path = write_preview(pattern, style_dir / "pattern-preview.wav", seed=args.seed)
            print(f"  Preview: {preview_path}")

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
