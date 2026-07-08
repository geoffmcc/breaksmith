from __future__ import annotations

from pathlib import Path

import pytest
from mido import MidiFile

import breaksmith
from breaksmith.cli import build_parser
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
    )


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


def test_strudel_export_contains_breaksmith_branding(tmp_path: Path) -> None:
    pattern = generate_pattern(fake_analysis(), "liquid", seed=42)
    output = tmp_path / "pattern.strudel.js"
    write_strudel(pattern, output)
    text = output.read_text(encoding="utf-8")
    assert "Generated by Breaksmith" in text
    assert "setcpm" in text
    assert "stack(" in text


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
