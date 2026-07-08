from __future__ import annotations

import argparse
import json
import re
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from mido import MidiFile

import breaksmith
import breaksmith.cli as cli
from breaksmith.analysis import calculate_loop_fit, extract_activity_maps
from breaksmith.click import render_click_tracks
from breaksmith.cli import build_parser
from breaksmith.exporters.json_export import write_pattern
from breaksmith.exporters.midi import write_midi
from breaksmith.exporters.strudel import write_strudel
from breaksmith.generator import STYLE_PRESETS, GenerationControls, generate_pattern
from breaksmith.models import (
    ARRANGEMENT_PRESETS,
    SHORT_ARRANGEMENT,
    AudioAnalysis,
    arrangement_bar_count,
)
from breaksmith.synth import (
    INSTRUMENT_DURATIONS,
    INSTRUMENT_RENDERERS,
    render_kick,
    render_percussion,
    render_preview,
    write_preview,
)


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
        low_activity=[
            0.15 + (0.75 if index in {0, 6, 16, 26, 32, 42, 48, 58} else 0.0)
            for index in range(steps)
        ],
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


def test_activity_maps_distinguish_low_and_high_frequency_regions() -> None:
    sample_rate = 8000
    t = np.arange(sample_rate * 2) / sample_rate
    y = np.zeros_like(t, dtype=np.float32)
    y[:sample_rate] = 0.5 * np.sin(2 * np.pi * 80 * t[:sample_rate])
    y[sample_rate:] = 0.5 * np.sin(2 * np.pi * 3000 * t[sample_rate:])
    step_times = np.linspace(0, 1.75, 8)
    maps = extract_activity_maps(
        y=y,
        sample_rate=sample_rate,
        step_times=step_times,
        steps_per_bar=4,
        onset_envelope=np.zeros(32),
        hop_length=512,
    )
    assert np.mean(maps["low_activity"][:4]) > np.mean(maps["low_activity"][4:])
    assert np.mean(maps["high_activity"][4:]) > np.mean(maps["high_activity"][:4])
    assert len(maps["bar_energy"]) == 2


def test_activity_maps_detect_silence_and_avoid_nan() -> None:
    sample_rate = 8000
    step_times = np.linspace(0, 1.75, 8)
    maps = extract_activity_maps(
        y=np.zeros(sample_rate * 2, dtype=np.float32),
        sample_rate=sample_rate,
        step_times=step_times,
        steps_per_bar=4,
        onset_envelope=np.zeros(32),
        hop_length=512,
    )
    for values in maps.values():
        assert np.all(np.isfinite(values))
    assert min(maps["silence_activity"]) == pytest.approx(1.0)


