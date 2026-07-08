# Source Activity Maps

Breaksmith stores step- and bar-level activity maps in `analysis.json`. These maps are normalized to `0.0` through `1.0` and are intended to guide musical decisions without hiding the editable grid.

## Step-Level Maps

- `onset_activity`: transient strength. Use for drum-space decisions, accents, fills, and avoiding clutter.
- `low_activity`: sub and bass energy below 180 Hz. Use for kick reinforcement, kick avoidance, and low-end crowding decisions.
- `low_mid_activity`: 180-500 Hz body and warmth. Use for snare body, tom/percussion restraint, and avoiding muddy fills.
- `mid_activity`: 500-3000 Hz musical midrange. Use to avoid masking melodies, chords, and vocals.
- `high_activity`: high-frequency energy above 3000 Hz. Use for hat brightness, cymbal restraint, and percussion density.
- `rms_activity`: broad loudness/energy. Use for arrangement density and section energy.
- `transient_activity`: onset-dominant character. Use to identify sharp source rhythms that drums can reinforce or answer.
- `sustain_activity`: sustained energy relative to onset strength. Use for syncopated response rather than constant doubling.
- `local_density`: local onset density over neighboring steps. Use to decide where the source is crowded or sparse.
- `silence_activity`: inverse loudness. Use to identify space for fills, pickups, or exposed drum movement.
- `brightness_activity`: normalized spectral centroid. Use for kit brightness, hat intensity, and sample-choice decisions.
- `spectral_flux`: positive spectral change. Use for transition detection and momentum cues.

## Bar-Level Maps

- `bar_energy`: average broad loudness per bar.
- `bar_density`: average local onset density per bar.
- `bar_brightness`: average brightness per bar.
- `bar_silence`: average silence/space per bar.

## Diagnostic Export

Write a CSV view of step-level maps with:

```bash
uv run breaksmith analyze input.wav --bpm 172 --features-csv analysis-features.csv
```

The CSV includes one row per generated grid step:

```text
bar,step,time_seconds,onset_activity,low_activity,...,spectral_flux
```

## Current Use In Generation

The existing generator still primarily uses `onset_activity`, `low_activity`, `high_activity`, and `bar_energy`. The richer maps are now available for Phase 4 and Phase 6 work, where Breaksmith will plan phrases and score drum interactions more deliberately.

## Limitations

- The maps are descriptive features, not stem separation.
- Normalization is robust enough for local decisions but not a full mastering-grade analysis.
- A high value means “prominent within this source,” not an absolute acoustic measurement.
