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


def write_midi(pattern: DrumPattern, output_path: Path) -> None:
    ticks_per_beat = 480
    ticks_per_step = ticks_per_beat * 4 // pattern.steps_per_bar

    midi = MidiFile(type=1, ticks_per_beat=ticks_per_beat)
    conductor = MidiTrack()
    midi.tracks.append(conductor)
    conductor.append(MetaMessage("track_name", name=f"{pattern.name} conductor", time=0))
    conductor.append(MetaMessage("set_tempo", tempo=bpm2tempo(pattern.bpm), time=0))
    conductor.append(MetaMessage("time_signature", numerator=4, denominator=4, time=0))

    for instrument, note in GM_DRUM_NOTES.items():
        track = MidiTrack()
        midi.tracks.append(track)
        track.append(MetaMessage("track_name", name=instrument, time=0))

        events: list[tuple[int, Message]] = []
        for hit in pattern.hits.get(instrument, []):
            absolute_step = hit.bar * pattern.steps_per_bar + hit.step
            start = max(0, round((absolute_step + hit.timing_offset_steps) * ticks_per_step))
            length = max(1, ticks_per_step // 2)
            events.append(
                (
                    start,
                    Message(
                        "note_on",
                        channel=9,
                        note=note,
                        velocity=hit.velocity,
                        time=0,
                    ),
                )
            )
            events.append(
                (
                    start + length,
                    Message(
                        "note_off",
                        channel=9,
                        note=note,
                        velocity=0,
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
