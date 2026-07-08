from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


INSTRUMENTS = ("kick", "snare", "closed_hat", "open_hat", "percussion")
DURATION_FITS = ("clean", "small_tail", "extra_beat", "partial_bar")

GENRES = ("dnb", "hiphop")

DNB_STYLES = ("minimal", "rolling", "aggressive", "liquid", "jungle", "halfstep", "techstep")
HIPHOP_STYLES = ("boom_bap", "lo_fi", "dusty", "soulful", "laid_back", "east_coast", "sparse")

STYLE_GENRE_MAP: dict[str, str] = {
    style: "dnb" for style in DNB_STYLES
} | {style: "hiphop" for style in HIPHOP_STYLES}

ALL_STYLES = DNB_STYLES + HIPHOP_STYLES


@dataclass(frozen=True, slots=True)
class GenreGrammar:
    """Declarative beat grammar defining genre-specific rhythmic rules."""
    hat_stride: int
    open_hat_fractions: tuple[float, ...]
    ghost_fractions: tuple[float, ...]
    fill_stride: int
    swing_base: float


DNB_GRAMMAR = GenreGrammar(
    hat_stride=1,
    open_hat_fractions=(0.4375, 0.9375),
    ghost_fractions=(0.125, 0.625, 0.875),
    fill_stride=4,
    swing_base=0.0,
)

HIPHOP_GRAMMAR = GenreGrammar(
    hat_stride=2,
    open_hat_fractions=(0.4375, 0.9375),
    ghost_fractions=(0.125, 0.625),
    fill_stride=4,
    swing_base=0.12,
)

GENRE_GRAMMARS: dict[str, GenreGrammar] = {
    "dnb": DNB_GRAMMAR,
    "hiphop": HIPHOP_GRAMMAR,
}


DEFAULT_STYLE_PER_GENRE: dict[str, str] = {
    "dnb": "minimal",
    "hiphop": "boom_bap",
}

GENRE_CONTROL_DEFAULTS: dict[str, dict[str, float]] = {
    "dnb": {
        "density": 0.5,
        "swing": 0.0,
        "humanize": 0.0,
        "variation": 0.25,
        "source_restraint": 0.0,
    },
    "hiphop": {
        "density": 0.35,
        "swing": 0.12,
        "humanize": 0.15,
        "variation": 0.30,
        "source_restraint": 0.3,
    },
}


def resolve_genre(style: str, genre: str | None = None) -> str:
    if genre is not None:
        if genre not in GENRES:
            raise ValueError(f"Unknown genre: {genre}")
        return genre
    if style not in STYLE_GENRE_MAP:
        raise ValueError(f"Unknown style: {style}")
    return STYLE_GENRE_MAP[style]


def validate_style_genre(style: str, genre: str) -> None:
    if style not in STYLE_GENRE_MAP:
        raise ValueError(f"Unknown style: {style}")
    if STYLE_GENRE_MAP[style] != genre:
        raise ValueError(
            f"style '{style}' is not available for genre '{genre}'"
        )


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
    low_mid_activity: list[float] = field(default_factory=list)
    mid_activity: list[float] = field(default_factory=list)
    rms_activity: list[float] = field(default_factory=list)
    transient_activity: list[float] = field(default_factory=list)
    sustain_activity: list[float] = field(default_factory=list)
    local_density: list[float] = field(default_factory=list)
    silence_activity: list[float] = field(default_factory=list)
    brightness_activity: list[float] = field(default_factory=list)
    spectral_flux: list[float] = field(default_factory=list)
    bar_density: list[float] = field(default_factory=list)
    bar_brightness: list[float] = field(default_factory=list)
    bar_silence: list[float] = field(default_factory=list)
    grid_start_seconds: float = 0.0
    downbeat_seconds: float = 0.0
    grid_start_source: str = "detected"
    tempo_confidence: float = 0.0
    beat_confidence: float = 0.0
    detected_beat_count: int = 0
    expected_beat_count: int = 0
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


@dataclass(frozen=True, slots=True)
class Section:
    name: str
    bar_count: int
    density_scale: float = 1.0
    hat_scale: float = 1.0
    fill_scale: float = 1.0
    ghost_scale: float = 1.0
    open_hat_scale: float = 1.0
    percussion_scale: float = 1.0
    kick_scale: float = 1.0
    snare_scale: float = 1.0
    breakbeat_bias_scale: float = 1.0
    mechanical_bias_scale: float = 1.0
    syncopation_scale: float = 1.0


