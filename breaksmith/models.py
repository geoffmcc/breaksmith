from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


INSTRUMENTS = ("kick", "snare", "closed_hat", "open_hat", "percussion")
DURATION_FITS = ("clean", "small_tail", "extra_beat", "partial_bar")


@dataclass(slots=True)
class AudioAnalysis:
    source: str
    duration_seconds: float
    sample_rate: int
    bpm: float
    beat_times: list[float]
    bar_count: int
    steps_per_bar: int
    step_times: list[float]
    onset_activity: list[float]
    low_activity: list[float]
    high_activity: list[float]
    bar_energy: list[float]
    grid_start_seconds: float = 0.0
    effective_duration_seconds: float = 0.0
    beat_duration_seconds: float = 0.0
    bar_duration_seconds: float = 0.0
    step_duration_seconds: float = 0.0
    complete_bar_count: int = 0
    suggested_bar_count: int = 0
    last_full_bar_duration_seconds: float = 0.0
    duration_remainder_seconds: float = 0.0
    duration_remainder_beats: float = 0.0
    duration_remainder_steps: float = 0.0
    duration_fit: str = "clean"
    loop_warnings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AudioAnalysis":
        return cls(**data)


@dataclass(slots=True)
class Hit:
    bar: int
    step: int
    velocity: int
    timing_offset_steps: float = 0.0

    def to_dict(self) -> dict[str, int | float]:
        return {
            "bar": self.bar,
            "step": self.step,
            "velocity": self.velocity,
            "timing_offset_steps": round(self.timing_offset_steps, 6),
        }


@dataclass(slots=True)
class DrumPattern:
    name: str
    bpm: float
    bars: int
    steps_per_bar: int
    hits: dict[str, list[Hit]]
    source_audio: str
    seed: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bpm": self.bpm,
            "bars": self.bars,
            "steps_per_bar": self.steps_per_bar,
            "source_audio": self.source_audio,
            "seed": self.seed,
            "metadata": self.metadata,
            "hits": {
                instrument: [hit.to_dict() for hit in instrument_hits]
                for instrument, instrument_hits in self.hits.items()
            },
        }


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