def test_activity_maps_expose_sustain_for_steady_tone() -> None:
    sample_rate = 8000
    t = np.arange(sample_rate * 2) / sample_rate
    y = (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    step_times = np.linspace(0, 1.75, 8)
    maps = extract_activity_maps(
        y=y,
        sample_rate=sample_rate,
        step_times=step_times,
        steps_per_bar=4,
        onset_envelope=np.zeros(32),
        hop_length=512,
    )
    assert np.mean(maps["sustain_activity"]) > np.mean(maps["transient_activity"])
    assert len(maps["mid_activity"]) == 8


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


def test_loop_fit_uses_effective_duration_after_grid_start() -> None:
    fit = calculate_loop_fit(
        duration_seconds=0.25 + bars_duration(4),
        bpm=172.0,
        steps_per_bar=16,
        grid_start_seconds=0.25,
    )
    assert fit["duration_fit"] == "clean"
    assert fit["complete_bar_count"] == 4
    assert fit["grid_start_seconds"] == pytest.approx(0.25)


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


@pytest.mark.parametrize(
    "style", ["minimal", "rolling", "aggressive", "liquid", "jungle", "techstep"]
)
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
    pattern = generate_pattern(
        fake_analysis(), "rolling", seed=42, controls=GenerationControls(bars=8)
    )
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


def test_pattern_metadata_records_timing_confidence() -> None:
    analysis = fake_analysis()
    analysis.grid_start_seconds = 0.125
    analysis.downbeat_seconds = 0.125
    analysis.grid_start_source = "manual_grid_start"
    analysis.tempo_confidence = 1.0
    analysis.beat_confidence = 0.75
    pattern = generate_pattern(analysis, "rolling", seed=42)
    assert pattern.metadata["grid_start_seconds"] == 0.125
    assert pattern.metadata["downbeat_seconds"] == 0.125
    assert pattern.metadata["grid_start_source"] == "manual_grid_start"
    assert pattern.metadata["tempo_confidence"] == 1.0
    assert pattern.metadata["beat_confidence"] == 0.75


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


def test_midi_velocity_curve_exponential_reduces_low_velocities(tmp_path: Path) -> None:
    pattern = generate_pattern(fake_analysis(), "rolling", seed=42)
    output = tmp_path / "linear.mid"
    write_midi(pattern, output, velocity_curve="linear")
    linear_midi = MidiFile(output)
    output2 = tmp_path / "exponential.mid"
    write_midi(pattern, output2, velocity_curve="exponential")
    exp_midi = MidiFile(output2)
    linear_vels = []
    exp_vels = []
    for track in linear_midi.tracks:
        for msg in track:
            if msg.type == "note_on":
                linear_vels.append(msg.velocity)
    for track in exp_midi.tracks:
        for msg in track:
            if msg.type == "note_on":
                exp_vels.append(msg.velocity)
    assert len(exp_vels) == len(linear_vels)
    assert sum(exp_vels) < sum(linear_vels)


def test_midi_export_has_note_off_velocities(tmp_path: Path) -> None:
    pattern = generate_pattern(fake_analysis(), "minimal", seed=42)
    output = tmp_path / "pattern.mid"
    write_midi(pattern, output)
    midi = MidiFile(output)
    note_off_velocities = []
    for track in midi.tracks:
        for msg in track:
            if msg.type == "note_off":
                note_off_velocities.append(msg.velocity)
    assert all(vel > 0 for vel in note_off_velocities)


def test_midi_export_has_groove_marker(tmp_path: Path) -> None:
    pattern = generate_pattern(fake_analysis(), "jungle", seed=42)
    output = tmp_path / "pattern.mid"
    write_midi(pattern, output)
    midi = MidiFile(output)
    markers = []
    for track in midi.tracks:
        for msg in track:
            if msg.type == "marker":
                markers.append(msg.text)
    assert any("groove" in m for m in markers)
    assert any("shuffled" in m for m in markers)


def test_midi_velocity_curve_hard_increases_loud_velocities(tmp_path: Path) -> None:
    pattern = generate_pattern(fake_analysis(), "aggressive", seed=42)
    output = tmp_path / "linear.mid"
    write_midi(pattern, output, velocity_curve="linear")
    linear_midi = MidiFile(output)
    output2 = tmp_path / "hard.mid"
    write_midi(pattern, output2, velocity_curve="hard")
    hard_midi = MidiFile(output2)
    linear_max = 0
    hard_max = 0
    for track in linear_midi.tracks:
        for msg in track:
            if msg.type == "note_on" and msg.velocity > linear_max:
                linear_max = msg.velocity
    for track in hard_midi.tracks:
        for msg in track:
            if msg.type == "note_on" and msg.velocity > hard_max:
                hard_max = msg.velocity
    assert hard_max >= linear_max


def test_midi_with_velocity_curve_from_cli(monkeypatch, tmp_path: Path) -> None:
    analysis = fake_analysis()
    analysis.source = str(tmp_path / "source.wav")
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(4000, dtype=np.float32), 4000)
    args = SimpleNamespace(
        audio=source,
        output=tmp_path / "output",
        bpm=172.0,
        steps_per_bar=16,
        style="rolling",
        seed=42,
        bars=2,
        density=0.5,
        swing=0.0,
        humanize=0.0,
        variation=0.25,
        grid_start=None,
        downbeat_start=None,
        preview=False,
        preview_bars=None,
        preview_comparison=False,
        structure=None,
        genre=None,
        source_restraint=None,
        phrase_awareness=0.3,
        groove="straight",
        variants=1,
        kick_density=None,
        snare_density=None,
        hat_density=None,
        open_hat_density=None,
        percussion_density=None,
        midi_velocity_curve="exponential",
    )
    assert cli._run_generate(args) == 0
    midi_path = tmp_path / "output" / "rolling" / "pattern.mid"
    assert midi_path.exists()
    midi = MidiFile(midi_path)
    note_on_count = sum(
        1 for track in midi.tracks for msg in track if msg.type == "note_on"
    )
    assert note_on_count > 0


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


