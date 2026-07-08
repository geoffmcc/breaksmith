from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from .models import (
    GENRE_GRAMMARS,
    INSTRUMENTS,
    AudioAnalysis,
    DrumPattern,
    Hit,
    Section,
    arrangement_bar_count,
)
from .generator_shared import (
    GenerationControls,
    _build_bar_sections,
    _layer_density_multipliers,
    _section_scaled,
    _velocity,
    _activity,
    _step_from_fraction,
    _humanized_velocity,
    groove_timing_offset,
)


@dataclass(frozen=True, slots=True)
class HipHopVelocityRanges:
    kick: tuple[int, int]
    snare: tuple[int, int]
    ghost: tuple[int, int]
    hat: tuple[int, int]
    open_hat: tuple[int, int]
    percussion: tuple[int, int]


@dataclass(frozen=True, slots=True)
class HipHopStylePreset:
    name: str
    description: str
    kick_density: float
    syncopation: float
    hat_density: float
    ghost_probability: float
    fill_density: float
    open_hat_probability: float
    percussion_density: float
    swing_amount: float
    activity_response: float
    velocities: HipHopVelocityRanges
    snare_late_offset: float = 0.0


HIPHOP_PRESETS: dict[str, HipHopStylePreset] = {
    "boom_bap": HipHopStylePreset(
        name="boom_bap",
        description="Classic hip-hop with strong kick/snare relationship and snare on 2 and 4.",
        kick_density=0.30,
        syncopation=0.35,
        hat_density=0.55,
        ghost_probability=0.08,
        fill_density=0.12,
        open_hat_probability=0.06,
        percussion_density=0.08,
        swing_amount=0.12,
        activity_response=0.50,
        velocities=HipHopVelocityRanges(
            (100, 127), (98, 124), (20, 42), (32, 78), (42, 72), (32, 72)
        ),
        snare_late_offset=0.0,
    ),
    "lo_fi": HipHopStylePreset(
        name="lo_fi",
        description="Softer, swung hip-hop with loose timing and restraint.",
        kick_density=0.22,
        syncopation=0.25,
        hat_density=0.38,
        ghost_probability=0.06,
        fill_density=0.06,
        open_hat_probability=0.04,
        percussion_density=0.04,
        swing_amount=0.18,
        activity_response=0.40,
        velocities=HipHopVelocityRanges(
            (78, 104), (72, 96), (16, 34), (28, 66), (32, 58), (24, 58)
        ),
        snare_late_offset=0.02,
    ),
    "dusty": HipHopStylePreset(
        name="dusty",
        description="Hard but imperfect pocket with moderate swing and character.",
        kick_density=0.28,
        syncopation=0.30,
        hat_density=0.45,
        ghost_probability=0.10,
        fill_density=0.10,
        open_hat_probability=0.06,
        percussion_density=0.08,
        swing_amount=0.14,
        activity_response=0.52,
        velocities=HipHopVelocityRanges(
            (96, 124), (94, 120), (22, 40), (30, 76), (38, 68), (30, 74)
        ),
        snare_late_offset=0.01,
    ),
    "soulful": HipHopStylePreset(
        name="soulful",
        description="Smooth pocket with supportive dynamics and gentle phrase changes.",
        kick_density=0.22,
        syncopation=0.24,
        hat_density=0.40,
        ghost_probability=0.08,
        fill_density=0.06,
        open_hat_probability=0.05,
        percussion_density=0.04,
        swing_amount=0.10,
        activity_response=0.40,
        velocities=HipHopVelocityRanges(
            (84, 110), (82, 104), (18, 36), (28, 66), (34, 60), (28, 62)
        ),
        snare_late_offset=0.0,
    ),
    "laid_back": HipHopStylePreset(
        name="laid_back",
        description="Minimal, spacious hip-hop with late snares and strong pocket.",
        kick_density=0.16,
        syncopation=0.18,
        hat_density=0.28,
        ghost_probability=0.04,
        fill_density=0.04,
        open_hat_probability=0.02,
        percussion_density=0.02,
        swing_amount=0.20,
        activity_response=0.35,
        velocities=HipHopVelocityRanges(
            (80, 106), (76, 100), (14, 30), (24, 58), (28, 48), (22, 52)
        ),
        snare_late_offset=0.03,
    ),
    "east_coast": HipHopStylePreset(
        name="east_coast",
        description="Firmer boom-bap attack with tighter swing and strong snare.",
        kick_density=0.34,
        syncopation=0.38,
        hat_density=0.55,
        ghost_probability=0.12,
        fill_density=0.16,
        open_hat_probability=0.08,
        percussion_density=0.10,
        swing_amount=0.08,
        activity_response=0.55,
        velocities=HipHopVelocityRanges(
            (106, 127), (104, 126), (24, 46), (36, 84), (48, 80), (36, 82)
        ),
        snare_late_offset=0.0,
    ),
    "sparse": HipHopStylePreset(
        name="sparse",
        description="Very few events with strong anchors and large spaces.",
        kick_density=0.12,
        syncopation=0.10,
        hat_density=0.20,
        ghost_probability=0.02,
        fill_density=0.02,
        open_hat_probability=0.01,
        percussion_density=0.01,
        swing_amount=0.12,
        activity_response=0.30,
        velocities=HipHopVelocityRanges(
            (92, 118), (90, 116), (18, 34), (28, 56), (32, 54), (26, 58)
        ),
        snare_late_offset=0.0,
    ),
}



