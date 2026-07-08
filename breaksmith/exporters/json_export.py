from __future__ import annotations

import json
from pathlib import Path

from ..models import AudioAnalysis, DrumPattern


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