SHORT_ARRANGEMENT: tuple[Section, ...] = (
    Section(
        "intro",
        4,
        density_scale=0.25,
        hat_scale=0.20,
        fill_scale=0.0,
        ghost_scale=0.0,
        open_hat_scale=0.0,
        percussion_scale=0.0,
        syncopation_scale=0.3,
        breakbeat_bias_scale=0.0,
        mechanical_bias_scale=0.0,
    ),
    Section(
        "buildup",
        8,
        density_scale=0.60,
        hat_scale=0.55,
        fill_scale=0.30,
        ghost_scale=0.40,
        open_hat_scale=0.40,
        percussion_scale=0.30,
        syncopation_scale=0.65,
    ),
    Section(
        "drop",
        16,
        density_scale=1.0,
        hat_scale=1.0,
        fill_scale=1.0,
        ghost_scale=1.0,
        open_hat_scale=1.0,
        percussion_scale=1.0,
        kick_scale=1.0,
        snare_scale=1.0,
        breakbeat_bias_scale=1.0,
        mechanical_bias_scale=1.0,
        syncopation_scale=1.0,
    ),
    Section(
        "breakdown",
        4,
        density_scale=0.35,
        hat_scale=0.25,
        fill_scale=0.05,
        ghost_scale=0.10,
        open_hat_scale=0.0,
        percussion_scale=0.05,
        syncopation_scale=0.35,
        breakbeat_bias_scale=0.2,
        mechanical_bias_scale=0.0,
    ),
    Section(
        "drop",
        16,
        density_scale=1.0,
        hat_scale=1.0,
        fill_scale=1.0,
        ghost_scale=1.0,
        open_hat_scale=1.0,
        percussion_scale=1.0,
        kick_scale=1.0,
        snare_scale=1.0,
        breakbeat_bias_scale=1.0,
        mechanical_bias_scale=1.0,
        syncopation_scale=1.0,
    ),
    Section(
        "outro",
        8,
        density_scale=0.20,
        hat_scale=0.15,
        fill_scale=0.0,
        ghost_scale=0.0,
        open_hat_scale=0.0,
        percussion_scale=0.0,
        syncopation_scale=0.25,
        breakbeat_bias_scale=0.0,
        mechanical_bias_scale=0.0,
    ),
)

BUILD_DROP_ARRANGEMENT: tuple[Section, ...] = (
    Section(
        "buildup",
        16,
        density_scale=0.50,
        hat_scale=0.45,
        fill_scale=0.25,
        ghost_scale=0.30,
        open_hat_scale=0.30,
        percussion_scale=0.20,
        syncopation_scale=0.55,
    ),
    Section(
        "drop",
        32,
        density_scale=1.0,
        hat_scale=1.0,
        fill_scale=1.0,
        ghost_scale=1.0,
        open_hat_scale=1.0,
        percussion_scale=1.0,
        kick_scale=1.0,
        snare_scale=1.0,
        breakbeat_bias_scale=1.0,
        mechanical_bias_scale=1.0,
        syncopation_scale=1.0,
    ),
    Section(
        "outro",
        4,
        density_scale=0.20,
        hat_scale=0.15,
        fill_scale=0.0,
        ghost_scale=0.0,
        open_hat_scale=0.0,
        percussion_scale=0.0,
        syncopation_scale=0.25,
        breakbeat_bias_scale=0.0,
        mechanical_bias_scale=0.0,
    ),
)

MINIMAL_ARRANGEMENT: tuple[Section, ...] = (
    Section(
        "drop",
        16,
        density_scale=1.0,
        hat_scale=1.0,
        fill_scale=1.0,
        ghost_scale=1.0,
        open_hat_scale=1.0,
        percussion_scale=1.0,
        kick_scale=1.0,
        snare_scale=1.0,
        breakbeat_bias_scale=1.0,
        mechanical_bias_scale=1.0,
        syncopation_scale=1.0,
    ),
    Section(
        "outro",
        4,
        density_scale=0.15,
        hat_scale=0.10,
        fill_scale=0.0,
        ghost_scale=0.0,
        open_hat_scale=0.0,
        percussion_scale=0.0,
        syncopation_scale=0.20,
        breakbeat_bias_scale=0.0,
        mechanical_bias_scale=0.0,
    ),
)

ARRANGEMENT_PRESETS: dict[str, tuple[Section, ...]] = {
    "short": SHORT_ARRANGEMENT,
    "build-drop": BUILD_DROP_ARRANGEMENT,
    "minimal": MINIMAL_ARRANGEMENT,
}


def arrangement_bar_count(arrangement: Sequence[Section]) -> int:
    return sum(section.bar_count for section in arrangement)


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
