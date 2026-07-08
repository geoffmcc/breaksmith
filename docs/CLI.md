# CLI Reference

This document describes every command and option in Breaksmith. Output is deterministic for the same source file, seed, style, and controls.

## Global Invocation

```bash
uv run breaksmith <command> [options]
```

All commands require a source audio path as the first positional argument.

## `breaksmith analyze`

Analyze audio and write timing analysis to JSON.

```
usage: breaksmith analyze [-h] [--output OUTPUT] [--bpm BPM]
                          [--steps-per-bar STEPS_PER_BAR]
                          [--grid-start GRID_START]
                          [--downbeat-start DOWNBEAT_START]
                          [--render-click] [--features-csv FEATURES_CSV]
                          source
```

### Positional Arguments

| Argument | Description |
|---|---|
| `source` | Path to audio file. WAV, MP3, M4A, FLAC, OGG, and anything FFmpeg supports. |

### Options

#### `--output OUTPUT`
Path for the analysis JSON output.
- **Default**: `analysis.json`
- **Example**: `--output my-analysis.json`

#### `--bpm BPM`
Override auto-detected BPM. Use when the source has weak transients or unsteady tempo.
- **Type**: positive float
- **Example**: `--bpm 172`

#### `--steps-per-bar STEPS_PER_BAR`
Grid resolution. Must be a multiple of 4.
- **Default**: `16`
- **Example**: `--steps-per-bar 32` (32nd note grid)

#### `--grid-start GRID_START`
Manual grid start offset in seconds. Override when the auto-detected grid start is off.
- **Type**: float (seconds)
- **Example**: `--grid-start 0.125`

#### `--downbeat-start DOWNBEAT_START`
Manual downbeat offset in seconds. Override when the auto-detected downbeat is off.
- **Type**: float (seconds)
- **Example**: `--downbeat-start 0.5`

#### `--render-click`
Render diagnostic audio files:
- `source-with-click.wav` — source mixed with a steady click track at the detected/submitted BPM
- `click.wav` — the click track alone

Use these to verify that the detected grid aligns with the source.
- **Type**: flag (no value)

#### `--features-csv FEATURES_CSV`
Write step-level feature maps (onset, low, high, energy, silence, brightness, sustain, flux) as CSV. Each row is one step across the entire source duration.
- **Example**: `--features-csv features.csv`

## `breaksmith generate`

Analyze audio and generate drum patterns.

```
usage: breaksmith generate [-h] [--output-base OUTPUT_BASE]
                           [--style STYLE] [--genre GENRE]
                           [--structure STRUCTURE] [--bars BARS]
                           [--density DENSITY] [--variation VARIATION]
                           [--swing SWING] [--humanize HUMANIZE]
                           [--seed SEED] [--variants VARIANTS]
                           [--source-restraint SOURCE_RESTRAINT]
                           [--phrase-awareness PHRASE_AWARENESS]
                           [--groove GROOVE]
                           [--kick-density KICK_DENSITY]
                           [--snare-density SNARE_DENSITY]
                           [--hat-density HAT_DENSITY]
                           [--open-hat-density OPEN_HAT_DENSITY]
                           [--percussion-density PERCUSSION_DENSITY]
                           [--midi-velocity-curve MIDI_VELOCITY_CURVE]
                           [--preview] [--preview-bars PREVIEW_BARS]
                           [--preview-comparison]
                           source
```

### Positional Arguments

| Argument | Description |
|---|---|
| `source` | Path to audio file. WAV, MP3, M4A, FLAC, OGG. |

### General Options

#### `--output-base OUTPUT_BASE`
Base output directory. A subdirectory is created for each style (and each variant).
- **Default**: `output`
- **Example**: `--output-base my-beats`

