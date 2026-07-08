# Source Activity Maps

> **Status:** This document was written during initial development. The richer feature maps described below (low_mid, mid, transient, sustain, local_density, silence, brightness, flux, and bar-level variants) were proposed but have **not been implemented**. The generator currently uses only `onset_activity`, `low_activity`, `high_activity`, and `bar_energy`. This document is preserved for reference and potential future implementation.

Breaksmith stores step- and bar-level activity maps in `analysis.json`. These maps are normalized to `0.0` through `1.0` and are intended to guide musical decisions without hiding the editable grid.

## Currently Implemented Step-Level Maps

- `onset_activity`: transient strength. Used for snare placement, ghost-note probability, and kick/hat scoring.
- `low_activity`: sub and bass energy below 180 Hz. Used for kick placement decisions.
- `high_activity`: high-frequency energy above 3000 Hz. Used for hat and percussion density.

## Currently Implemented Bar-Level Maps

- `bar_energy`: average broad loudness per bar. Used for source restraint (modulates density per-bar based on source energy when `--source-restraint > 0`).

## Proposed But Not Implemented

The following maps were planned but not implemented. They remain in `analysis.json` if the analysis code includes them, but are not used by any generator:

- `low_mid_activity`: 180-500 Hz body and warmth (proposed for snare body, tom/percussion restraint)
- `mid_activity`: 500-3000 Hz musical midrange (proposed for masking avoidance)
- `transient_activity`: onset-dominant character (proposed for sharp rhythm reinforcement)
- `sustain_activity`: sustained energy relative to onset (proposed for syncopated response)
- `local_density`: local onset density over neighboring steps (proposed for crowded/sparse detection)
- `silence_activity`: inverse loudness (proposed for fill/pickup placement)
- `brightness_activity`: normalized spectral centroid (proposed for kit brightness decisions)
- `spectral_flux`: positive spectral change (proposed for transition detection)
- `bar_density`, `bar_brightness`, `bar_silence`: bar-level summaries of the above

## Diagnostic Export

Write a CSV view of step-level maps with:

```bash
uv run breaksmith analyze input.wav --bpm 172 --features-csv analysis-features.csv
```

The CSV includes one row per generated grid step:

```text
bar,step,time_seconds,onset_activity,low_activity,...,spectral_flux
```

(Columns for unimplemented features may still appear in the CSV if the analysis code calculates them, but they are not used in generation.)

## Current Use In Generation

The generator uses `onset_activity`, `low_activity`, `high_activity`, and `bar_energy`. See [`MUSICAL_MODEL.md`](MUSICAL_MODEL.md) for how these features are used in the generation pipeline.

## Limitations

- The maps are descriptive features, not stem separation.
- Normalization is robust enough for local decisions but not a full mastering-grade analysis.
- A high value means "prominent within this source," not an absolute acoustic measurement.
- Only 4 of the proposed 12 feature maps are implemented and used in generation.