@pytest.mark.parametrize("option", ["--grid-start", "--downbeat-start"])
def test_cli_rejects_negative_grid_overrides(option: str) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["analyze", "input.wav", option, "-0.1"])


def test_requesting_more_bars_than_source_does_not_crash() -> None:
    pattern = generate_pattern(
        fake_analysis(), "rolling", seed=42, controls=GenerationControls(bars=12)
    )
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
        grid_start=None,
        downbeat_start=None,
        render_click=False,
        features_csv=None,
    )
    assert cli._run_analyze(args) == 0
    output = capsys.readouterr().out
    assert "Grid fit: 8 complete bars + 1.00 beat" in output
    assert "approximately 1 beat" in output
    assert "--bars 8" in output


def test_analyze_passes_manual_grid_start_to_analysis(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, float | None] = {}

    def fake_analyze(*args, **kwargs):
        captured["grid_start_override"] = kwargs["grid_start_override"]
        captured["downbeat_override"] = kwargs["downbeat_override"]
        analysis = fake_analysis()
        analysis.grid_start_seconds = kwargs["grid_start_override"]
        analysis.downbeat_seconds = kwargs["grid_start_override"]
        analysis.grid_start_source = "manual_grid_start"
        return analysis

    monkeypatch.setattr(cli, "analyze_audio", fake_analyze)
    args = argparse.Namespace(
        audio=Path("test.wav"),
        output=tmp_path / "analysis.json",
        bpm=172.0,
        steps_per_bar=16,
        grid_start=0.125,
        downbeat_start=None,
        render_click=False,
        features_csv=None,
    )
    assert cli._run_analyze(args) == 0
    assert captured == {"grid_start_override": 0.125, "downbeat_override": None}


def test_analyze_output_includes_timing_confidence(monkeypatch, capsys, tmp_path: Path) -> None:
    analysis = fake_analysis()
    analysis.tempo_confidence = 1.0
    analysis.beat_confidence = 0.5
    analysis.detected_beat_count = 8
    analysis.expected_beat_count = 16
    analysis.grid_start_seconds = 0.125
    analysis.downbeat_seconds = 0.125
    analysis.grid_start_source = "manual_grid_start"
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    args = argparse.Namespace(
        audio=Path("test.wav"),
        output=tmp_path / "analysis.json",
        bpm=172.0,
        steps_per_bar=16,
        grid_start=0.125,
        downbeat_start=None,
        render_click=False,
        features_csv=None,
    )
    assert cli._run_analyze(args) == 0
    output = capsys.readouterr().out
    assert "Timing confidence: tempo=1.00, beat=0.50 (8/16 beats)" in output
    assert "Grid start: 0.125s (manual_grid_start); downbeat: 0.125s" in output


def test_analyze_render_click_writes_diagnostic_files(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(4000, dtype=np.float32), 4000)
    analysis = fake_analysis()
    analysis.source = str(source)
    analysis.duration_seconds = 1.0
    analysis.bpm = 120.0
    analysis.grid_start_seconds = 0.25
    analysis.downbeat_seconds = 0.25
    analysis.beat_duration_seconds = 0.5
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    args = argparse.Namespace(
        audio=source,
        output=tmp_path / "analysis.json",
        bpm=120.0,
        steps_per_bar=16,
        grid_start=0.25,
        downbeat_start=None,
        render_click=True,
        features_csv=None,
    )
    assert cli._run_analyze(args) == 0
    assert (tmp_path / "analysis-click.wav").exists()
    assert (tmp_path / "source-with-click.wav").exists()


