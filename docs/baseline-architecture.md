# Breaksmith Baseline Architecture

> **Status:** Historical architecture documentation from initial development phase. The current codebase has evolved significantly since this was written — see [the README](../README.md) and [MUSICAL_MODEL.md](MUSICAL_MODEL.md) for current documentation. This document is preserved for architectural reference.

## Current Package Structure

- `breaksmith/analysis.py`: audio decoding, BPM handling, beat-grid creation, source activity extraction, and loop-fit diagnostics.
- `breaksmith/models.py`: shared dataclasses for `AudioAnalysis`, `Hit`, and `DrumPattern`.
- `breaksmith/generator.py`: style presets, generation controls, deterministic seeded pattern generation, timing offsets, and pattern metadata.
- `breaksmith/cli.py`: `analyze` and `generate` commands, argument validation, diagnostics, and export orchestration.
- `breaksmith/synth.py`: drum sound synthesis (kick, snare, hat, percussion) used for audio preview rendering.
- `breaksmith/models.py`: shared dataclasses for `AudioAnalysis`, `Hit`, `DrumPattern`, `Section`, and `Arrangement`.
- `breaksmith/exporters/json_export.py`: JSON output for analysis and patterns.
- `breaksmith/exporters/midi.py`: multi-track General MIDI drum export with per-instrument note lengths, velocity curves, note-off velocities, groove markers, and section markers.
- `breaksmith/exporters/strudel.py`: editable Strudel pattern export.
- `tests/test_generator.py`: unit and integration coverage for generation, loop-fit diagnostics, exporters, CLI parser behavior, and stale branding.

## What Already Works

- Audio files are loaded through `librosa` with source sample rate preserved.
- BPM is estimated with `librosa.beat.beat_track`, with optional `--bpm` override.
- Likely half-time/double-time BPM estimates are folded into a DnB-friendly range when BPM is not overridden.
- Beat-grid and step-grid timing are created for 4/4 material.
- Loop-fit diagnostics classify source duration as `clean`, `small_tail`, `extra_beat`, or `partial_bar`.
- `--bars` generation clamps output to an exact requested bar count without falsifying `analysis.json`.
- Pattern generation supports seven styles: `minimal`, `rolling`, `aggressive`, `liquid`, `jungle`, `halfstep`, and `techstep`.
- Generation is deterministic for the same source analysis, style, controls, and seed.
- Exporters produce JSON, MIDI, and Strudel from the same `DrumPattern` model.
- MIDI renders timing offsets as ticks; JSON preserves logical grid positions plus `timing_offset_steps`.

## Timing Analysis Baseline

Timing is calculated in `analysis.py`.

- `beat_duration = 60 / bpm`.
- `step_duration = beat_duration * 4 / steps_per_bar`.
- The grid starts at the first tracked beat when beat tracking is reliable.
- If too few beats are found, the grid starts at `0.0` and a warning is emitted.
- If the first tracked beat is implausibly late, the grid is anchored to `0.0` and a warning is emitted.
- `calculate_loop_fit()` computes effective duration from `duration_seconds - grid_start_seconds` and classifies duration fit.
- Clean loop boundaries now avoid accidental extra bars from floating-point edge cases.

Known timing limitations:

- Pickup handling is heuristic-only.
- Downbeat detection is currently simple and should be treated as a risk area.

## Source Activity Maps

Current source-aware features are stored on `AudioAnalysis` as step-level lists:

- `onset_activity`
- `low_activity`
- `high_activity`
- `bar_energy`

The extraction process uses onset strength, STFT band averages, RMS, and percentile normalization.

The following maps were proposed but not implemented: low_mid_activity, mid_activity, transient_activity, sustain_activity, local_density, silence_activity, brightness_activity, spectral_flux, and bar-level variants. See [`source-activity-maps.md`](source-activity-maps.md) for the current state.

## Generator Architecture Baseline

Generation lives in `generator.py`.

The current model is:

```text
style preset
+ source activity values
+ generation controls
+ seeded random variation
-> DrumPattern
```

Styles are typed `StylePreset` objects that control:

