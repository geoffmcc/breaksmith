# Musical Model

Breaksmith is a rule-based drum pattern generator. It does not use machine learning or template matching. Every note is placed by combining:

1. **Genre grammar** — basic rhythmic structure (note stride, bar grid, swing defaults)
2. **Style presets** — instrument-level density, syncopation, fill probability, velocity ranges
3. **Source features** — onset, low, high, and energy activity extracted from the audio
4. **Stochastic scoring** — each step gets a hit probability per instrument, modulated by controls
5. **Deterministic RNG** — same inputs always produce the same output

## Genre Grammar

Each genre defines the fundamental rhythmic grid and step resolution.

### Drum & Bass (`GENRE_CONTROL_DEFAULTS["dnb"]`)

- **Step stride**: 16th notes (4 steps per beat, 16 per bar)
- **Hat stride**: 16th notes (closed hats run at 16th-note resolution by default)
- **Default density**: 0.5
- **Default swing**: 0.0 (DnB is generally straight)
- **Default humanize**: 0.0
- **Default variation**: 0.25
- **Default source restraint**: 0.0
- **Bar grid**: `[[0,1,2,3],[4,5,6,7],[8,9,10,11],[12,13,14,15]]` (4 beats, 4 steps per beat)

The DnB grammar has no inherent swing — all swing comes from the style preset's `swing_amount` or the `--swing` CLI option.

### Hip-Hop (`GENRE_CONTROL_DEFAULTS["hiphop"]`)

- **Step stride**: 8th notes (2 steps per beat, 8 per bar)
- **Hat stride**: 8th notes (closed hats run at 8th-note resolution by default)
- **Default density**: 0.35
- **Default swing**: 0.12
- **Default humanize**: 0.15
- **Default variation**: 0.30
- **Default source restraint**: 0.3
- **Bar grid**: `[[0,1],[2,3],[4,5],[6,7]]` (4 beats, 2 steps per beat)

The hip-hop grammar has built-in swing to reflect the genre's natural feel. Swing delays even-numbered steps (the "off" beats).

## Style Presets

Each style defines a `StylePreset` dataclass instance within a genre's preset dict. A style preset controls these parameters:

### `base_density` (float, 0.0–1.0)
Base density for each instrument. Actual density is `base_density × master_density × layer_multiplier`.

### `syncopation` (float, 0.0–1.0)
Probability that a kick or snare lands on an off-beat step rather than a main beat step.

### `fill_frequency` (float, 0.0–1.0)
Probability that a bar contains a fill. Fills add extra hits in pattern on a fill bar.

### `kick_pattern`
List of preferred bar positions for kicks (0-indexed step positions within a bar). The generator weights these positions higher.

### `velocity_range` (tuple of 2 ints, 1–127)
Min and max MIDI velocity for the instrument. Velocities are distributed within this range based on the instrument's role and accent status.

### `swing_amount` (float, 0.0–1.0)
Built-in swing for the style. Each style has its own swing feel, independent of the genre default. The `--swing` CLI option adds on top of this.

## Generation Pipeline

```
source audio → analysis → feature maps
                              ↓
controls + genre grammar → grid setup (step stride, bar count)
                              ↓
style preset → per-bar instrument probabilities
                              ↓
    source restraint → bar energy modulation of density
                              ↓
    phrase awareness → phrase position modulation of density/fills
                              ↓
    stochastic scoring → kick, snare, hat, open hat, percussion per step
                              ↓
    swing + humanize + groove → timing offsets per hit
                              ↓
velocity assignment → accent / ghost note logic
                              ↓
    pattern → MIDI export     pattern → JSON export
    pattern → Strudel export  pattern → WAV preview
```

### Step 1: Audio Analysis

Librosa extracts onset strength, spectral features, and beat tracking. The output is a dictionary of feature arrays, one value per grid step. See [`source-activity-maps.md`](source-activity-maps.md).

### Step 2: Grid Setup

The genre grammar defines the step resolution and bar structure. Bar count is either source-matched or user-specified. Variants add a seed offset for each copy.

### Step 3: Style Application

For each bar, the style preset provides base probabilities for each instrument. The master `--density` scales these.

### Step 4: Source Restraint

When `--source-restraint > 0`, the per-bar energy of the source modulates the density multiplier for that bar. Low-energy bars get lower density; high-energy bars can go up to the full density.

### Step 5: Phrase Awareness

When `--phrase-awareness > 0`, each 4-bar phrase gets a modulation arc:
- **Bar 0** (phrase start): lowest density, fewest fills, fewest open hats
- **Bar 1**: slightly higher density, more variation
- **Bar 2**: more fills, higher open-hat probability
- **Bar 3** (phrase end): most fills, most open hats, most variation

The arc strength is scaled by `phrase-awareness`. At 0.0, no phrase modulation occurs.

### Step 6: Hit Scoring

For each step in each bar, the generator scores each instrument independently:

**Kick scoring** considers:
- Style `base_density["kick"]` × global density × per-bar restraint factor
- Whether the step is a main beat or off-beat (syncopation weight)
- Source onset activity at this step (higher onset → more likely)
- Source low activity at this step (higher low energy → more likely)
- Variation noise from RNG

