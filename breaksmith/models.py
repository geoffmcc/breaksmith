from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


INSTRUMENTS = ("kick", "snare", "closed_hat", "open_hat", "percussion")


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