def test_analyze_writes_feature_csv(monkeypatch, tmp_path: Path) -> None:
    analysis = fake_analysis()
    analysis.rms_activity = [0.1] * len(analysis.step_times)
    analysis.low_mid_activity = [0.2] * len(analysis.step_times)
    analysis.mid_activity = [0.3] * len(analysis.step_times)
    analysis.transient_activity = [0.4] * len(analysis.step_times)
    analysis.sustain_activity = [0.5] * len(analysis.step_times)
    analysis.local_density = [0.6] * len(analysis.step_times)
    analysis.silence_activity = [0.7] * len(analysis.step_times)
    analysis.brightness_activity = [0.8] * len(analysis.step_times)
    analysis.spectral_flux = [0.9] * len(analysis.step_times)
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    features_csv = tmp_path / "features.csv"
    args = argparse.Namespace(
        audio=Path("test.wav"),
        output=tmp_path / "analysis.json",
        bpm=172.0,
        steps_per_bar=16,
        grid_start=None,
        downbeat_start=None,
        render_click=False,
        features_csv=features_csv,
    )
    assert cli._run_analyze(args) == 0
    text = features_csv.read_text(encoding="utf-8")
    assert "low_mid_activity" in text
    assert "spectral_flux" in text


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
        grid_start=None,
        downbeat_start=None,
        preview=False,
        preview_bars=None,
        preview_comparison=False,
        structure=None,
        genre=None,
        source_restraint=None,
        phrase_awareness=0.3,
        groove="straight",
        variants=1,
        kick_density=None,
        snare_density=None,
        hat_density=None,
        open_hat_density=None,
        percussion_density=None,
        midi_velocity_curve="linear",
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
        grid_start=None,
        downbeat_start=None,
        preview=False,
        preview_bars=None,
        preview_comparison=False,
        structure=None,
        genre=None,
        source_restraint=None,
        phrase_awareness=0.3,
        groove="straight",
        variants=1,
        kick_density=None,
        snare_density=None,
        hat_density=None,
        open_hat_density=None,
        percussion_density=None,
        midi_velocity_curve="linear",
    )
    assert cli._run_generate(args) == 0
    output = capsys.readouterr().out
    assert "Requested grid: 8 bars" in output
    assert "Ignoring 0.35s of source audio beyond the requested grid boundary." in output
    assert "Generated exactly 8 bars." in output


