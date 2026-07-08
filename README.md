# Breaksmith

Breaksmith is an audio-aware breakbeat, drum-and-bass, and hip-hop groove generator. It analyzes loops or tracks and generates editable drum arrangements as MIDI, Strudel, and JSON.

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

Render a timing diagnostic click track while analyzing:

```bash
uv run breaksmith analyze path/to/loop.wav --bpm 172 --render-click
```

This writes `analysis-click.wav` and `source-with-click.wav` next to the analysis JSON so you can hear whether the grid and bar starts line up with the source. Use `--grid-start` or `--downbeat-start` when the automatic start point needs manual correction:

```bash
uv run breaksmith analyze path/to/loop.wav --bpm 172 --grid-start 0.125 --render-click
```

Export step-level source activity maps as CSV:

```bash
uv run breaksmith analyze path/to/loop.wav --bpm 172 --features-csv analysis-features.csv
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

Use the same manual grid start during generation:

```bash
uv run breaksmith generate path/to/loop.wav --bpm 172 --grid-start 0.125 --bars 8
```

Choose an output directory:

```bash
uv run breaksmith generate path/to/loop.wav --output output/my-loop
```

Generate with an arrangement preset and audio preview:

```bash
uv run breaksmith generate path/to/loop.wav --structure build-drop --preview
```

Select a genre for style-specific defaults:

```bash
uv run breaksmith generate input.wav --genre dnb --style liquid
uv run breaksmith generate input.wav --genre hiphop --style boom_bap
```

Generate multiple variants for comparison:

```bash
uv run breaksmith generate input.wav --style rolling --variants 3 --preview-comparison
```

Use a groove template for consistent feel:

```bash
uv run breaksmith generate input.wav --style liquid --groove mpc --swing 0.0
```

Generate a shorter audio preview for faster iteration:

```bash
uv run breaksmith generate input.wav --style rolling --preview --preview-bars 4
```

All output directories include `source_sha256`, `pattern_sha256`, and a full `input_manifest` in the pattern metadata for full reproducibility.

## Styles

### Drum & Bass

- `minimal`: sparse, clean, restrained, with strong space between hits.
- `rolling`: continuous forward movement, syncopated kicks, active hats, restrained ghost snares.
- `aggressive`: higher density, stronger accents, more fills, more forceful velocity.
- `liquid`: smooth, musical, controlled hats, subtle ghost notes, softer fills.
- `jungle`: breakbeat-like syncopation, busier snares, shuffled percussion, stronger variation.
- `halfstep`: half-time weight, large spaces, heavy kick and snare emphasis, sparse hats.
- `techstep`: dark, mechanical, tight, syncopated, controlled repetition, sharper accents.

### Hip-Hop

- `boom_bap`: classic hip-hop with strong kick/snare relationship and snare on 2 and 4.
- `lo_fi`: softer, swung hip-hop with loose timing and restraint.
- `dusty`: hard but imperfect pocket with moderate swing and character.
- `soulful`: smooth pocket with supportive dynamics and gentle phrase changes.
- `laid_back`: minimal, spacious hip-hop with late snares and strong pocket.
- `east_coast`: firmer boom-bap attack with tighter swing and strong snare.
- `sparse`: very few events with strong anchors and large spaces.

Use `--style all` to generate every style for the detected or specified genre.

## Generation Controls

- `--bars`: generated bar count; must be a positive integer.
- `--density`: overall hit density, `0.0` to `1.0` (genre-dependent default).
- `--swing`: additional off-grid swing delay, `0.0` to `0.5` steps (genre-dependent default).
- `--humanize`: random timing and velocity looseness, `0.0` to `1.0` (genre-dependent default).
- `--variation`: random and bar-to-bar variation, `0.0` to `1.0` (genre-dependent default).
- `--seed`: deterministic random seed.
- `--bpm`: tempo override.
- `--grid-start`: manual grid start in seconds.
- `--downbeat-start`: manual first downbeat in seconds; overrides `--grid-start`.
- `--steps-per-bar`: grid resolution; must be a positive multiple of four.
- `--features-csv`: write step-level source activity maps for diagnostics.
- `--preview`: render a WAV audio preview of each generated pattern (requires FFmpeg).
- `--preview-bars`: bar count for the audio preview (defaults to full pattern; shorter = faster).
- `--preview-comparison`: generate a single WAV with all style previews concatenated for A/B comparison.
- `--structure`: section arrangement preset (`short`, `build-drop`, `minimal`).
- `--midi-velocity-curve`: velocity mapping curve (`linear`, `exponential`, `compressed`, or `hard`).

### Genre & Style

- `--genre`: genre context (`dnb` or `hiphop`); sets style-specific defaults for density, swing, humanize, variation, and source restraint.
- `--style`: drum style name or `all` to generate every style for the genre.

### Advanced Controls

- `--source-restraint`: modulate density by source bar energy, `0.0` to `1.0` (0 = ignore source, 1 = fully follow source). Hip-hop defaults to 0.3.
- `--phrase-awareness`: how strongly phrase position modulates density, `0.0` to `1.0` (default 0.3). Bars near phrase boundaries get subtle density and variation shifts.
- `--groove`: structured timing template (`straight`, `mpc`, `laid_back`, `pushed`, `shuffled`). Adds consistent per-step timing offsets on top of swing and humanization.
- `--variants`: number of variant patterns to generate (default 1). Each variant uses `seed + variant_index` and writes to a `variant_N` subdirectory.

### Per-Layer Density

- `--kick-density`: density multiplier for kicks, `0.0` to `1.0`.
- `--snare-density`: density multiplier for snares, `0.0` to `1.0`.
- `--hat-density`: density multiplier for closed hats, `0.0` to `1.0`.
- `--open-hat-density`: density multiplier for open hats, `0.0` to `1.0`.
- `--percussion-density`: density multiplier for percussion, `0.0` to `1.0`.

The same audio analysis, style, controls, and seed should produce deterministic output. Each pattern JSON includes `source_sha256`, `pattern_sha256`, and `input_manifest` for reproducibility verification.

## Output

```text
output/
├── analysis.json
├── minimal/
│   ├── pattern.json
│   ├── pattern.mid
│   ├── pattern.strudel.js
│   └── pattern-preview.wav       # with --preview
├── rolling/
├── aggressive/
├── ...
├── comparison.wav                  # with --preview-comparison
└── rolling/
    └── variant_0/                  # with --variants 3
        ├── pattern.json
        ├── pattern.mid
        └── pattern.strudel.js
