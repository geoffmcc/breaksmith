from __future__ import annotations

import json
from pathlib import Path

from ..models import AudioAnalysis, DrumPattern


FEATURE_FIELDS = (
    "onset_activity",
    "low_activity",
    "low_mid_activity",
    "mid_activity",
    "high_activity",
    "rms_activity",
    "transient_activity",
    "sustain_activity",
    "local_density",
    "silence_activity",
    "brightness_activity",
    "spectral_flux",
)


def write_analysis(analysis: AudioAnalysis, output_path: Path) -> None:
    output_path.write_text(
        json.dumps(analysis.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def write_pattern(pattern: DrumPattern, output_path: Path) -> None:
    output_path.write_text(
        json.dumps(pattern.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def write_feature_csv(analysis: AudioAnalysis, output_path: Path) -> None:
    headers = ["bar", "step", "time_seconds", *FEATURE_FIELDS]
    lines = [",".join(headers)]
    for index, time_seconds in enumerate(analysis.step_times):
        row = [
            str(index // analysis.steps_per_bar),
            str(index % analysis.steps_per_bar),
            f"{time_seconds:.6f}",
        ]
        for field in FEATURE_FIELDS:
            values = getattr(analysis, field)
            row.append(f"{values[index]:.6f}" if index < len(values) else "0.000000")
        lines.append(",".join(row))
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