def _add_hit(
    hits: dict[str, list[Hit]],
    instrument: str,
    bar: int,
    step: int,
    velocity: int,
    humanize: float,
    swing: float,
    snare_late_offset: float,
    rng: random.Random,
    groove: str = "straight",
    steps_per_bar: int = 16,
) -> None:
    velocity = _humanized_velocity(velocity, humanize, rng)
    timing_offset = swing if step % 2 == 1 else 0.0
    if instrument == "snare" and snare_late_offset:
        timing_offset += snare_late_offset
    if humanize:
        timing_offset += rng.uniform(-0.06, 0.06) * humanize
    timing_offset += groove_timing_offset(groove, steps_per_bar, step)
    timing_offset = round(max(-0.45, min(0.49, timing_offset)), 6)
    for existing in hits[instrument]:
        if existing.bar == bar and existing.step == step:
            existing.velocity = max(existing.velocity, velocity)
            existing.timing_offset_steps = timing_offset
            return
    hits[instrument].append(
        Hit(bar=bar, step=step, velocity=velocity, timing_offset_steps=timing_offset)
    )


def generate_hiphop_pattern(
    analysis: AudioAnalysis,
    style: str,
    *,
    seed: int,
    controls: GenerationControls | None = None,
    arrangement: Sequence[Section] | None = None,
) -> DrumPattern:
    if style not in HIPHOP_PRESETS:
        raise ValueError(f"Unknown hip-hop style: {style}")
    controls = controls or GenerationControls()
    controls.validate()

    preset = HIPHOP_PRESETS[style]
    grammar = GENRE_GRAMMARS.get("hiphop")
    rng = random.Random(f"{seed}:{style}:hiphop:{asdict(controls)}")
    steps = analysis.steps_per_bar
    bars = (
        arrangement_bar_count(arrangement)
        if arrangement is not None
        else (controls.bars or analysis.bar_count)
    )

    primary_beats = controls.meter.primary_beats_per_bar
    steps_per_beat = steps // primary_beats
    if primary_beats == 4:
        snare_fractions = (0.25, 0.75)
    elif primary_beats == 3:
        snare_fractions = (1.0 / 3.0,)
    else:
        snare_fractions = (0.5,)

    bar_sections = _build_bar_sections(bars, arrangement)

    hits: dict[str, list[Hit]] = {instrument: [] for instrument in INSTRUMENTS}
    density_scale = 0.40 + controls.density * 1.10
    ldm = _layer_density_multipliers(controls)
    variation_scale = controls.variation
    humanize = controls.humanize
    swing = min(0.5, controls.swing + preset.swing_amount)
    restraint = controls.source_restraint
    phrase_aware = controls.phrase_awareness
    groove_name = controls.groove

    for bar in range(bars):
        section = bar_sections.get(bar)
        offset = (bar % max(1, analysis.bar_count)) * steps
        energy = _activity(analysis.bar_energy, bar)
        bar_scale = 1.0 + restraint * (energy - 1.0)
        bar_in_phrase = bar % grammar.phrase_length
        phrase_t = bar_in_phrase / max(1, grammar.phrase_length - 1)
        phrase_factor = 1.0 + phrase_aware * (phrase_t - 0.5) * 0.5

        eff_kick_density = _section_scaled(preset.kick_density, section, "kick_scale") * bar_scale * phrase_factor
        eff_hat_density = _section_scaled(preset.hat_density, section, "hat_scale") * bar_scale * phrase_factor
        eff_ghost_prob = _section_scaled(preset.ghost_probability, section, "ghost_scale") * bar_scale / max(0.1, phrase_factor)
        eff_fill_density = _section_scaled(preset.fill_density, section, "fill_scale") * bar_scale * phrase_factor
        eff_open_hat_prob = _section_scaled(
            preset.open_hat_probability, section, "open_hat_scale"
        ) * bar_scale * phrase_factor
        eff_percussion_density = _section_scaled(
            preset.percussion_density, section, "percussion_scale"
        ) * bar_scale * phrase_factor

        for fraction in snare_fractions:
            step = _step_from_fraction(steps, fraction)
            _add_hit(
                hits, "snare", bar, step,
                _velocity(
                    _activity(analysis.onset_activity, offset + step),
                    *preset.velocities.snare,
                ),
                humanize, swing, preset.snare_late_offset, rng,
                groove_name, steps,
            )

        _add_hit(
            hits, "kick", bar, 0,
            _velocity(_activity(analysis.low_activity, offset), *preset.velocities.kick),
            humanize, swing, 0.0, rng,
            groove_name, steps,
        )

        kick_forbidden = {_step_from_fraction(steps, f) for f in snare_fractions}
        kick_candidates: list[tuple[float, int]] = []
        for step in range(1, steps):
            if step in kick_forbidden:
                continue
            index = offset + step
            score = (
                _activity(analysis.low_activity, index) * 0.60
                + _activity(analysis.onset_activity, index) * 0.30
                + rng.uniform(-0.10, 0.10) * variation_scale * phrase_factor
            )
            kick_candidates.append((score, step))

        desired_extra = max(0, round(eff_kick_density * density_scale * (primary_beats - 1) * ldm["kick"]))
        selected = 0
        for score, step in sorted(kick_candidates, reverse=True):
            if selected >= desired_extra:
                break
            chance = 0.15 + controls.density * 0.15
            if score >= 0.45 or rng.random() < chance * variation_scale:
                if all(abs(step - hit.step) > 1 for hit in hits["kick"] if hit.bar == bar):
                    _add_hit(
                        hits, "kick", bar, step,
                        _velocity(max(0.0, score), *preset.velocities.kick),
                        humanize, swing, 0.0, rng,
                        groove_name, steps,
                    )
                    selected += 1

        for step in range(0, steps, grammar.hat_stride):
            index = offset + step
            accent = step % steps_per_beat == 0
            probability = eff_hat_density * density_scale * ldm["closed_hat"] + (0.08 if accent else 0.0)
            if step % (2 * steps_per_beat) == steps_per_beat:
                probability += 0.06
            if rng.random() < min(0.92, probability):
                base = max(
                    _activity(analysis.high_activity, index), 0.40 if accent else 0.0
                )
                _add_hit(
                    hits, "closed_hat", bar, step,
                    _velocity(base, *preset.velocities.hat),
                    humanize, swing, 0.0, rng,
                    groove_name, steps,
                )

        for fraction in grammar.open_hat_fractions:
            step = _step_from_fraction(steps, fraction)
            chance = eff_open_hat_prob * density_scale * ldm["open_hat"] + energy * 0.10
            if rng.random() < min(0.60, chance):
                _add_hit(
                    hits, "open_hat", bar, step,
                    _velocity(energy, *preset.velocities.open_hat),
                    humanize, swing, 0.0, rng,
                    groove_name, steps,
                )

        ghost_set = {_step_from_fraction(steps, f) for f in grammar.ghost_fractions}
        for gs in sorted(ghost_set):
            index = offset + gs
            emptiness = 1.0 - _activity(analysis.onset_activity, index)
            chance = eff_ghost_prob * density_scale * ldm["snare"] * (0.40 + emptiness)
            if rng.random() < min(0.75, chance):
                _add_hit(
                    hits, "snare", bar, gs,
                    _velocity(emptiness, *preset.velocities.ghost),
                    humanize, swing, preset.snare_late_offset, rng,
                    groove_name, steps,
                )

        percussion_steps = {
            2 * steps_per_beat - 2,
            2 * steps_per_beat + 2,
            steps - 3,
        }
        for ps in sorted(g % steps for g in percussion_steps):
            chance = eff_percussion_density * density_scale * ldm["percussion"] * phrase_factor
            if rng.random() < min(0.70, chance):
                _add_hit(
                    hits, "percussion", bar, ps,
                    _velocity(
                        _activity(analysis.high_activity, offset + ps),
                        *preset.velocities.percussion,
                    ),
                    humanize, swing, 0.0, rng,
                    groove_name, steps,
                )

        is_phrase_end = (bar + 1) % grammar.fill_stride == 0 or bar == bars - 1
        if arrangement and section is not None:
            next_section = bar_sections.get(bar + 1)
            if next_section is not None and next_section is not section:
                is_phrase_end = True
        if is_phrase_end:
            fill_start = (primary_beats - 1) * steps_per_beat
            for fs in range(fill_start, steps):
                normalized = (fs - fill_start) / max(1, steps - fill_start - 1)
                chance = eff_fill_density * density_scale * min(ldm["snare"], ldm["percussion"]) * (0.30 + normalized * 0.50)
                if rng.random() < min(0.85, chance):
                    inst = "snare" if fs % 2 == 0 else "percussion"
                    _add_hit(
                        hits, inst, bar, fs,
                        _velocity(normalized, *preset.velocities.percussion),
                        humanize, swing,
                        preset.snare_late_offset if inst == "snare" else 0.0,
                        rng,
                        groove_name, steps,
                    )

    for instrument_hits in hits.values():
        instrument_hits.sort(key=lambda hit: (hit.bar, hit.step, hit.timing_offset_steps))

    arrangement_meta = None
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
        meter=controls.meter,
        metadata={
            "generator": "Breaksmith",
            "genre": "hiphop",
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
