# Breaksmith

Breaksmith is an audio-aware breakbeat and drum-and-bass groove generator. It analyzes loops or tracks and generates editable drum arrangements as MIDI, Strudel, and JSON.

The current system is rule-based and audio-aware: it estimates tempo, builds a beat grid, measures low/high/onset activity, and uses those features to guide drum pattern generation. Prompt-directed or model-assisted generation is a future direction, not part of the current implementation.

## Requirements

- Python 3.12 recommended; Python 3.11 is also supported
- `uv`
- FFmpeg available on `PATH` for formats such as MP3/M4A

## Install

```bash
uv python install 3.12
uv sync --python 3.12
```

Breaksmith supports Python 3.11 and 3.12. New installs should use Python 3.12 unless you need 3.11 for compatibility with an existing environment.

## Commands

Analyze an audio file:

```bash
uv run breaksmith analyze path/to/loop.wav
```

Generate all styles:

```bash
uv run breaksmith generate path/to/loop.wav
```

Generate one style with explicit controls:

```bash
uv run breaksmith generate input.wav \
  --style rolling \
  --bars 8 \
  --density 0.65 \
  --swing 0.12 \
  --humanize 0.08 \
  --variation 0.40 \
  --seed 42
```

Override a bad tempo estimate:

```bash
uv run breaksmith generate path/to/loop.wav --bpm 172
```

Choose an output directory:

```bash
uv run breaksmith generate path/to/loop.wav --output output/my-loop
```

## Styles

- `minimal`: sparse, clean, restrained, with strong space between hits.
- `rolling`: continuous forward movement, syncopated kicks, active hats, restrained ghost snares.
- `aggressive`: higher density, stronger accents, more fills, more forceful velocity.
- `liquid`: smooth, musical, controlled hats, subtle ghost notes, softer fills.
- `jungle`: breakbeat-like syncopation, busier snares, shuffled percussion, stronger variation.
- `halfstep`: half-time weight, large spaces, heavy kick and snare emphasis, sparse hats.
- `techstep`: dark, mechanical, tight, syncopated, controlled repetition, sharper accents.

Use `--style all` to generate every style, or select one style with `--style rolling`.

## Generation Controls

- `--bars`: generated bar count; must be a positive integer.
- `--density`: overall hit density, `0.0` to `1.0`.
- `--swing`: additional off-grid swing delay, `0.0` to `0.5` steps.
- `--humanize`: random timing and velocity looseness, `0.0` to `1.0`.
- `--variation`: random and bar-to-bar variation, `0.0` to `1.0`.
- `--seed`: deterministic random seed.
- `--bpm`: tempo override.
- `--steps-per-bar`: grid resolution; must be a positive multiple of four.

The same audio analysis, style, controls, and seed should produce deterministic output.

## Output

```text
output/
├── analysis.json
├── minimal/
│   ├── pattern.json
│   ├── pattern.mid
│   └── pattern.strudel.js
├── rolling/
├── aggressive/
├── liquid/
├── jungle/
├── halfstep/
└── techstep/
```

JSON preserves the logical grid and includes per-hit `timing_offset_steps` when swing or humanization is applied. MIDI renders those timing offsets as tick offsets while keeping events ordered. Strudel output keeps the pattern readable on the logical grid and documents the timing controls in comments rather than emitting complex timing transforms.

## Ableton Workflow

Import a generated `pattern.mid` file into Ableton Live, assign drum sounds to the General MIDI drum notes, and edit the notes normally. Breaksmith writes separate MIDI tracks for kick, snare, closed hat, open hat, and percussion.

## Strudel Workflow

Open `pattern.strudel.js` in Strudel or paste it into the Strudel editor. The export uses default Strudel sound names: `bd`, `sd`, `hh`, `oh`, and `rim`.

## Current Limitations

- Assumes 4/4 time.
- Works best with steady-tempo loops and rough tracks.
- Downbeat detection is intentionally simple.
- Strudel timing output is intentionally grid-readable; detailed swing/humanization is represented in JSON and MIDI.
- Breaksmith generates MIDI, Strudel, and JSON, but does not render audio previews yet.
- It does not include stem separation, chord recognition, model training, or natural-language generation yet.

## Project Direction

Near-term work is focused on making Breaksmith a reliable local music tool with strong generator controls, useful style presets, and testable exports. Future directions include rendered audio previews, user-supplied drum kits, Ableton/MPC-oriented exports, section-aware arrangements, style preset files, prompt-directed parameter control, and a local GUI or web interface.

## Run Tests

```bash
uv run pytest
uv run ruff check .
```
