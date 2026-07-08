from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analysis import analyze_audio
from .exporters.json_export import write_analysis, write_pattern
from .exporters.midi import write_midi
from .exporters.strudel import write_strudel
from .generator import STYLE_CONFIG, GenerationControls, generate_pattern
from .models import AudioAnalysis, ensure_output_dir


def _positive_bpm(value: str) -> float:
    bpm = float(value)
    if bpm <= 0:
        raise argparse.ArgumentTypeError("BPM must be greater than zero")
    return bpm


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
        choices=[*STYLE_CONFIG, "all"],
        default="all",
    )
    generate_parser.add_argument("--seed", type=int, default=42)
    generate_parser.add_argument("--bpm", type=_positive_bpm, help="Override tempo estimation")
    generate_parser.add_argument("--steps-per-bar", type=int, default=16)
    generate_parser.add_argument("--bars", type=_positive_int("bars"), help="Generated bar count")
    generate_parser.add_argument(
        "--density",
        type=_bounded_float("density", 0.0, 1.0),
        default=0.5,
        help="Overall hit density from 0.0 to 1.0",
    )
    generate_parser.add_argument(
        "--swing",
        type=_bounded_float("swing", 0.0, 0.5),
        default=0.0,
        help="Additional off-grid swing delay in steps from 0.0 to 0.5",
    )
    generate_parser.add_argument(
        "--humanize",
        type=_bounded_float("humanize", 0.0, 1.0),
        default=0.0,
        help="Random timing and velocity looseness from 0.0 to 1.0",
    )
    generate_parser.add_argument(
        "--variation",
        type=_bounded_float("variation", 0.0, 1.0),
        default=0.25,
        help="Bar-to-bar/random variation from 0.0 to 1.0",
    )

    return parser


def _run_analyze(args: argparse.Namespace) -> int:
    analysis = analyze_audio(
        args.audio,
        steps_per_bar=args.steps_per_bar,
        bpm_override=args.bpm,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_analysis(analysis, args.output)
    print(f"Source: {args.audio}")
    print(f"BPM: {analysis.bpm:.2f}")
    print(f"Duration: {analysis.duration_seconds:.2f}s")
    _print_loop_diagnostics(analysis)
    print(f"Detected output grid: {analysis.bar_count} bars")
    print(f"Wrote: {args.output}")
    for warning in analysis.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _run_generate(args: argparse.Namespace) -> int:
    output_dir = ensure_output_dir(args.output)
    analysis = analyze_audio(
        args.audio,
        steps_per_bar=args.steps_per_bar,
        bpm_override=args.bpm,
    )
    analysis_path = output_dir / "analysis.json"
    write_analysis(analysis, analysis_path)

    controls = GenerationControls(
        density=args.density,
        swing=args.swing,
        humanize=args.humanize,
        variation=args.variation,
        bars=args.bars,
    )
    controls.validate()
    styles = list(STYLE_CONFIG) if args.style == "all" else [args.style]
    generation_bar_count = controls.bars or analysis.bar_count
    print(f"Source: {args.audio}")
    print(f"Detected BPM: {analysis.bpm:.2f}")
    print(f"Duration: {analysis.duration_seconds:.2f}s")
    print(f"Detected source fit: {_format_grid_fit(analysis)}")
    print(f"Grid: {analysis.bar_count} analyzed bars × {analysis.steps_per_bar} steps")
    if controls.bars is None:
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
            print(
                f"Ignoring {remainder:.2f}s of source audio beyond the requested grid boundary."
            )
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
        pattern = generate_pattern(analysis, style, seed=args.seed, controls=controls)
        style_dir = ensure_output_dir(output_dir / style)
        write_pattern(pattern, style_dir / "pattern.json")
        write_midi(pattern, style_dir / "pattern.mid")
        write_strudel(pattern, style_dir / "pattern.strudel.js")
        hit_count = sum(len(value) for value in pattern.hits.values())
        print(f"Generated {style}: {hit_count} hits → {style_dir}")

    if controls.bars is not None:
        print(f"Generated exactly {controls.bars} bars.")

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
