from __future__ import annotations

import argparse
import json
import re
from types import SimpleNamespace
from pathlib import Path

import pytest
from mido import MidiFile

import breaksmith
import breaksmith.cli as cli
from breaksmith.analysis import calculate_loop_fit
from breaksmith.cli import build_parser
from breaksmith.exporters.json_export import write_pattern
from breaksmith.exporters.midi import write_midi
from breaksmith.exporters.strudel import write_strudel
from breaksmith.generator import STYLE_PRESETS, GenerationControls, generate_pattern
from breaksmith.models import AudioAnalysis


def fake_analysis() -> AudioAnalysis:
    steps = 64
    return AudioAnalysis(
        source="/tmp/fake.wav",
        duration_seconds=8.0,
        sample_rate=44100,
        bpm=172.0,
        beat_times=[index * 0.3488 for index in range(16)],
        bar_count=4,
        steps_per_bar=16,
        step_times=[index * 0.0872 for index in range(steps)],
        onset_activity=[0.2 + (0.6 if index % 5 == 0 else 0.0) for index in range(steps)],
        low_activity=[0.15 + (0.75 if index in {0, 6, 16, 26, 32, 42, 48, 58} else 0.0) for index in range(steps)],
        high_activity=[0.35 + (0.35 if index % 2 == 0 else 0.0) for index in range(steps)],
        bar_energy=[0.35, 0.55, 0.70, 0.45],
        grid_start_seconds=0.0,
        effective_duration_seconds=8.0,
        beat_duration_seconds=0.348837,
        bar_duration_seconds=1.395349,
        step_duration_seconds=0.087209,
        complete_bar_count=4,
        suggested_bar_count=4,
        last_full_bar_duration_seconds=5.581395,
        duration_remainder_seconds=0.0,
        duration_remainder_beats=0.0,
        duration_remainder_steps=0.0,
        duration_fit="clean",
        loop_warnings=[],
    )


