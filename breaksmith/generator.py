from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from .models import (
    INSTRUMENTS,
    AudioAnalysis,
    DrumPattern,
    Hit,
    Section,
    arrangement_bar_count,
)


@dataclass(frozen=True, slots=True)
class GenerationControls:
    density: float = 0.5
    swing: float = 0.0
    humanize: float = 0.0
    variation: float = 0.25
    bars: int | None = None

    def validate(self) -> None:
        for name in ("density", "humanize", "variation"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")
        if not 0.0 <= self.swing <= 0.5:
            raise ValueError("swing must be between 0.0 and 0.5")
        if self.bars is not None and self.bars <= 0:
            raise ValueError("bars must be a positive integer")


@dataclass(frozen=True, slots=True)
class VelocityRanges:
    kick: tuple[int, int]
    snare: tuple[int, int]
    ghost: tuple[int, int]
    hat: tuple[int, int]
    open_hat: tuple[int, int]
    percussion: tuple[int, int]


@dataclass(frozen=True, slots=True)
class StylePreset:
    name: str
    description: str
    required_snare_steps: tuple[float, ...]
    kick_density: float
    syncopation: float
    hat_density: float
    ghost_probability: float
    fill_density: float
    open_hat_probability: float
    percussion_density: float
    swing_amount: float
    activity_response: float
    velocities: VelocityRanges
    half_time: bool = False
    breakbeat_bias: float = 0.0
    mechanical_bias: float = 0.0


STYLE_PRESETS: dict[str, StylePreset] = {
    "minimal": StylePreset(
        name="minimal",
        description="Sparse, clean, restrained DnB groove with strong space between hits.",
        required_snare_steps=(0.25, 0.75),
        kick_density=0.25,
        syncopation=0.25,
        hat_density=0.36,
        ghost_probability=0.07,
        fill_density=0.18,
        open_hat_probability=0.08,
        percussion_density=0.05,
        swing_amount=0.02,
        activity_response=0.45,
        velocities=VelocityRanges((100, 124), (98, 121), (25, 48), (38, 82), (48, 82), (38, 78)),
    ),
    "rolling": StylePreset(
        name="rolling",
        description="Continuous forward movement with syncopated kicks and active hats.",
        required_snare_steps=(0.25, 0.75),
        kick_density=0.52,
        syncopation=0.60,
        hat_density=0.66,
        ghost_probability=0.22,
        fill_density=0.45,
        open_hat_probability=0.18,
        percussion_density=0.14,
        swing_amount=0.04,
        activity_response=0.68,
        velocities=VelocityRanges((102, 126), (100, 124), (28, 55), (42, 96), (55, 94), (42, 92)),
    ),
    "aggressive": StylePreset(
        name="aggressive",
        description="Higher density, stronger accents, more fills, and forceful velocity.",
        required_snare_steps=(0.25, 0.75),
        kick_density=0.74,
        syncopation=0.78,
        hat_density=0.82,
        ghost_probability=0.34,
        fill_density=0.72,
        open_hat_probability=0.27,
        percussion_density=0.26,
        swing_amount=0.025,
        activity_response=0.82,
        velocities=VelocityRanges(
            (108, 127), (106, 127), (34, 67), (48, 108), (62, 104), (48, 108)
        ),
    ),
    "liquid": StylePreset(
        name="liquid",
        description="Smooth, musical DnB groove with controlled hats and subtle ghost notes.",
        required_snare_steps=(0.25, 0.75),
        kick_density=0.38,
        syncopation=0.46,
        hat_density=0.56,
        ghost_probability=0.16,
        fill_density=0.28,
        open_hat_probability=0.14,
        percussion_density=0.10,
        swing_amount=0.055,
        activity_response=0.55,
        velocities=VelocityRanges((92, 116), (92, 116), (24, 48), (36, 84), (45, 78), (34, 78)),
    ),
    "jungle": StylePreset(
        name="jungle",
        description="Breakbeat-like syncopation, busier snares, shuffled percussion, strong variation.",
        required_snare_steps=(0.25, 0.75),
        kick_density=0.68,
        syncopation=0.92,
        hat_density=0.72,
        ghost_probability=0.42,
        fill_density=0.66,
        open_hat_probability=0.22,
        percussion_density=0.40,
        swing_amount=0.10,
        activity_response=0.72,
        velocities=VelocityRanges((98, 124), (95, 123), (30, 70), (38, 98), (50, 96), (42, 112)),
        breakbeat_bias=0.82,
    ),
    "halfstep": StylePreset(
        name="halfstep",
        description="Half-time weight with large spaces, heavy kick/snare emphasis, and sparse hats.",
        required_snare_steps=(0.75,),
        kick_density=0.30,
        syncopation=0.30,
        hat_density=0.30,
        ghost_probability=0.06,
        fill_density=0.16,
        open_hat_probability=0.06,
        percussion_density=0.06,
        swing_amount=0.015,
        activity_response=0.50,
        velocities=VelocityRanges((110, 127), (112, 127), (22, 42), (34, 72), (42, 74), (34, 74)),
        half_time=True,
    ),
    "techstep": StylePreset(
        name="techstep",
        description="Dark, mechanical, tight, syncopated groove with sharper accents.",
        required_snare_steps=(0.25, 0.75),
        kick_density=0.58,
        syncopation=0.70,
        hat_density=0.62,
        ghost_probability=0.20,
        fill_density=0.36,
        open_hat_probability=0.10,
        percussion_density=0.18,
        swing_amount=0.01,
        activity_response=0.62,
        velocities=VelocityRanges((106, 126), (104, 126), (28, 56), (42, 92), (48, 84), (46, 96)),
        mechanical_bias=0.76,
    ),
}

STYLE_CONFIG = STYLE_PRESETS


def _velocity(activity: float, low: int, high: int) -> int:
    return max(1, min(127, round(low + max(0.0, min(1.0, activity)) * (high - low))))


def _activity(values: list[float], index: int) -> float:
    if not values:
        return 0.0
    return values[index % len(values)]


def _step_from_fraction(steps: int, fraction: float) -> int:
    return max(0, min(steps - 1, round(steps * fraction)))


def _timing_offset(
    step: int, controls: GenerationControls, preset: StylePreset, rng: random.Random
) -> float:
    swing = min(0.5, controls.swing + preset.swing_amount)
    offset = swing if step % 2 == 1 else 0.0
    if controls.humanize:
        offset += rng.uniform(-0.08, 0.08) * controls.humanize
    return round(max(-0.45, min(0.49, offset)), 6)


def _humanized_velocity(velocity: int, controls: GenerationControls, rng: random.Random) -> int:
    if controls.humanize <= 0:
        return velocity
    delta = round(rng.uniform(-10, 10) * controls.humanize)
    return max(1, min(127, velocity + delta))


def _add_hit(
    hits: dict[str, list[Hit]],
    instrument: str,
    bar: int,
    step: int,
    velocity: int,
    controls: GenerationControls,
    preset: StylePreset,
    rng: random.Random,
) -> None:
    velocity = _humanized_velocity(velocity, controls, rng)
    timing_offset = _timing_offset(step, controls, preset, rng)
    for existing in hits[instrument]:
        if existing.bar == bar and existing.step == step:
            existing.velocity = max(existing.velocity, velocity)
            existing.timing_offset_steps = timing_offset
            return
    hits[instrument].append(
        Hit(bar=bar, step=step, velocity=velocity, timing_offset_steps=timing_offset)
    )


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


def generate_pattern(
    analysis: AudioAnalysis,
    style: str,
    *,
    seed: int,
    controls: GenerationControls | None = None,
    arrangement: Sequence[Section] | None = None,
) -> DrumPattern:
    if style not in STYLE_PRESETS:
        raise ValueError(f"Unknown style: {style}")
    controls = controls or GenerationControls()
    controls.validate()

    preset = STYLE_PRESETS[style]
    rng = random.Random(f"{seed}:{style}:{asdict(controls)}")
    steps = analysis.steps_per_bar
    bars = (
        arrangement_bar_count(arrangement)
        if arrangement is not None
        else (controls.bars or analysis.bar_count)
    )

    bar_sections = _build_bar_sections(bars, arrangement)

    hits: dict[str, list[Hit]] = {instrument: [] for instrument in INSTRUMENTS}
    density_scale = 0.45 + controls.density * 1.15
    variation_scale = controls.variation

    for bar in range(bars):
        section = bar_sections.get(bar)
        offset = (bar % max(1, analysis.bar_count)) * steps
        energy = _activity(analysis.bar_energy, bar)

        eff_kick_density = _section_scaled(preset.kick_density, section, "kick_scale")
        eff_hat_density = _section_scaled(preset.hat_density, section, "hat_scale")
        eff_ghost_prob = _section_scaled(preset.ghost_probability, section, "ghost_scale")
        eff_fill_density = _section_scaled(preset.fill_density, section, "fill_scale")
        eff_open_hat_prob = _section_scaled(preset.open_hat_probability, section, "open_hat_scale")
        eff_percussion_density = _section_scaled(
            preset.percussion_density, section, "percussion_scale"
        )
        eff_syncopation = _section_scaled(preset.syncopation, section, "syncopation_scale")
        eff_breakbeat_bias = _section_scaled(preset.breakbeat_bias, section, "breakbeat_bias_scale")
        eff_mechanical_bias = _section_scaled(
            preset.mechanical_bias, section, "mechanical_bias_scale"
        )

        for fraction in preset.required_snare_steps:
            step = _step_from_fraction(steps, fraction)
            activity = _activity(analysis.onset_activity, offset + step)
            _add_hit(
                hits,
                "snare",
                bar,
                step,
                _velocity(activity, *preset.velocities.snare),
                controls,
                preset,
                rng,
            )

        _add_hit(
            hits,
            "kick",
            bar,
            0,
            _velocity(_activity(analysis.low_activity, offset), *preset.velocities.kick),
            controls,
            preset,
            rng,
        )

        forbidden = {
            _step_from_fraction(steps, fraction) for fraction in preset.required_snare_steps
        } | {
            (_step_from_fraction(steps, fraction) - 1) % steps
            for fraction in preset.required_snare_steps
        }
        kick_candidates: list[tuple[float, int]] = []
        for step in range(1, steps):
            if step in forbidden:
                continue
            index = offset + step
            activity_score = (
                _activity(analysis.low_activity, index) * 0.62
                + _activity(analysis.onset_activity, index) * 0.38
            )
            syncopation = 0.18 if step % 4 in {1, 2, 3} else 0.0
            breakbeat = eff_breakbeat_bias * (0.16 if step in {2, 5, 7, 10, 14, 15} else 0.0)
            mechanical = eff_mechanical_bias * (0.14 if step in {3, 6, 9, 11, 14} else -0.04)
            randomness = rng.uniform(-0.18, 0.18) * variation_scale
            score = (
                activity_score * preset.activity_response
                + syncopation * eff_syncopation
                + breakbeat
                + mechanical
                + randomness
            )
            kick_candidates.append((score, step))

        desired_extra = max(0, round(eff_kick_density * density_scale * 4))
        if preset.half_time:
            desired_extra = min(desired_extra, 1)
        selected = 0
        threshold = 0.54 - eff_syncopation * 0.16 - controls.density * 0.10
        for score, step in sorted(kick_candidates, reverse=True):
            if selected >= desired_extra:
                break
            chance = 0.12 + eff_syncopation * 0.22 + controls.density * 0.20
            if score >= threshold or rng.random() < chance * variation_scale:
                if all(abs(step - hit.step) > 1 for hit in hits["kick"] if hit.bar == bar):
                    _add_hit(
                        hits,
                        "kick",
                        bar,
                        step,
                        _velocity(max(0.0, score), *preset.velocities.kick),
                        controls,
                        preset,
                        rng,
                    )
                    selected += 1

        for step in range(steps):
            index = offset + step
            accent = step % 4 == 0
            probability = (
                eff_hat_density * density_scale
                + energy * 0.18
                + _activity(analysis.high_activity, index) * 0.15
            )
            if preset.half_time and step % 4 not in {0, 2}:
                probability *= 0.45
            if eff_mechanical_bias and step % 2 == 1:
                probability *= 0.58
            if accent or rng.random() < min(0.96, probability):
                base_activity = max(
                    _activity(analysis.high_activity, index), 0.45 if accent else 0.0
                )
                _add_hit(
                    hits,
                    "closed_hat",
                    bar,
                    step,
                    _velocity(base_activity, *preset.velocities.hat),
                    controls,
                    preset,
                    rng,
                )

        for step in (steps // 2 - 1, steps - 1):
            chance = eff_open_hat_prob * density_scale + energy * 0.20
            if rng.random() < min(0.85, chance):
                _add_hit(
                    hits,
                    "open_hat",
                    bar,
                    step,
                    _velocity(energy, *preset.velocities.open_hat),
                    controls,
                    preset,
                    rng,
                )

        ghost_steps = {steps // 4 - 2, steps // 2 + 2, 3 * steps // 4 - 2, steps - 2}
        if eff_breakbeat_bias:
            ghost_steps.update({steps // 4 + 2, steps // 2 - 1, steps - 3})
        for step in sorted(step % steps for step in ghost_steps):
            index = offset + step
            emptiness = 1.0 - _activity(analysis.onset_activity, index)
            chance = eff_ghost_prob * density_scale * (0.45 + emptiness)
            if rng.random() < min(0.90, chance):
                _add_hit(
                    hits,
                    "snare",
                    bar,
                    step,
                    _velocity(emptiness, *preset.velocities.ghost),
                    controls,
                    preset,
                    rng,
                )

        percussion_steps = {steps // 2 - 2, steps // 2 + 1, steps - 3}
        if eff_breakbeat_bias:
            percussion_steps.update({1, 3, 6, 11, 15})
        for step in sorted(step % steps for step in percussion_steps):
            chance = eff_percussion_density * density_scale + eff_breakbeat_bias * 0.10
            if rng.random() < min(0.85, chance * (0.55 + variation_scale)):
                _add_hit(
                    hits,
                    "percussion",
                    bar,
                    step,
                    _velocity(
                        _activity(analysis.high_activity, offset + step),
                        *preset.velocities.percussion,
                    ),
                    controls,
                    preset,
                    rng,
                )

        is_phrase_end = (bar + 1) % 4 == 0 or bar == bars - 1
        if arrangement and section is not None:
            next_bar_section = bar_sections.get(bar + 1)
            if next_bar_section is not None and next_bar_section is not section:
                is_phrase_end = True
        if is_phrase_end:
            fill_start = 3 * steps // 4
            for step in range(fill_start, steps):
                normalized = (step - fill_start) / max(1, steps - fill_start - 1)
                chance = eff_fill_density * density_scale * (0.35 + normalized * 0.70)
                if rng.random() < min(0.96, chance):
                    instrument = "snare" if step % 2 == 0 else "percussion"
                    _add_hit(
                        hits,
                        instrument,
                        bar,
                        step,
                        _velocity(normalized, *preset.velocities.percussion),
                        controls,
                        preset,
                        rng,
                    )

    for instrument_hits in hits.values():
        instrument_hits.sort(key=lambda hit: (hit.bar, hit.step, hit.timing_offset_steps))

    arrangement_meta: dict[str, Any] | None = None
    if arrangement is not None:
        arrangement_meta = {
            "sections": [{"name": s.name, "bar_count": s.bar_count} for s in arrangement],
        }

    return DrumPattern(
        name=style,
        bpm=analysis.bpm,
        bars=bars,
        steps_per_bar=analysis.steps_per_bar,
        hits=hits,
        source_audio=analysis.source,
        seed=seed,
        metadata={
            "generator": "Breaksmith",
            "description": preset.description,
            "generator_version": "0.1.0",
            "source_detected_bars": analysis.bar_count,
            "source_complete_bars": analysis.complete_bar_count,
            "generated_bars": bars,
            "bars_override": controls.bars,
            "arrangement": arrangement_meta,
            "grid_start_seconds": analysis.grid_start_seconds,
            "downbeat_seconds": analysis.downbeat_seconds,
            "grid_start_source": analysis.grid_start_source,
            "tempo_confidence": analysis.tempo_confidence,
            "beat_confidence": analysis.beat_confidence,
            "source_activity_strategy": "cycle analyzed bar activity when generated bars exceed source bars",
            "controls": asdict(controls),
            "timing": {
                "json": "Logical grid positions plus per-hit timing_offset_steps.",
                "midi": "Swing and humanization are rendered as tick offsets.",
                "strudel": "Strudel export preserves the logical grid and documents timing feel in comments.",
            },
        },
    )