#### `--style STYLE`
Generation style within the genre. Use `all` to generate all styles for the genre.
- **DnB styles**: `minimal`, `rolling`, `aggressive`, `liquid`, `jungle`, `halfstep`, `techstep`
- **Hip-hop styles**: `boom_bap`, `lo_fi`, `dusty`, `soulful`, `laid_back`, `east_coast`, `sparse`
- **Default**: `all`
- **Example**: `--style liquid`

#### `--genre GENRE`
Genre. Inferred from style if not provided (e.g., `--style liquid` implies `--genre dnb`). Required when `--style all`.
- **Values**: `dnb`, `hiphop`
- **Example**: `--genre hiphop`

#### `--structure STRUCTURE`
Arrangement structure.
- **Values**: `short`, `build-drop`, `minimal`
- **Default**: none (flat bars, no arrangement)
- **Example**: `--structure build-drop`

#### `--bars BARS`
Number of bars to generate. Must be at least 1. If not provided, matches the source length.
- **Type**: positive int
- **Example**: `--bars 8`

### Pattern Controls

#### `--density DENSITY`
Master density scaling all instrument probabilities. Genre-dependent default.
- **Range**: 0.0 (silence) to 1.0 (maximum)
- **Default**: 0.5 (DnB), 0.35 (hip-hop)
- **Example**: `--density 0.3`

#### `--variation VARIATION`
Randomness in kick scoring and instrument selection. Higher values produce more bar-to-bar variety.
- **Range**: 0.0 (fully deterministic) to 1.0 (maximum variation)
- **Default**: 0.25 (DnB), 0.30 (hip-hop)
- **Example**: `--variation 0.5`

#### `--swing SWING`
Additional off-grid delay on even-numbered steps. Added to each style's built-in `swing_amount`.
- **Range**: 0.0 (none) to 0.5 (maximum)
- **Default**: 0.0 (DnB), 0.12 (hip-hop)
- **Example**: `--swing 0.1`

#### `--humanize HUMANIZE`
Random timing jitter and velocity fluctuation.
- Timing jitter: up to ±8% of a step duration
- Velocity fluctuation: up to ±10 MIDI velocity units
- **Range**: 0.0 (none) to 1.0 (maximum)
- **Default**: 0.0 (DnB), 0.15 (hip-hop)
- **Example**: `--humanize 0.2`

#### `--seed SEED`
Deterministic RNG seed. Same source, seed, style, and controls always produce the same pattern.
- **Type**: int
- **Default**: `42`
- **Example**: `--seed 99`

#### `--variants VARIANTS`
Generate multiple variant patterns, each with a different seed offset. Each variant is written to a `variant_N/` subdirectory within the style directory.
- **Type**: positive int
- **Default**: `1`
- **Example**: `--variants 3` (produces `variant_0/`, `variant_1/`, `variant_2/`)

#### `--source-restraint SOURCE_RESTRAINT`
How strongly the source's per-bar energy modulates density. Higher values make quiet source bars produce sparser drums.
- **Range**: 0.0 (ignored) to 1.0 (follows energy closely)
- **Default**: 0.0 (DnB), 0.3 (hip-hop)
- **Example**: `--source-restraint 0.5`

#### `--phrase-awareness PHRASE_AWARENESS`
4-bar phrase modulation. Bars near phrase start are more restrained; bars near phrase end have more fills, open hats, and variation.
- **Range**: 0.0 (disabled) to 1.0 (strong arc)
- **Default**: `0.3`
- **Example**: `--phrase-awareness 0.0`

#### `--groove GROOVE`
Per-step timing offset template applied to all hits (on top of swing and humanization).
- **Values**: `straight`, `mpc`, `laid_back`, `pushed`, `shuffled`
- **Default**: `straight`
- **Example**: `--groove mpc`

Groove template offsets (steps within a bar):

