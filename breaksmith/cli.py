from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .app import AnalysisRequest, GenerationRequest, analyze_source, generate_patterns, list_run_manifests
from .analysis import analyze_audio
from .models import (
    ALL_STYLES,
    ARRANGEMENT_PRESETS,
    AudioAnalysis,
    DEFAULT_STYLE_PER_GENRE,
    GENRES,
    GROOVE_PRESETS,
    METER_PRESETS,
    Section,
    arrangement_bar_count,
    parse_time_signature,
    resolve_genre,
    validate_beat_grouping,
    validate_style_genre,
)
from .presets import load_preset


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
    if analysis.raw_detected_bpm:
        candidates = ", ".join(f"{value:.2f}" for value in analysis.candidate_bpm_values)
        print(f"Raw detected BPM: {analysis.raw_detected_bpm:.2f}")
        print(f"Candidate BPMs: {candidates}")
        print(
            f"Selected BPM: {analysis.bpm:.2f} "
            f"(score={analysis.tempo_selection_score:.2f}; {analysis.tempo_selection_reason})"
        )
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
    analyze_parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output parent directory; each run gets a unique child directory",
    )
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
        help="Output parent directory; each run gets a unique child directory",
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
        "--preset",
        type=Path,
        help="Load generation settings from a Breaksmith preset JSON file; explicit audio/output still apply",
    )
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

    runs_parser = subparsers.add_parser("runs", help="List previous Breaksmith runs")
    runs_parser.add_argument("--output", type=Path, default=Path("output"))
    runs_parser.add_argument("--limit", type=_positive_int("limit"), default=20)
    runs_parser.add_argument("--json", action="store_true", help="Write run history as JSON")

    return parser


def _run_analyze(args: argparse.Namespace) -> int:
    result = analyze_source(
        AnalysisRequest(
            audio=args.audio,
            output=args.output,
            bpm=args.bpm,
            steps_per_bar=args.steps_per_bar,
            grid_start=args.grid_start,
            downbeat_start=args.downbeat_start,
            time_signature=args.time_signature,
            beat_grouping=args.beat_grouping,
            render_click=args.render_click,
            features_csv=args.features_csv,
        ),
        analyzer=analyze_audio,
    )
    analysis = result.analysis
    analysis_artifact = next(
        (artifact for artifact in result.artifacts if artifact["artifact_type"] == "analysis"),
        None,
    )
    analysis_path = result.run_dir / (analysis_artifact["path"] if analysis_artifact else "analysis.json")
    print(f"Source: {args.audio}")
    print(f"BPM: {analysis.bpm:.2f}")
    print(f"Duration: {analysis.duration_seconds:.2f}s")
    _print_loop_diagnostics(analysis)
    _print_feature_summary(analysis)
    print(f"Detected output grid: {analysis.bar_count} bars")
    print(f"Wrote: {analysis_path}")
    for artifact in result.artifacts:
        artifact_path = result.run_dir / artifact["path"]
        if artifact["artifact_type"] == "features_csv":
            print(f"Wrote feature CSV: {artifact_path}")
        elif artifact["artifact_type"] == "click":
            print(f"Wrote click: {artifact_path}")
        elif artifact["artifact_type"] == "source_with_click":
            print(f"Wrote source with click: {artifact_path}")
    print(f"Wrote manifest: {result.manifest_path}")
    print(f"Output written to: {result.run_dir}")
    for warning in analysis.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _run_generate(args: argparse.Namespace) -> int:
    if getattr(args, "preset", None):
        preset = load_preset(args.preset)
        request = preset.request
        request = GenerationRequest(**{**asdict(request), "audio": args.audio, "output": args.output})
    else:
        request = GenerationRequest(
            audio=args.audio,
            output=args.output,
            style=args.style,
            genre=args.genre,
            seed=args.seed,
            variants=args.variants,
            bpm=args.bpm,
            steps_per_bar=args.steps_per_bar,
            grid_start=args.grid_start,
            downbeat_start=args.downbeat_start,
            bars=args.bars,
            structure=args.structure,
            density=args.density,
            swing=args.swing,
            humanize=args.humanize,
            variation=args.variation,
            phrase_awareness=args.phrase_awareness,
            groove=args.groove,
            preview=args.preview,
            preview_bars=args.preview_bars,
            preview_comparison=args.preview_comparison,
            source_restraint=args.source_restraint,
            kick_density=args.kick_density,
            snare_density=args.snare_density,
            hat_density=args.hat_density,
            open_hat_density=args.open_hat_density,
            percussion_density=args.percussion_density,
            midi_velocity_curve=args.midi_velocity_curve,
            time_signature=args.time_signature,
            beat_grouping=args.beat_grouping,
        )
    args = argparse.Namespace(**{**vars(args), **asdict(request)})
    meter = parse_time_signature(args.time_signature)
    if args.beat_grouping is not None:
        meter = validate_beat_grouping(meter, args.beat_grouping)
    result = generate_patterns(
        request,
        analyzer=analyze_audio,
    )
    analysis = result.analysis

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

    generation_bar_count = effective_bars
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
    print(f"Grid: {analysis.bar_count} analyzed bars x {analysis.steps_per_bar} steps")
    if arrangement is not None:
        sections_desc = " -> ".join(f"{s.name}({s.bar_count}b)" for s in arrangement)
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
        requested_duration = result.controls.bars * analysis.bar_duration_seconds
        remainder = analysis.effective_duration_seconds - requested_duration
        print(f"Requested grid: {result.controls.bars} bars")
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
        f"bars={generation_bar_count}, density={result.controls.density}, "
        f"swing={result.controls.swing}, humanize={result.controls.humanize}, variation={result.controls.variation}"
    )
    for generated in result.results:
        hit_count = sum(len(value) for value in generated.pattern.hits.values())
        print(f"Generated {generated.label}: {hit_count} hits -> {generated.directory}")
        if "preview" in generated.artifacts:
            print(f"  Preview: {generated.artifacts['preview']}")
    for artifact in result.artifacts:
        if artifact["artifact_type"] == "preview_comparison":
            print(f"Comparison preview: {result.run_dir / artifact['path']}")

    if arrangement is not None:
        print(f"Generated {generation_bar_count} bars ({args.structure} arrangement).")
    elif bars_explicit:
        print(f"Generated exactly {generation_bar_count} bars.")

    print(f"Wrote manifest: {result.manifest_path}")
    print(f"Output written to: {result.run_dir}")

    for warning in analysis.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _run_runs(args: argparse.Namespace) -> int:
    runs = list_run_manifests(args.output, limit=args.limit)
    if args.json:
        print(json.dumps(runs, indent=2, default=str))
        return 0
    if not runs:
        print(f"No runs found under: {args.output}")
        return 0
    for run in runs:
        options = run.get("options", {}) if isinstance(run.get("options"), dict) else {}
        print(
            f"{run.get('created_at', 'unknown')} | {run.get('command', 'run')} | "
            f"{run.get('source_filename', 'unknown source')} | "
            f"bpm={options.get('selected_bpm', 'n/a')} | {run.get('run_directory')}"
        )
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "analyze":
            result = _run_analyze(args)
        elif args.command == "generate":
            result = _run_generate(args)
        else:
            result = _run_runs(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Interrupted.\n")
    raise SystemExit(result)


if __name__ == "__main__":
    main()
