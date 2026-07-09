from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import numpy as np
import soundfile as sf

from breaksmith.app import GenerationRequest, generate_patterns, read_source_metadata
from breaksmith.models import AudioAnalysis
from breaksmith.presets import GenerationPreset, load_preset, save_preset


def fake_analysis(source: Path) -> AudioAnalysis:
    steps = 64
    return AudioAnalysis(
        source=str(source),
        duration_seconds=8.0,
        sample_rate=44100,
        bpm=172.0,
        beat_times=[index * 0.3488 for index in range(16)],
        bar_count=4,
        steps_per_bar=16,
        step_times=[index * 0.0872 for index in range(steps)],
        onset_activity=[0.4] * steps,
        low_activity=[0.5] * steps,
        high_activity=[0.3] * steps,
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
    )


def test_cli_import_does_not_initialize_qt() -> None:
    code = "import sys, breaksmith.cli as cli; cli.build_parser(); raise SystemExit('PySide6' in sys.modules or 'PySide6.QtWidgets' in sys.modules)"
    completed = subprocess.run([sys.executable, "-c", code], check=False)
    assert completed.returncode == 0


def test_source_metadata_reads_audio_file(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(8000, dtype=np.float32), 8000)

    metadata = read_source_metadata(source)

    assert metadata.sample_rate == 8000
    assert metadata.channels == 1
    assert metadata.duration_seconds == 1.0


def test_generation_service_writes_manifest_and_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(8000, dtype=np.float32), 8000)

    result = generate_patterns(
        GenerationRequest(
            audio=source,
            output=tmp_path / "output",
            style="rolling",
            bars=2,
            variants=2,
            preview=True,
        ),
        analyzer=lambda audio, **_kwargs: fake_analysis(audio),
    )

    assert result.manifest_path.exists()
    assert len(result.results) == 2
    assert all((item.directory / "pattern.mid").exists() for item in result.results)
    assert all((item.directory / "pattern-preview.wav").exists() for item in result.results)


def test_generation_preset_round_trip(tmp_path: Path) -> None:
    preset = GenerationPreset(
        "Liquid Test",
        GenerationRequest(audio=Path("loop.wav"), style="liquid", bars=8, seed=99),
    )

    path = save_preset(preset, tmp_path)
    loaded = load_preset(path)

    assert loaded.name == "Liquid Test"
    assert loaded.request.style == "liquid"
    assert loaded.request.bars == 8
    assert loaded.request.seed == 99


def test_gui_window_constructs(qtbot) -> None:  # type: ignore[no-untyped-def]
    from breaksmith.gui.window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "Breaksmith"
    assert window.analyze_button.text() == "Analyze"
    assert not window.generate_button.isEnabled()