def test_render_click_tracks_places_clicks_at_grid_positions(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    sample_rate = 4000
    sf.write(source, np.zeros(sample_rate, dtype=np.float32), sample_rate)
    analysis = fake_analysis()
    analysis.duration_seconds = 1.0
    analysis.grid_start_seconds = 0.25
    analysis.downbeat_seconds = 0.25
    analysis.beat_duration_seconds = 0.5
    click_path, mixed_path = render_click_tracks(source, analysis, tmp_path)
    click, sr = sf.read(click_path, dtype="float32")
    mixed, mixed_sr = sf.read(mixed_path, dtype="float32")
    assert sr == sample_rate
    assert mixed_sr == sample_rate
    assert len(click) == sample_rate
    assert len(mixed) == sample_rate
    assert np.max(np.abs(click[950:1100])) > 0.1
    assert np.max(np.abs(click[2950:3100])) > 0.1
    assert np.max(np.abs(click[:800])) == pytest.approx(0.0)


def test_all_synth_renderers_return_correct_length() -> None:
    sample_rate = 44100
    for name, renderer in INSTRUMENT_RENDERERS.items():
        duration = INSTRUMENT_DURATIONS[name]
        sound = renderer(sample_rate, duration, seed=42)
        expected = max(1, round(sample_rate * duration))
        assert len(sound) == expected, f"{name}: expected {expected}, got {len(sound)}"


def test_all_synth_renderers_produce_nonzero_audio() -> None:
    for name, renderer in INSTRUMENT_RENDERERS.items():
        sound = renderer(44100, INSTRUMENT_DURATIONS[name], seed=42)
        assert np.max(np.abs(sound)) > 0.01, f"{name} produced silence"


@pytest.mark.parametrize("renderer", [render_kick, render_percussion])
def test_tonal_synth_has_audible_frequency_content(renderer) -> None:
    sound = renderer(44100, 0.1, seed=42)
    spectrum = np.abs(np.fft.rfft(sound))
    lower = spectrum[: len(spectrum) // 4]
    upper = spectrum[len(spectrum) // 4 :]
    assert np.sum(lower) > np.sum(upper), f"{renderer.__name__} lacks low-end content"


def test_render_preview_returns_correct_length() -> None:
    pattern = generate_pattern(fake_analysis(), "rolling", seed=42)
    sr = 22050
    audio = render_preview(pattern, sample_rate=sr, seed=42)
    step_dur = (60.0 / pattern.bpm) * 4.0 / pattern.steps_per_bar
    expected_seconds = pattern.bars * pattern.steps_per_bar * step_dur
    padding = max(INSTRUMENT_DURATIONS.values()) * 1.2
    expected_samples = max(1, round((expected_seconds + padding) * sr))
    assert len(audio) == expected_samples


def test_render_preview_produces_audible_output() -> None:
    pattern = generate_pattern(
        fake_analysis(), "aggressive", seed=42, controls=GenerationControls(density=1.0)
    )
    audio = render_preview(pattern, sample_rate=22050, seed=42)
    assert np.max(np.abs(audio)) > 0.01


def test_write_preview_creates_valid_wav(tmp_path: Path) -> None:
    pattern = generate_pattern(fake_analysis(), "liquid", seed=42)
    output = tmp_path / "preview.wav"
    result = write_preview(pattern, output, seed=42)
    assert result == output
    assert output.exists()
    data, sr = sf.read(output, dtype="float32")
    assert sr == 44100
    assert len(data) > 0
    assert np.max(np.abs(data)) > 0.0


def test_generate_with_preview_writes_wav(monkeypatch, tmp_path: Path) -> None:
    analysis = fake_analysis()
    analysis.source = str(tmp_path / "source.wav")
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(4000, dtype=np.float32), 4000)
    args = SimpleNamespace(
        audio=source,
        output=tmp_path / "output",
        bpm=172.0,
        steps_per_bar=16,
        style="rolling",
        seed=42,
        bars=2,
        density=0.5,
        swing=0.0,
        humanize=0.0,
        variation=0.25,
        grid_start=None,
        downbeat_start=None,
        preview=True,
        preview_bars=None,
        preview_comparison=False,
        structure=None,
        genre=None,
        source_restraint=None,
        phrase_awareness=0.3,
        groove="straight",
        variants=1,
        kick_density=None,
        snare_density=None,
        hat_density=None,
        open_hat_density=None,
        percussion_density=None,
        midi_velocity_curve="linear",
    )
    assert cli._run_generate(args) == 0
    preview = tmp_path / "output" / "rolling" / "pattern-preview.wav"
    assert preview.exists()
    data, sr = sf.read(preview, dtype="float32")
    assert sr == 44100
    assert len(data) > 0


def test_generate_preview_matches_render_preview(monkeypatch, tmp_path: Path) -> None:
    analysis = fake_analysis()
    analysis.source = str(tmp_path / "source.wav")
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(4000, dtype=np.float32), 4000)
    args = SimpleNamespace(
        audio=source,
        output=tmp_path / "output",
        bpm=172.0,
        steps_per_bar=16,
        style="rolling",
        seed=42,
        bars=2,
        density=0.5,
        swing=0.0,
        humanize=0.0,
        variation=0.25,
        grid_start=None,
        downbeat_start=None,
        preview=True,
        preview_bars=None,
        preview_comparison=False,
        structure=None,
        genre=None,
        source_restraint=None,
        phrase_awareness=0.3,
        groove="straight",
        variants=1,
        kick_density=None,
        snare_density=None,
        hat_density=None,
        open_hat_density=None,
        percussion_density=None,
        midi_velocity_curve="linear",
    )
    assert cli._run_generate(args) == 0
    preview_path = tmp_path / "output" / "rolling" / "pattern-preview.wav"
    assert preview_path.exists()


def test_arrangement_presets_have_correct_bar_totals() -> None:
    assert arrangement_bar_count(SHORT_ARRANGEMENT) == 56
    assert arrangement_bar_count(ARRANGEMENT_PRESETS["build-drop"]) == 52
    assert arrangement_bar_count(ARRANGEMENT_PRESETS["minimal"]) == 20


def test_arrangement_overrides_bars_in_pattern() -> None:
    pattern = generate_pattern(fake_analysis(), "rolling", seed=42, arrangement=SHORT_ARRANGEMENT)
    assert pattern.bars == 56
    assert pattern.metadata["arrangement"] is not None
    assert pattern.metadata["arrangement"]["sections"][0]["name"] == "intro"


def test_arrangement_with_controls_bars_is_ignored_by_generator() -> None:
    pattern = generate_pattern(
        fake_analysis(),
        "aggressive",
        seed=42,
        controls=GenerationControls(bars=16),
        arrangement=SHORT_ARRANGEMENT,
    )
    assert pattern.bars == 56


def test_intro_section_has_fewer_hits_than_drop() -> None:
    pattern = generate_pattern(fake_analysis(), "rolling", seed=42, arrangement=SHORT_ARRANGEMENT)
    intro_hits = sum(1 for hits in pattern.hits.values() for hit in hits if hit.bar < 4)
    drop_start = 4 + 8  # intro(4) + buildup(8)
    drop_end = drop_start + 16
    drop_hits = sum(
        1 for hits in pattern.hits.values() for hit in hits if drop_start <= hit.bar < drop_end
    )
    assert intro_hits < drop_hits


def test_outro_has_reduced_density_compared_to_full_arrangement() -> None:
    pattern = generate_pattern(fake_analysis(), "jungle", seed=42, arrangement=SHORT_ARRANGEMENT)
    intro_bar_hits = sum(1 for hits in pattern.hits.values() for hit in hits if hit.bar == 0)
    drop_bar_hits = sum(1 for hits in pattern.hits.values() for hit in hits if hit.bar == 12)
    outro_bar_hits = sum(1 for hits in pattern.hits.values() for hit in hits if hit.bar == 54)
    assert drop_bar_hits > intro_bar_hits
    assert drop_bar_hits > outro_bar_hits


def test_generate_with_structure_cli_flag(monkeypatch, capsys, tmp_path: Path) -> None:
    analysis = fake_analysis()
    analysis.source = str(tmp_path / "source.wav")
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(4000, dtype=np.float32), 4000)
    args = SimpleNamespace(
        audio=source,
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
        grid_start=None,
        downbeat_start=None,
        preview=False,
        preview_bars=None,
        preview_comparison=False,
        structure="short",
        genre=None,
        source_restraint=None,
        phrase_awareness=0.3,
        groove="straight",
        variants=1,
        kick_density=None,
        snare_density=None,
        hat_density=None,
        open_hat_density=None,
        percussion_density=None,
        midi_velocity_curve="linear",
    )
    assert cli._run_generate(args) == 0
    output = capsys.readouterr().out
    assert "intro(4b) → buildup(8b) → drop(16b) → breakdown(4b) → drop(16b) → outro(8b)" in output
    assert "56 total bars" in output
    assert "short arrangement" in output