| Bar step | straight | mpc | laid_back | pushed | shuffled |
|---|---|---|---|---|---|
| 0 (downbeat) | 0 | 0 | 0 | 0 | 0 |
| 1 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 2 | 0 | 0 | 0 | 0 | 0 |
| 3 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 4 | 0 | 0 | 0 | 0 | 0 |
| 5 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 6 | 0 | 0 | 0 | 0 | 0 |
| 7 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 8 | 0 | 0 | 0 | 0 | 0 |
| 9 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 10 | 0 | 0 | 0 | 0 | 0 |
| 11 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 12 | 0 | 0 | 0 | 0 | 0 |
| 13 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 14 | 0 | 0 | 0 | 0 | 0 |
| 15 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 16 | 0 | 0 | 0 | 0 | +0.08 |
| 17 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 18 | 0 | 0 | 0 | 0 | 0 |
| 19 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 20 | 0 | 0 | 0 | 0 | 0 |
| 21 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 22 | 0 | 0 | 0 | 0 | 0 |
| 23 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 24 | 0 | 0 | 0 | 0 | 0 |
| 25 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 26 | 0 | 0 | 0 | 0 | 0 |
| 27 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 28 | 0 | 0 | 0 | 0 | 0 |
| 29 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |
| 30 | 0 | 0 | 0 | 0 | 0 |
| 31 (off) | 0 | +0.06 | +0.08 | -0.04 | 0 |

Offsets are fractions of a step (0.0 = on grid, 0.5 = halfway to next step, -0.04 = slightly ahead).

### Per-Layer Density

These multipliers apply on top of the master `--density` value. Default 1.0 (no change).

| Option | Layer | Range |
|---|---|---|
| `--kick-density` | Kick | 0.0–1.0 |
| `--snare-density` | Snare/clap | 0.0–1.0 |
| `--hat-density` | Closed hat | 0.0–1.0 |
| `--open-hat-density` | Open hat | 0.0–1.0 |
| `--percussion-density` | Percussion | 0.0–1.0 |

Example: silence open hats and halve kick density:

```bash
--open-hat-density 0.0 --kick-density 0.5
```

### Export Options

#### `--midi-velocity-curve MIDI_VELOCITY_CURVE`
Velocity curve for MIDI velocity mapping.
- **Values**: `linear`, `exponential`, `compressed`, `hard`
- **Default**: `linear`
- **Description**:
  - `linear`: 1:1 mapping (velocity ∈ [1, 127] from style range)
  - `exponential`: lower velocities are extra quiet, louder hits punch harder
  - `compressed`: narrows the velocity range (quieter accents, reduced dynamic range)
  - `hard`: every hit near max velocity
- **Example**: `--midi-velocity-curve compressed`

#### `--preview`
Render a WAV audio preview of the generated pattern. Uses synthesized drums (5 instruments, 0.25s duration each).
- **Type**: flag (no value)

#### `--preview-bars PREVIEW_BARS`
Number of bars to render in the preview. Useful for shorter preview loops. Defaults to the pattern length.
- **Type**: positive int
- **Example**: `--preview-bars 4`

#### `--preview-comparison`
Concatenate previews of all styles (within the genre) into a single WAV file. Each style plays for its full duration in order. Combined preview written to `output/comparison.wav`.
- **Type**: flag (no value)
- **Example**: `--preview --preview-comparison` (renders individual previews + comparison)

### Full Example

```bash
uv run breaksmith generate "path/to/loop.wav" \
  --genre dnb \
  --style liquid \
  --bars 8 \
  --density 0.45 \
  --variation 0.3 \
  --swing 0.05 \
  --humanize 0.1 \
  --seed 42 \
  --variants 2 \
  --source-restraint 0.3 \
  --phrase-awareness 0.4 \
  --groove mpc \
  --kick-density 0.8 \
  --hat-density 1.2 \
  --midi-velocity-curve compressed \
  --preview \
  --preview-bars 4 \
  --preview-comparison
```

## `breaksmith --version`

Print the version number and exit.

```bash
uv run breaksmith --version
```

## `breaksmith --help`

Print the top-level help listing all subcommands.

```bash
uv run breaksmith --help
```