def analysis_with_loop_duration(duration_seconds: float) -> AudioAnalysis:
    analysis = fake_analysis()
    fit = calculate_loop_fit(
        duration_seconds=duration_seconds,
        bpm=172.0,
        steps_per_bar=16,
        grid_start_seconds=0.0,
    )
    analysis.duration_seconds = duration_seconds
    analysis.bar_count = max(1, int(-(-duration_seconds // float(fit["bar_duration_seconds"]))))
    analysis.grid_start_seconds = float(fit["grid_start_seconds"])
    analysis.effective_duration_seconds = float(fit["effective_duration_seconds"])
    analysis.beat_duration_seconds = float(fit["beat_duration_seconds"])
    analysis.bar_duration_seconds = float(fit["bar_duration_seconds"])
    analysis.step_duration_seconds = float(fit["step_duration_seconds"])
    analysis.complete_bar_count = int(fit["complete_bar_count"])
    analysis.suggested_bar_count = int(fit["suggested_bar_count"])
    analysis.last_full_bar_duration_seconds = float(fit["last_full_bar_duration_seconds"])
    analysis.duration_remainder_seconds = float(fit["duration_remainder_seconds"])
    analysis.duration_remainder_beats = float(fit["duration_remainder_beats"])
    analysis.duration_remainder_steps = float(fit["duration_remainder_steps"])
    analysis.duration_fit = str(fit["duration_fit"])
    analysis.loop_warnings = list(fit["loop_warnings"])
    return analysis


def bars_duration(bars: float, bpm: float = 172.0) -> float:
    return bars * 4 * 60 / bpm


def test_loop_fit_clean_8_bar_loop() -> None:
    fit = calculate_loop_fit(duration_seconds=bars_duration(8), bpm=172.0, steps_per_bar=16)
    assert fit["duration_fit"] == "clean"
    assert fit["complete_bar_count"] == 8
    assert fit["duration_remainder_beats"] == pytest.approx(0.0)
    assert fit["suggested_bar_count"] == 8


def test_loop_fit_8_bars_plus_one_beat() -> None:
    fit = calculate_loop_fit(
        duration_seconds=bars_duration(8) + 60 / 172,
        bpm=172.0,
        steps_per_bar=16,
    )
    assert fit["duration_fit"] == "extra_beat"
    assert fit["complete_bar_count"] == 8
    assert fit["duration_remainder_beats"] == pytest.approx(1.0)
    assert fit["suggested_bar_count"] == 8
    assert "approximately 1 beat" in " ".join(fit["loop_warnings"])


def test_loop_fit_8_bars_plus_small_tail() -> None:
    fit = calculate_loop_fit(duration_seconds=bars_duration(8) + 0.03, bpm=172.0, steps_per_bar=16)
    assert fit["duration_fit"] == "small_tail"
    assert fit["suggested_bar_count"] == 8


def test_loop_fit_7_and_a_half_bars_is_partial() -> None:
    fit = calculate_loop_fit(duration_seconds=bars_duration(7.5), bpm=172.0, steps_per_bar=16)
    assert fit["duration_fit"] == "partial_bar"
    assert fit["complete_bar_count"] == 7
    assert fit["duration_remainder_beats"] == pytest.approx(2.0)
    assert "not aligned" in " ".join(fit["loop_warnings"])


def test_loop_fit_boundary_with_float_noise_is_clean() -> None:
    fit = calculate_loop_fit(duration_seconds=bars_duration(8) + 0.001, bpm=172.0, steps_per_bar=16)
    assert fit["duration_fit"] == "clean"
    assert fit["complete_bar_count"] == 8


def test_package_imports_under_breaksmith() -> None:
    assert breaksmith.__version__ == "0.1.0"


def test_cli_parser_uses_breaksmith_name() -> None:
    parser = build_parser()
    assert parser.prog == "breaksmith"
    help_text = parser.format_help()
    assert "breaksmith" in help_text
    assert "drum-and-bass" in help_text


@pytest.mark.parametrize("style", sorted(STYLE_PRESETS))
def test_every_style_generates_valid_pattern(style: str) -> None:
    pattern = generate_pattern(fake_analysis(), style, seed=42)
    assert pattern.name == style
    assert pattern.metadata["generator"] == "Breaksmith"
    assert sum(len(hits) for hits in pattern.hits.values()) > 0


def test_styles_are_meaningfully_different() -> None:
    rendered = {
        style: generate_pattern(fake_analysis(), style, seed=42).to_dict()["hits"]
        for style in STYLE_PRESETS
    }
    assert len({repr(value) for value in rendered.values()}) == len(STYLE_PRESETS)


def test_generation_is_reproducible() -> None:
    controls = GenerationControls(density=0.65, swing=0.12, humanize=0.08, variation=0.4)
    left = generate_pattern(fake_analysis(), "aggressive", seed=123, controls=controls).to_dict()
    right = generate_pattern(fake_analysis(), "aggressive", seed=123, controls=controls).to_dict()
    assert left == right


def test_different_seeds_change_output_when_variation_is_enabled() -> None:
    controls = GenerationControls(density=0.65, swing=0.12, humanize=0.08, variation=0.8)
    left = generate_pattern(fake_analysis(), "jungle", seed=1, controls=controls).to_dict()
    right = generate_pattern(fake_analysis(), "jungle", seed=2, controls=controls).to_dict()
    assert left != right


@pytest.mark.parametrize("style", ["minimal", "rolling", "aggressive", "liquid", "jungle", "techstep"])
def test_required_dnb_snares_exist(style: str) -> None:
    pattern = generate_pattern(fake_analysis(), style, seed=42)
    positions = {(hit.bar, hit.step) for hit in pattern.hits["snare"]}
    for bar in range(pattern.bars):
        assert (bar, 4) in positions
        assert (bar, 12) in positions


def test_halfstep_uses_half_time_snare_weight() -> None:
    pattern = generate_pattern(fake_analysis(), "halfstep", seed=42)
    positions = {(hit.bar, hit.step) for hit in pattern.hits["snare"]}
    assert all((bar, 12) in positions for bar in range(pattern.bars))


def test_all_hits_stay_in_grid_and_velocity_range() -> None:
    controls = GenerationControls(density=1.0, swing=0.5, humanize=1.0, variation=1.0)
    pattern = generate_pattern(fake_analysis(), "jungle", seed=9, controls=controls)
    for hits in pattern.hits.values():
        for hit in hits:
            assert 0 <= hit.bar < pattern.bars
            assert 0 <= hit.step < pattern.steps_per_bar
            assert 1 <= hit.velocity <= 127
            assert -0.45 <= hit.timing_offset_steps <= 0.49


@pytest.mark.parametrize(
    "controls",
    [
        GenerationControls(density=-0.1),
        GenerationControls(density=1.1),
        GenerationControls(swing=-0.1),
        GenerationControls(swing=0.6),
        GenerationControls(humanize=1.1),
        GenerationControls(variation=-0.1),
        GenerationControls(bars=0),
    ],
)
def test_invalid_generation_controls_are_rejected(controls: GenerationControls) -> None:
    with pytest.raises(ValueError):
        controls.validate()


def test_cli_rejects_invalid_parameter() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["generate", "input.wav", "--density", "1.5"])


def test_requested_bar_count_is_respected() -> None:
    pattern = generate_pattern(fake_analysis(), "rolling", seed=42, controls=GenerationControls(bars=8))
    assert pattern.bars == 8
    assert all(hit.bar < 8 for hits in pattern.hits.values() for hit in hits)


def test_bars_override_clamps_extra_beat_source_to_8_bars() -> None:
    analysis = analysis_with_loop_duration(bars_duration(8) + 60 / 172)
    pattern = generate_pattern(analysis, "rolling", seed=42, controls=GenerationControls(bars=8))
    assert analysis.bar_count == 9
    assert analysis.complete_bar_count == 8
    assert pattern.bars == 8
    assert pattern.metadata["source_detected_bars"] == 9
    assert pattern.metadata["generated_bars"] == 8
    assert pattern.metadata["bars_override"] == 8


def test_without_bars_preserves_ceil_behavior_for_extra_beat_source() -> None:
    analysis = analysis_with_loop_duration(bars_duration(8) + 60 / 172)
    pattern = generate_pattern(analysis, "rolling", seed=42)
    assert analysis.duration_fit == "extra_beat"
    assert pattern.bars == 9


def test_pattern_json_records_source_and_generated_bar_counts(tmp_path: Path) -> None:
    analysis = analysis_with_loop_duration(bars_duration(8) + 60 / 172)
    pattern = generate_pattern(analysis, "rolling", seed=42, controls=GenerationControls(bars=8))
    output = tmp_path / "pattern.json"
    write_pattern(pattern, output)
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["bars"] == 8
    assert data["metadata"]["source_detected_bars"] == 9
    assert data["metadata"]["generated_bars"] == 8
    assert data["metadata"]["bars_override"] == 8


def test_midi_export_completes_and_events_remain_ordered(tmp_path: Path) -> None:
    controls = GenerationControls(swing=0.2, humanize=1.0, variation=0.7)
    pattern = generate_pattern(fake_analysis(), "rolling", seed=42, controls=controls)
    output = tmp_path / "pattern.mid"
    write_midi(pattern, output)
    midi = MidiFile(output)
    assert output.exists()
    for track in midi.tracks:
        absolute = 0
        for message in track:
            assert message.time >= 0
            absolute += message.time
        assert absolute >= 0


def test_midi_export_has_no_events_outside_requested_bars(tmp_path: Path) -> None:
    analysis = analysis_with_loop_duration(bars_duration(8) + 60 / 172)
    pattern = generate_pattern(
        analysis,
        "jungle",
        seed=42,
        controls=GenerationControls(bars=8, swing=0.2, humanize=1.0),
    )
    output = tmp_path / "pattern.mid"
    write_midi(pattern, output)
    midi = MidiFile(output)
    ticks_per_step = midi.ticks_per_beat * 4 // pattern.steps_per_bar
    end_tick = pattern.bars * pattern.steps_per_bar * ticks_per_step
    for track in midi.tracks:
        absolute = 0
        for message in track:
            absolute += message.time
            assert absolute <= end_tick


def test_strudel_export_contains_breaksmith_branding(tmp_path: Path) -> None:
    pattern = generate_pattern(fake_analysis(), "liquid", seed=42)
    output = tmp_path / "pattern.strudel.js"
    write_strudel(pattern, output)
    text = output.read_text(encoding="utf-8")
    assert "Generated by Breaksmith" in text
    assert "setcpm" in text
    assert "stack(" in text


def test_strudel_export_contains_exact_requested_bar_count(tmp_path: Path) -> None:
    analysis = analysis_with_loop_duration(bars_duration(8) + 60 / 172)
    pattern = generate_pattern(analysis, "rolling", seed=42, controls=GenerationControls(bars=8))
    output = tmp_path / "pattern.strudel.js"
    write_strudel(pattern, output)
    text = output.read_text(encoding="utf-8")
    first_pattern = re.search(r's\("([^"]+)"\)', text)
    assert first_pattern is not None
    assert len(first_pattern.group(1).split(" | ")) == 8


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "abc"])
def test_cli_rejects_invalid_bars_values(value: str) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["generate", "input.wav", "--bars", value])