def test_generate_with_structure_overrides_bars(monkeypatch, capsys, tmp_path: Path) -> None:
    analysis = fake_analysis()
    analysis.source = str(tmp_path / "source.wav")
    monkeypatch.setattr(cli, "analyze_audio", lambda *args, **kwargs: analysis)
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(4000, dtype=np.float32), 4000)
    args = SimpleNamespace(
        audio=source,
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
        grid_start=None,
        downbeat_start=None,
        preview=False,
        preview_bars=None,
        preview_comparison=False,
        structure="minimal",
        genre=None,
        source_restraint=None,
        phrase_awareness=0.3,
        groove="straight",
        variants=1,
        kick_density=None,
        snare_density=None,
        hat_density=None,
        open_hat_density=None,
        percussion_density=None,
        midi_velocity_curve="linear",
    )
    assert cli._run_generate(args) == 0
    captured = capsys.readouterr()
    assert "Warning: --structure overrides --bars" in captured.err
    assert "drop(16b) → outro(4b)" in captured.out
    assert "20 total bars" in captured.out


def test_no_stale_branding_in_active_source_files() -> None:
    root = Path(__file__).resolve().parents[1]
    stale_terms = ["beat" + "-agent", "beat" + "_agent", "Beat " + "Agent", "BEAT" + "_AGENT"]
    checked_suffixes = {".py", ".md", ".toml"}
    offenders: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir() or path.suffix not in checked_suffixes:
            continue
        if any(part in {".venv", ".venv2", ".git", "output", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        if any(term in text for term in stale_terms):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
