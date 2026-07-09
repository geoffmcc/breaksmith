from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


INSTRUMENTS = ("kick", "snare", "closed_hat", "open_hat", "percussion")
DURATION_FITS = ("clean", "small_tail", "extra_beat", "partial_bar")


@dataclass(frozen=True, slots=True)
class Meter:
    numerator: int
    denominator: int
    beat_groups: tuple[int, ...]
    tempo_unit: str
    primary_beats_per_bar: int
    pulses_per_bar: int
    steps_per_bar: int

    @property
    def display(self) -> str:
        return f"{self.numerator}/{self.denominator}"

    @property
    def is_compound(self) -> bool:
        return self.numerator % 3 == 0 and self.denominator == 8

    @property
    def is_simple(self) -> bool:
        return not self.is_compound

    @property
    def beat_group_count(self) -> int:
        return len(self.beat_groups)

    def step_group(self, step: int) -> int:
        """Return which primary-beat group a step belongs to (0-indexed)."""
        if not self.beat_groups or self.steps_per_bar <= 0:
            return 0
        steps_per_primary = self.steps_per_bar / max(1, self.primary_beats_per_bar)
        return min(len(self.beat_groups) - 1, int(step // steps_per_primary))

    def beat_for_step(self, step: int) -> int:
        """Return the primary beat index for a given step."""
        if self.steps_per_bar <= 0:
            return 0
        steps_per_beat = self.steps_per_bar / max(1, self.primary_beats_per_bar)
        return int(step // steps_per_beat)

    def step_in_beat(self, step: int) -> int:
        """Return the sub-step position within the primary beat."""
        if self.steps_per_bar <= 0:
            return 0
        steps_per_beat = self.steps_per_bar / max(1, self.primary_beats_per_bar)
        return int(step % steps_per_beat)

    def is_downbeat(self, step: int) -> bool:
        """True if step lands on the first primary beat."""
        return step == 0

    def is_primary_beat(self, step: int) -> bool:
        """True if step lands on any primary beat (including downbeat)."""
        if self.steps_per_bar <= 0 or self.primary_beats_per_bar <= 0:
            return False
        steps_per_beat = self.steps_per_bar / self.primary_beats_per_bar
        return step % steps_per_beat == 0

    def accent_strength(self, step: int) -> float:
        """Accent strength for a step: 1.0 = strong, ~0.7 = secondary, 0.0 = none."""
        if step == 0:
            return 1.0
        if not self.beat_groups:
            return 0.0
        steps_per_primary = self.steps_per_bar / max(1, self.primary_beats_per_bar)
        beat_idx = int(step // steps_per_primary)
        if step % steps_per_primary != 0:
            return 0.0
        cumulative = 0
        for i, group_size in enumerate(self.beat_groups):
            cumulative += group_size
            if beat_idx < cumulative:
                return 0.7 if i > 0 else 1.0
        return 0.0

    def downbeat_steps(self) -> list[int]:
        """List of step positions that are primary beats."""
        if self.steps_per_bar <= 0 or self.primary_beats_per_bar <= 0:
            return [0]
        steps_per_beat = self.steps_per_bar / self.primary_beats_per_bar
        return [round(i * steps_per_beat) for i in range(self.primary_beats_per_bar)]

    def group_accent_steps(self) -> list[tuple[int, float]]:
        """List of (step, strength) for beat-group accents within a bar."""
        if not self.beat_groups:
            return [(0, 1.0)]
        steps_per_primary = self.steps_per_bar / max(1, self.primary_beats_per_bar)
        result = []
        for i in range(len(self.beat_groups)):
            step = round(i * steps_per_primary)
            strength = 1.0 if i == 0 else 0.7
            result.append((step, strength))
        return result

    def beat_duration(self, bpm: float) -> float:
        if bpm <= 0:
            return 0.0
        return 60.0 / bpm

    def bar_duration(self, bpm: float) -> float:
        if bpm <= 0:
            return 0.0
        return self.primary_beats_per_bar * self.beat_duration(bpm)

    def step_duration(self, bpm: float) -> float:
        if bpm <= 0 or self.steps_per_bar <= 0:
            return 0.0
        return self.bar_duration(bpm) / self.steps_per_bar

    def pulse_duration(self, bpm: float) -> float:
        """Duration of one pulse (eighth note in 6/8, quarter in 4/4)."""
        if bpm <= 0 or self.pulses_per_bar <= 0:
            return 0.0
        return self.bar_duration(bpm) / self.pulses_per_bar

    def to_dict(self) -> dict[str, Any]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "display": self.display,
            "beat_groups": list(self.beat_groups),
            "tempo_unit": self.tempo_unit,
            "primary_beats_per_bar": self.primary_beats_per_bar,
            "pulses_per_bar": self.pulses_per_bar,
            "steps_per_bar": self.steps_per_bar,
        }


METER_44 = Meter(
    numerator=4, denominator=4,
    beat_groups=(1, 1, 1, 1),
    tempo_unit="quarter",
    primary_beats_per_bar=4,
    pulses_per_bar=4,
    steps_per_bar=16,
)

METER_34 = Meter(
    numerator=3, denominator=4,
    beat_groups=(1, 1, 1),
    tempo_unit="quarter",
    primary_beats_per_bar=3,
    pulses_per_bar=3,
    steps_per_bar=12,
)

METER_68 = Meter(
    numerator=6, denominator=8,
    beat_groups=(3, 3),
    tempo_unit="dotted_quarter",
    primary_beats_per_bar=2,
    pulses_per_bar=6,
    steps_per_bar=12,
)

METER_PRESETS: dict[str, Meter] = {
    "4/4": METER_44,
    "3/4": METER_34,
    "6/8": METER_68,
}


def parse_time_signature(value: str) -> Meter:
    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid time signature: '{value}'. Use format '4/4', '3/4', '6/8'.")
    key = value.strip()
    if key not in METER_PRESETS:
        allowed = ", ".join(METER_PRESETS)
        raise ValueError(f"Unsupported time signature: '{key}'. Supported: {allowed}")
    return METER_PRESETS[key]


def validate_beat_grouping(meter: Meter, grouping: str | None) -> Meter:
    if grouping is None:
        return meter
    parts = [int(p) for p in grouping.split("+")]
    if len(parts) != meter.beat_group_count:
        raise ValueError(
            f"Beat grouping '{grouping}' has {len(parts)} groups, "
            f"but {meter.display} expects {meter.beat_group_count} groups "
            f"({' + '.join(str(g) for g in meter.beat_groups)})."
        )
    if sum(parts) != meter.pulses_per_bar:
        raise ValueError(
            f"Beat grouping '{grouping}' sums to {sum(parts)}, "
            f"but {meter.display} has {meter.pulses_per_bar} pulses per bar. "
            f"Expected: {'+'.join(str(g) for g in meter.beat_groups)}"
        )
    return Meter(
        numerator=meter.numerator,
        denominator=meter.denominator,
        beat_groups=tuple(parts),
        tempo_unit=meter.tempo_unit,
        primary_beats_per_bar=meter.primary_beats_per_bar,
        pulses_per_bar=meter.pulses_per_bar,
        steps_per_bar=meter.steps_per_bar,
    )

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
    phrase_length: int = 4


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
class TempoScoreComponents:
    bpm_plausibility: float = 0.0
    onset_spacing: float = 0.0
    bar_fit: float = 0.0
    beat_fit: float = 0.0
    bar_count_plausibility: float = 0.0
    beat_count_plausibility: float = 0.0
    raw_proximity: float = 0.0
    detector_confidence: float = 0.0
    grid_fit: float = 0.0


@dataclass(slots=True)
class TempoCandidateDiagnostic:
    bpm: float
    valid: bool
    octave_shift: int
    octave_multiplier: float
    grid_start_seconds: float = 0.0
    grid_start_source: str = "audio_start"
    rejection_reason: str = ""
    total_score: float = 0.0
    score_components: TempoScoreComponents = field(default_factory=TempoScoreComponents)
    inferred_beats: float = 0.0
    inferred_bars: float = 0.0
    nearest_whole_beats: int = 0
    nearest_whole_bars: int = 0
    beat_fit_error_seconds: float = 0.0
    bar_fit_error_seconds: float = 0.0
    fit_classification: str = "partial_bar"
    onset_evidence: str = "unavailable"
    confidence_contribution: float = 0.0
    tie_break_outcome: str = ""
    rationale: str = ""


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
    meter: Meter = METER_44
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
    raw_detected_bpm: float = 0.0
    candidate_bpm_values: list[float] = field(default_factory=list)
    tempo_selection_score: float = 0.0
    tempo_selection_reason: str = ""
    bar_fit_score: float = 0.0
    tempo_source: str = "detected"
    octave_correction_applied: bool = False
    octave_multiplier: float = 1.0
    octave_shift: int = 0
    tempo_ambiguous: bool = False
    tempo_tie_break: str = ""
    tempo_candidates: list[TempoCandidateDiagnostic] = field(default_factory=list)

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
    meter: Meter = METER_44
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


@dataclass(frozen=True, slots=True)
class GrooveTemplate:
    name: str
    description: str
    timing_offsets: tuple[float, ...]
    compatible_meters: tuple[str, ...] = ("4/4", "3/4", "6/8")


GROOVE_PRESETS: dict[str, GrooveTemplate] = {
    "straight": GrooveTemplate(
        name="straight",
        description="No groove offset; all steps on the grid.",
        timing_offsets=(),
    ),
    "mpc": GrooveTemplate(
        name="mpc",
        description="Classic MPC-style swing: off-beat 16ths pushed slightly late.",
        timing_offsets=(
            0.000, 0.000, 0.014, 0.000,
            0.000, 0.000, 0.014, 0.000,
            0.000, 0.000, 0.014, 0.000,
            0.000, 0.000, 0.014, 0.000,
        ),
    ),
    "laid_back": GrooveTemplate(
        name="laid_back",
        description="Relaxed feel: off-beats consistently late.",
        timing_offsets=(
            0.000, 0.018, 0.000, 0.022,
            0.000, 0.018, 0.000, 0.022,
            0.000, 0.018, 0.000, 0.022,
            0.000, 0.018, 0.000, 0.022,
        ),
    ),
    "pushed": GrooveTemplate(
        name="pushed",
        description="Driving feel: off-beats slightly early.",
        timing_offsets=(
            0.000, -0.012, 0.000, -0.016,
            0.000, -0.012, 0.000, -0.016,
            0.000, -0.012, 0.000, -0.016,
            0.000, -0.012, 0.000, -0.016,
        ),
    ),
    "shuffled": GrooveTemplate(
        name="shuffled",
        description="Strong shuffle: every second 16th note pushed late.",
        timing_offsets=(
            0.000, 0.000, 0.028, 0.000,
            0.000, 0.000, 0.028, 0.000,
            0.000, 0.000, 0.028, 0.000,
            0.000, 0.000, 0.028, 0.000,
        ),
    ),
}