def test_requesting_more_bars_than_source_does_not_crash() -> None:
    pattern = generate_pattern(fake_analysis(), "rolling", seed=42, controls=GenerationControls(bars=12))
    assert pattern.bars == 12
    assert pattern.metadata["source_activity_strategy"].startswith("cycle analyzed")


def test_analyze_output_includes_grid_fit_diagnostics(monkeypatch, capsys, tmp_path: Path) -> None:
    analysis = analysis_with_loop_duration(bars_duration(8) + 60 / 172)
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    args = argparse.Namespace(
        audio=Path("test.wav"),
        output=tmp_path / "analysis.json",
        bpm=172.0,
        steps_per_bar=16,
    )
    assert cli._run_analyze(args) == 0
    output = capsys.readouterr().out
    assert "Grid fit: 8 complete bars + 1.00 beat" in output
    assert "approximately 1 beat" in output
    assert "--bars 8" in output


def test_generate_output_suggests_bars_for_extra_beat_source(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    analysis = analysis_with_loop_duration(bars_duration(8) + 60 / 172)
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    args = SimpleNamespace(
        audio=Path("test.wav"),
        output=tmp_path / "output",
        bpm=172.0,
        steps_per_bar=16,
        style="rolling",
        seed=42,
        bars=None,
        density=0.5,
        swing=0.0,
        humanize=0.0,
        variation=0.25,
    )
    assert cli._run_generate(args) == 0
    output = capsys.readouterr().out
    assert "Detected source fit: 8 complete bars + 1.00 beat" in output
    assert "Generating 9 bars because --bars was not specified." in output
    assert "--bars 8" in output


def test_generate_output_reports_exact_requested_bars(monkeypatch, capsys, tmp_path: Path) -> None:
    analysis = analysis_with_loop_duration(bars_duration(8) + 60 / 172)
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    args = SimpleNamespace(
        audio=Path("test.wav"),
        output=tmp_path / "output",
        bpm=172.0,
        steps_per_bar=16,
        style="rolling",
        seed=42,
        bars=8,
        density=0.5,
        swing=0.0,
        humanize=0.0,
        variation=0.25,
    )
    assert cli._run_generate(args) == 0
    output = capsys.readouterr().out
    assert "Requested grid: 8 bars" in output
    assert "Ignoring 0.35s of source audio beyond the requested grid boundary." in output
    assert "Generated exactly 8 bars." in output


def test_no_stale_branding_in_active_source_files() -> None:
    root = Path(__file__).resolve().parents[1]
    stale_terms = ["beat" + "-agent", "beat" + "_agent", "Beat " + "Agent", "BEAT" + "_AGENT"]
    checked_suffixes = {".py", ".md", ".toml"}
    offenders: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir() or path.suffix not in checked_suffixes:
            continue
        if any(part in {".venv", ".git", "output", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if any(term in text for term in stale_terms):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
