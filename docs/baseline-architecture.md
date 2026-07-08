# Breaksmith Baseline Architecture

This report captures the current Breaksmith architecture and musical baseline before the larger music-engine roadmap begins.

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

Limitations:

- There are no low-mid, mid, brightness, flux, sustain, silence, or local-density maps yet.
- Feature meaning and musical intent are not yet documented in machine-readable form.
- Per-bar summaries are minimal.
- Extreme-event robustness exists through percentile normalization but needs more targeted tests.

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

Musical limitations:

- Styles are more than raw probabilities, but they are not yet full grammars or template systems.
- Drum decisions are still mostly local step decisions rather than phrase-aware event scoring.
- Generated hits do not carry provenance, confidence, lock state, duration, or stable IDs.

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

- MIDI does not yet provide separate files per instrument or configurable mappings.
- Strudel does not represent detailed swing/humanization beyond comments.
- Export validation is covered by tests but not centralized as a pattern validation stage.

## Current CLI Baseline

Commands:

- `breaksmith analyze AUDIO`
- `breaksmith generate AUDIO`

Important options:

- `--bpm`
- `--steps-per-bar`
- `--output`
- `--style`
- `--seed`
- `--bars`
- `--density`
- `--swing`
- `--humanize`
- `--variation`

CLI limitations:

- No `render`, `revise`, `inspect`, or kit commands yet.
- There is no cache for analysis within repeated workflows.

## Baseline Smoke Test

Using `/mnt/c/Users/geoff/Music/test.wav` with `--bpm 172`:

```text
Duration: 11.16s
Grid fit: clean 8-bar loop
Detected output grid: 8 bars
```

Generating `rolling` with `--bars 8` produced an 8-bar output and reported that the requested grid aligns with the analyzed source duration.

The analyzer emitted:

```text
Warning: Few reliable beats were found; the grid begins at the audio start.
```

This is acceptable for the current sample but highlights why Phase 1 should add confidence reporting and click-render verification.

## High-Risk Areas For Refactoring

- Downbeat/grid-start logic is embedded in `analyze_audio()` and needs a clearer timing-analysis layer.
- Source feature extraction and loop-fit diagnostics currently live in the same module.
- `AudioAnalysis` is growing and may need nested typed structures as analysis maps expand.
- Generation mixes style grammar, source response, phrase behavior, random selection, and humanization in one function.
- There is no central pattern validation stage before export.

## Phase 1 Entry Criteria

The current baseline is stable enough to begin Phase 1. The next phase should focus on timing confidence, manual grid-start/downbeat controls, pickup-aware diagnostics, and click-track renders before adding more generation complexity.