**Snare scoring** considers:
- Style `base_density["snare"]` × global density × per-bar restraint factor
- Source onset activity (high onset → more likely to be a snare position)
- Whether the step is a typical snare position (beat 2 and 4 for 4-on-the-floor styles)
- Syncopation weight
- Variation noise from RNG

**Closed hat scoring** considers:
- Style `base_density["hat"]` × global density × per-bar restraint factor
- Hat stride (all steps for DnB, every other step for hip-hop)
- Source high activity (higher high energy → more likely)
- Minimum hat density ensures no bar is completely silent on hats

**Open hat scoring** considers:
- Style `base_density["open_hat"]` × global density × per-bar restraint factor
- Source high activity
- Phrase position (more open hats at the end of phrases)
- Open hats cannot overlap with closed hats at the same step

**Percussion scoring** considers:
- Style `base_density["percussion"]` × global density × per-bar restraint factor
- Source activity patterns
- Percussion is the most varied layer

### Step 7: Fills

On bars where the fill check passes (controlled by style `fill_frequency` × bar energy), additional hits are injected:
- Extra kicks on non-standard positions
- Additional snares/ghost notes
- Extra closed hats on steps that would normally be silent
- Percussion flurries

Fill density is inversely proportional to the current bar's density — sparse bars get more dramatic fills.

### Step 8: Timing Offsets

Each hit gets three layers of timing adjustment:

1. **Swing**: style `swing_amount` + CLI `--swing`. Applied to even-numbered steps within each beat. The delay is `step_duration × swing_amount`.

2. **Groove**: per-step offsets from the chosen groove template (`straight`, `mpc`, `laid_back`, `pushed`, `shuffled`). Offsets are fractions of a step duration.

3. **Humanize**: random jitter of up to `±0.08 × step_duration × humanize_amount`. Applied to every hit independently.

All offsets are stored in the `Pattern` as `timing_offset` values in seconds, and are written to the JSON and MIDI exports.

### Step 9: Velocity Assignment

Each instrument has a `velocity_range` from its style preset. Velocities are distributed:

- **Kick strong** (main beats): high end of range
- **Fill kicks**: mid-range
- **Snare main**: high end of range
- **Ghost snares**: low end of range
- **Closed hats**: range midpoint ± random fluctuation
- **Open hats**: high end of range
- **Percussion**: scattered across range

The velocity curve (`--midi-velocity-curve`) remaps these values:
- `linear`: no change
- `exponential`: `velocity² / 127` (quieter notes get quieter, louder notes punch harder)
- `compressed`: narrows range by 30%
- `hard`: every hit → 127

Humanize adds ±10 velocity units (within 1–127 bounds).

### Step 10: Export

The `Pattern` object is a list of hits (step, bar, instrument, velocity, timing_offset). It is written to:
- **MIDI**: Type 1 multi-track file, one track per instrument, notes at the bar+step position.
- **JSON**: Logical grid with per-instrument arrays, timing offsets in seconds.
- **Strudel**: Readable mini-notation strings grouped by bar.
- **Preview**: Synthesized audio using a simple tone-per-instrument synth (5 instruments, 0.25s duration).

## Genre Grammar Internals

### `GenreGrammar`

```python
@dataclass
class GenreGrammar:
    phrase_length: int = 4       # bars per phrase
    stride: int = 16             # steps per bar (default 16th notes)
    hat_stride: int = 16         # hat resolution steps per bar
    bar_grid: list[list[int]] = None  # beat groupings within a bar
    default_swing: float = 0.0   # genre-level swing
```

DnB: `stride=16, hat_stride=16`
Hip-hop: `stride=8, hat_stride=8`

### `GenerationControls`

```python
@dataclass
class GenerationControls:
    bars: int = 8
    density: float = 0.5
    variation: float = 0.25
    swing: float = 0.0
    humanize: float = 0.0
    fill_frequency: float = 0.15
    seed: int = 42
    source_restraint: float = 0.0
    phrase_awareness: float = 0.3
    groove: str = "straight"
    structure: str | None = None
    kick_density: float = 1.0
    snare_density: float = 1.0
    hat_density: float = 1.0
    open_hat_density: float = 1.0
    percussion_density: float = 1.0
    midi_velocity_curve: str = "linear"
```

### `GrooveTemplate`

```python
@dataclass
class GrooveTemplate:
    name: str
    offsets: list[float]  # 32 offsets for 2-bar groove cycle
```

Five presets: `straight`, `mpc`, `laid_back`, `pushed`, `shuffled`.

## Determinism Guarantee

All random numbers flow through a single `random.Random` instance seeded with the provided seed. The generation pipeline uses no external randomness (no system time, no hash collisions). For a given source file, style, seed, and controls:

- Same pattern (same steps, same instruments, same velocities, same timing offsets)
- Same exported files (bit-identical JSON and MIDI)
- Same preview WAV

Varying the seed produces a different but equally valid pattern within the same density/structure constraints.
