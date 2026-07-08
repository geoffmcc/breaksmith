from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from .models import GROOVE_PRESETS, Section


@dataclass(frozen=True, slots=True)
class GenerationControls:
    density: float = 0.5
    swing: float = 0.0
    humanize: float = 0.0
    variation: float = 0.25
    source_restraint: float = 0.0
    phrase_awareness: float = 0.3
    groove: str = "straight"
    bars: int | None = None
    genre: str | None = None
    kick_density: float | None = None
    snare_density: float | None = None
    hat_density: float | None = None
    open_hat_density: float | None = None
    percussion_density: float | None = None

    def validate(self) -> None:
        for name in ("density", "humanize", "variation", "source_restraint", "phrase_awareness"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
        if not 0.0 <= self.swing <= 0.5:
            raise ValueError("swing must be between 0.0 and 0.5")
        if self.bars is not None and self.bars <= 0:
            raise ValueError("bars must be a positive integer")
        for name in ("kick_density", "snare_density", "hat_density", "open_hat_density", "percussion_density"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
        if self.groove not in GROOVE_PRESETS:
            raise ValueError(f"Unknown groove: {self.groove}")


def _build_bar_sections(
    bars: int, arrangement: Sequence[Section] | None
) -> dict[int, Section | None]:
    if arrangement is None:
        return {}
    bar_to_section: dict[int, Section | None] = {}
    bar_index = 0
    for section in arrangement:
        for _ in range(section.bar_count):
            if bar_index < bars:
                bar_to_section[bar_index] = section
            bar_index += 1
    return bar_to_section


def _section_scaled(value: float, section: Section | None, attr: str) -> float:
    if section is None:
        return value
    return value * getattr(section, attr, 1.0)


def _velocity(activity: float, low: int, high: int) -> int:
    return max(1, min(127, round(low + max(0.0, min(1.0, activity)) * (high - low))))


def _activity(values: list[float], index: int) -> float:
    if not values:
        return 0.0
    return values[index % len(values)]


def _step_from_fraction(steps: int, fraction: float) -> int:
    return max(0, min(steps - 1, round(steps * fraction)))


def _timing_offset(
    step: int, controls: GenerationControls, swing_amount: float, rng: random.Random
) -> float:
    swing = min(0.5, controls.swing + swing_amount)
    offset = swing if step % 2 == 1 else 0.0
    if controls.humanize:
        offset += rng.uniform(-0.08, 0.08) * controls.humanize
    return round(max(-0.45, min(0.49, offset)), 6)


def _layer_density_multipliers(controls: GenerationControls) -> dict[str, float]:
    return {
        "kick": controls.kick_density if controls.kick_density is not None else 1.0,
        "snare": controls.snare_density if controls.snare_density is not None else 1.0,
        "closed_hat": controls.hat_density if controls.hat_density is not None else 1.0,
        "open_hat": controls.open_hat_density if controls.open_hat_density is not None else 1.0,
        "percussion": controls.percussion_density if controls.percussion_density is not None else 1.0,
    }


def _humanized_velocity(velocity: int, humanize: float, rng: random.Random) -> int:
    if humanize <= 0:
        return velocity
    delta = round(rng.uniform(-10, 10) * humanize)
    return max(1, min(127, velocity + delta))


def groove_timing_offset(groove: str, steps_per_bar: int, step: int) -> float:
    template = GROOVE_PRESETS.get(groove)
    if template is None or not template.timing_offsets:
        return 0.0
    off_len = len(template.timing_offsets)
    if off_len == 0:
        return 0.0
    idx = step % off_len
    return template.timing_offsets[idx]