- required snare positions
- kick density
- syncopation
- hat density
- ghost-note probability
- fill density
- open-hat probability
- percussion density
- swing amount
- source activity response
- velocity ranges
- half-time, breakbeat, and mechanical biases

Randomness is introduced in:

- kick candidate scoring
- optional kick selection
- hat and open-hat inclusion
- ghost-note inclusion
- percussion inclusion
- phrase-end fills
- timing and velocity humanization

Generation already handles requested bars greater than analyzed bars by cycling source activity. This prevents out-of-range access but is not yet musically planned.

Musical limitations (some addressed in later development):

- ~~Styles are more than raw probabilities, but they are not yet full grammars or template systems.~~ Genre grammars (`GenreGrammar`) and groove templates (`GrooveTemplate`) now provide structured rhythmic frameworks.
- ~~Drum decisions are still mostly local step decisions rather than phrase-aware event scoring.~~ Phrase awareness (`--phrase-awareness`) now modulates density, fills, and hats across each 4-bar phrase.
- Generated hits do not carry provenance, confidence, lock state, duration, or stable IDs — still not implemented.

## Export Architecture Baseline

All exporters consume the shared `DrumPattern` model.

JSON:

- Stores pattern metadata, hits, velocities, logical bar/step positions, and timing offsets.
- Also stores source-detected and generated bar counts in metadata.

MIDI:

- Writes a type-1 MIDI file.
- Uses separate tracks for kick, snare, closed hat, open hat, and percussion.
- Uses General MIDI drum notes on channel 10.
- Writes tempo and 4/4 time-signature metadata.
- Applies `timing_offset_steps` at export time.

Strudel:

- Writes readable grid-based patterns using `bd`, `sd`, `hh`, `oh`, and `rim`.
- Preserves logical grid readability rather than encoding detailed microtiming.
- Documents timing controls in comments.

Export limitations:

- MIDI provides separate tracks per instrument. Configurable MIDI mappings are not yet implemented.
- Strudel represents timing controls as comments (Strudel's own timing model handles performance).
- Export validation is covered by tests but not centralized as a pattern validation stage.

## Current CLI Baseline

Commands:

- `breaksmith analyze AUDIO`
- `breaksmith generate AUDIO`

Important options (current — see [CLI.md](CLI.md) for full list):

- `--bpm`, `--steps-per-bar`, `--output`, `--style`, `--genre`, `--seed`, `--bars`
- `--density`, `--swing`, `--humanize`, `--variation`
- `--source-restraint`, `--phrase-awareness`, `--groove`
- `--kick-density`, `--snare-density`, `--hat-density`, `--open-hat-density`, `--percussion-density`
- `--midi-velocity-curve`, `--preview`, `--preview-bars`, `--preview-comparison`
- `--variants`, `--structure`

CLI limitations:

- There is no cache for analysis within repeated workflows.

## Phase 1 Status

The following Phase 1 features from this document have been implemented:

- **Confidence reporting**: `tempo_confidence`, `beat_confidence`, `detected_beat_count`, and `expected_beat_count` are reported in analysis output.
- **Click-track verification**: `--render-click` writes `click.wav` and `source-with-click.wav`.
- **Manual grid-start and downbeat controls**: `--grid-start` and `--downbeat-start` override auto-detection.
- **Pickup-adaptive diagnostics**: duration fit (`clean`, `small_tail`, `extra_beat`, `partial_bar`) helps identify pickup and alignment issues.

## High-Risk Areas For Refactoring

- Downbeat/grid-start logic is embedded in `analyze_audio()` and needs a clearer timing-analysis layer.
- Source feature extraction and loop-fit diagnostics currently live in the same module.
- `AudioAnalysis` is growing and may need nested typed structures as analysis maps expand.
- Generation mixes style grammar, source response, phrase behavior, random selection, and humanization in one function.
- There is no central pattern validation stage before export.

## Development History

The 12 development phases following this baseline document implemented: timing confidence reporting, manual grid/downbeat controls, click-track renders, variant generation, phrase awareness, groove templates, preview workflow (comparison, preview-bars), reproducibility metadata, and comprehensive documentation. See [ROADMAP.md](ROADMAP.md) for version history.
