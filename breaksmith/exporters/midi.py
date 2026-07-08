from __future__ import annotations

from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

from ..models import DrumPattern


GM_DRUM_NOTES = {
    "kick": 36,
    "snare": 38,
    "closed_hat": 42,
    "open_hat": 46,
    "percussion": 37,
}

NOTE_LENGTH_FRACTIONS = {
    "kick": 0.85,
    "snare": 0.65,
    "closed_hat": 0.25,
    "open_hat": 0.85,
    "percussion": 0.45,
}

VELOCITY_CURVES = {
    "linear": lambda v: v,
    "exponential": lambda v: max(1, round(127.0 * (v / 127.0) ** 1.5)),
    "compressed": lambda v: max(1, round(40 + (v - 40) * 0.6)) if v > 40 else v,
    "hard": lambda v: max(1, round(127.0 * (v / 127.0) ** 0.6)),
}


def _apply_velocity_curve(velocity: int, curve: str) -> int:
    fn = VELOCITY_CURVES.get(curve)
    if fn is None:
        return velocity
    return max(1, min(127, fn(velocity)))


GROOVE_FEEL_MARKERS: dict[str, str] = {
    "minimal": "straight",
    "rolling": "forward",
    "aggressive": "hard",
    "liquid": "laid-back",
    "jungle": "shuffled",
    "halfstep": "half-time",
    "techstep": "mechanical",
}


def write_midi(
    pattern: DrumPattern,
    output_path: Path,
    *,
    velocity_curve: str = "linear",
) -> None:
    ticks_per_beat = 480
    ticks_per_step = ticks_per_beat * 4 // pattern.steps_per_bar

    midi = MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    conductor = MidiTrack()
    midi.tracks.append(conductor)
    conductor.append(MetaMessage("track_name", name=f"{pattern.name} conductor", time=0))
    conductor.append(MetaMessage("set_tempo", tempo=bpm2tempo(pattern.bpm), time=0))
    conductor.append(MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    feel = GROOVE_FEEL_MARKERS.get(pattern.name, "straight")
    conductor.append(MetaMessage("marker", text=f"groove: {feel}", time=0))
    swing_meta = pattern.metadata.get("controls", {}).get("swing", 0.0)
    conductor.append(MetaMessage("marker", text=f"swing: {swing_meta:.2f}", time=0))
    if pattern.metadata.get("arrangement"):
        sections = pattern.metadata["arrangement"]["sections"]
        bar_cursor = 0
        for sec in sections:
            section_start_ticks = bar_cursor * pattern.steps_per_bar * ticks_per_step
            conductor.append(
                MetaMessage("marker", text=f"section: {sec['name']}", time=section_start_ticks)
            )
            bar_cursor += sec["bar_count"]

    for instrument, note in GM_DRUM_NOTES.items():
        track = MidiTrack()
        midi.tracks.append(track)
        track.append(MetaMessage("track_name", name=instrument, time=0))

        length_fraction = NOTE_LENGTH_FRACTIONS.get(instrument, 0.5)
        events: list[tuple[int, Message]] = []
        max_start_tick = pattern.bars * pattern.steps_per_bar * ticks_per_step - 1
        for hit in pattern.hits.get(instrument, []):
            absolute_step = hit.bar * pattern.steps_per_bar + hit.step
            raw = round((absolute_step + hit.timing_offset_steps) * ticks_per_step)
            start = max(0, min(max_start_tick, raw))
            vel = _apply_velocity_curve(hit.velocity, velocity_curve)
            length = max(1, round(length_fraction * ticks_per_step))
            release = max(0, min(63, vel // 2 - 1))
            events.append(
                (
                    start,
                    Message(
                        "note_on",
                        channel=9,
                        note=note,
                        velocity=vel,
                        time=0,
                    ),
                )
            )
            events.append(
                (
                    min(start + length, max_start_tick),
                    Message(
                        "note_off",
                        channel=9,
                        note=note,
                        velocity=release,
                        time=0,
                    ),
                )
            )

        previous_tick = 0
        for absolute_tick, message in sorted(
            events,
            key=lambda item: (item[0], 0 if item[1].type == "note_off" else 1),
        ):
            message.time = absolute_tick - previous_tick
            previous_tick = absolute_tick
            track.append(message)

    midi.save(output_path)