```

JSON preserves the logical grid and includes per-hit `timing_offset_steps` when swing or humanization is applied. MIDI renders those timing offsets as tick offsets while keeping events ordered; it also writes per-instrument note lengths, note-off release velocities, groove feel markers, and section markers. Strudel output keeps the pattern readable on the logical grid and documents the timing controls in comments rather than emitting complex timing transforms.

When `--structure` is used, the output pattern contains a `section` metadata field and an `arrangement` field in JSON. MIDI exports include section marker events for DAW navigation.

## Ableton Workflow

Import a generated `pattern.mid` file into Ableton Live, assign drum sounds to the General MIDI drum notes, and edit the notes normally. Breaksmith writes separate MIDI tracks for kick, snare, closed hat, open hat, and percussion.

## Strudel Workflow

Open `pattern.strudel.js` in Strudel or paste it into the Strudel editor. The export uses default Strudel sound names: `bd`, `sd`, `hh`, `oh`, and `rim`.

## Current Limitations

- Assumes 4/4 time.
- Works best with steady-tempo loops and rough tracks.
- Downbeat detection is intentionally simple.
- Strudel timing output is intentionally grid-readable; detailed swing/humanization is represented in JSON and MIDI.
- Breaksmith generates MIDI, Strudel, and JSON, and can render WAV audio previews with `--preview`.
- It does not include stem separation, chord recognition, model training, or natural-language generation yet.

## Project Direction

Near-term work is focused on making Breaksmith a reliable local music tool with strong generator controls, useful style presets, and testable exports. Future directions include user-supplied drum kits, Ableton/MPC-oriented exports, style preset files, prompt-directed parameter control, and a local GUI or web interface.

## Run Tests

```bash
uv run pytest
uv run ruff check .
```
