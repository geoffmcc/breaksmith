# Output Formats

Breaksmith writes three primary output formats (MIDI, JSON, Strudel) plus optional rendered audio previews. All outputs are written to `output/<style>/` (or `output/<style>/variant_N/` when `--variants > 1`).

## Output Directory Structure

```
output/
├── analysis.json                          # Full audio analysis (from analyze step)
├── comparison.wav                         # Concatenated preview of all styles (with --preview-comparison)
├── minimal/
│   ├── pattern.json                       # Full drum pattern
│   ├── pattern.mid                        # Multi-track MIDI (Type 1)
│   ├── pattern.strudel.js                 # Strudel-compatible pattern
│   └── pattern-preview.wav                # Rendered audio preview (with --preview)
├── rolling/
│   ├── pattern.json
│   ├── pattern.mid
│   ├── pattern.strudel.js
│   └── pattern-preview.wav
└── liquid/
    └── variant_0/                         # (only with --variants 3)
        ├── pattern.json
        ├── pattern.mid
        ├── pattern.strudel.js
        └── pattern-preview.wav
```

## MIDI (`pattern.mid`)

- **Format**: Standard MIDI File Type 1 (multi-track)
- **Tracks**: one track per instrument (5 tracks)
- **Tempo**: set to detected or user-specified BPM
- **Time signature**: set from the analysis meter (default 4/4; changes to 3/4 or 6/8 when `--time-signature` is used)
- **Note mapping**:

| Track | MIDI Note | Drum |
|---|---|---|
| 0 | 36 (C2) | Kick |
| 1 | 38 (D2) | Snare |
| 2 | 42 (F#2) | Closed hi-hat |
| 3 | 46 (A#2) | Open hi-hat |
| 4 | 37 (C#2) | Percussion |

This is the General MIDI drum map subset. Most DAWs and drum machines recognize these note numbers.

- **Velocity**: 1–127, scaled by the selected velocity curve (`linear`, `exponential`, `compressed`, `hard`)
- **Tick-level microtiming**: swing, groove, and humanize offsets are baked into note-on positions at 480 PPQ resolution
- **Note length**: fixed at 1 tick (trigger-style — release is immediate, as is standard for drum maps)

### DAW Workflow

1. Drag `pattern.mid` into a DAW track.
2. The multi-track structure separates each instrument onto its own lane/channel.
3. Map a drum rack or sampler to the GM note numbers above.
4. Replace sounds in the drum rack — velocity and timing are preserved.

## JSON (`pattern.json`)

```json
{
  "metadata": {
    "source": "/path/to/source.wav",
    "source_sha256": "abc123...",
    "pattern_sha256": "def456...",
    "bpm": 172.0,
    "bars": 8,
    "steps_per_bar": 16,
    "genre": "dnb",
    "style": "liquid",
    "seed": 42,
    "controls": {
      "density": 0.5,
      "variation": 0.25,
      "swing": 0.0,
      "humanize": 0.0,
      "source_restraint": 0.0,
      "phrase_awareness": 0.3,
      "groove": "straight",
      "kick_density": 1.0,
      "snare_density": 1.0,
      "hat_density": 1.0,
      "open_hat_density": 1.0,
      "percussion_density": 1.0,
      "midi_velocity_curve": "linear"
    },
    "input_manifest": {
      "source_sha256": "abc123...",
      "generator_version": "0.1.0",
      "seed": 42,
      "style": "liquid",
      "genre": "dnb",
      "bars": 8,
      "controls": { ... }
    },
    "generated_at": "2026-07-08T12:00:00"
  },
  "bars": [
    {
      "index": 0,
      "is_fill": false,
      "hits": {
        "kick": [
          { "step": 0, "velocity": 110, "timing_offset": 0.0, "accent": true },
          { "step": 8, "velocity": 95, "timing_offset": 0.0, "accent": true }
        ],
        "snare": [
          { "step": 4, "velocity": 100, "timing_offset": 0.0, "accent": true },
          { "step": 12, "velocity": 85, "timing_offset": 0.005, "accent": false }
        ],
        "hat": [
          { "step": 0, "velocity": 80, "timing_offset": 0.0, "accent": false },
          { "step": 2, "velocity": 65, "timing_offset": 0.003, "accent": false }
        ],
        "open_hat": [...],
        "percussion": [...]
      },
      "bar_energy": 0.72,
      "density_multiplier": 1.0
    }
  ],
  "format_version": "1.0"
}
```

### Schema

- **`metadata`**: source file info, generation controls, SHAs for reproducibility
  - `source_sha256`: SHA256 of the source audio file
  - `pattern_sha256`: SHA256 of the JSON-serialized pattern (excluding metadata)
  - `input_manifest`: full reproduction context (source SHA, version, seed, style, genre, bars, controls)
- **`bars[]`**: array of bar objects
  - `index`: bar number (0-based)
  - `is_fill`: whether this bar is a fill
  - `hits`: per-instrument arrays of hit objects
  - `bar_energy`: normalized energy of this bar in the source
  - `density_multiplier`: actual density multiplier applied after restraint
- **`hits[].step`**: step within the bar (0 to steps_per_bar-1)
- **`hits[].velocity`**: MIDI velocity (1–127)
- **`hits[].timing_offset`**: timing offset in seconds from the exact grid position (positive = late, negative = early)
- **`hits[].accent`**: whether this hit is musically accented

### Output Shape

The `write_pattern()` function uses a fixed output shape that groups hits by instrument within each bar, not by step. This mirrors how drum patterns are conceptually organized.

## Strudel (`pattern.strudel.js`)

```javascript
// Breaksmith generated pattern
// Source: source.wav
// BPM: 172.0
// Genre: dnb, Style: liquid
// Seed: 42
// Timing offsets not reflected in Strudel notation

// Bars 0-3
// Bar 0
samples({
  bd: "x... x... x... x...",
  sd: ".... x... .... x..x",
  hh: "x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x",
  oh: ".... .... .... ....",
  rim: "x... .... x... ...."
})
// Bar 1
samples({
  bd: "x... .... x... x...",
  sd: ".... x... .... x...",
  hh: "x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x",
  oh: ".... .... x... ....",
  rim: ".... x... .... ...."
})
```

- Uses Strudel's `samples{}` notation with default sounds: `bd` (kick), `sd` (snare), `hh` (closed hat), `oh` (open hat), `rim` (percussion)
- Each bar is rendered as a separate `samples{}` block
- `x` = hit, `.` = rest
- Strudel's `samples{}` function can be replaced with `stack()` for per-track editing
- Open hats are noted on a separate line but use `samples` type `oh` which typically maps to an open hat sample
- Timing offsets (swing, humanize, groove) are documented in a header comment but not applied to the Strudel notation, since Strudel has its own timing model
- Groups of 4 bars are commented with "Bars N-M" headings

### Strudel Workflow

1. Open `pattern.strudel.js` in a text editor.
2. Copy the contents and paste into the [Strudel REPL](https://strudel.tidalcycles.org/).
3. The pattern plays immediately with default samples.
4. Edit the `x`/`.` strings to modify the pattern rhythmically.
5. Replace the sample map to use custom samples:
   ```javascript
   samples({ bd: "path/to/kick.wav", sd: "path/to/snare.wav", ... })
   ```

## Preview Audio (`pattern-preview.wav`)

- **Format**: WAV (44.1 kHz, mono, 16-bit)
- **Synth**: each instrument is a simple synthesized tone:
  - Kick: low sine wave (60 Hz, 0.25s)
  - Snare: noise burst (0.25s)
  - Closed hat: high sine (8000 Hz, 0.25s)
  - Open hat: high sine + noise (4000 Hz, 0.25s)
  - Percussion: mid sine (200 Hz, 0.25s)
- **Purpose**: groove audition, not mix reference. The preview confirms timing and density. Replace sounds in your DAW for production.

### Preview Modes

| Mode | Description |
|---|---|
| `--preview` | Renders 1 WAV per style (or variant) |
| `--preview-bars N` | Renders only the first N bars (shorter audition) |
| `--preview-comparison` | Concatenates all style previews into one file at `output/comparison.wav` |

When both `--preview` and `--preview-comparison` are used, individual previews and the comparison file are all written.

## Analysis JSON (`analysis.json`)

Generated during the analyze step (and re-run during generate for fresh analysis data). Contains:

- **Tempo** (`bpm`): detected or user-specified
- **Tempo confidence** (`tempo_confidence`): 0.0–1.0, reliability of BPM detection
- **Beat confidence** (`beat_confidence`): 0.0–1.0, how many beats were detected vs. expected
- **Beat count** (`beat_count`): number of detected beat positions
- **Grid start** (`grid_start`): detected or manual grid start in seconds
- **Downbeat start** (`downbeat_start`): detected or manual downbeat in seconds
- **Source duration** (`source_duration_seconds`)
- **Steps per bar** (`steps_per_bar`)
- **Number of bars** (`num_bars`)
- **Duration fit** (`duration_fit`): `clean`, `small_tail`, `extra_beat`, or `partial_bar`
- **Duration fit details**: reason for the fit classification
- **Meter** (`meter`): time signature object with numerator, denominator, beat_groups, tempo_unit, primary_beats_per_bar, pulses_per_bar, steps_per_bar
- **File properties**: path, extension, format
- **Feature maps**: step-level arrays for onset, low, high, energy, silence, brightness, sustain, flux
- **Beat positions**: list of detected beat times in seconds

## Output Shape

The Python `OutputShape` is a dict grouping hits by instrument per bar:

```python
{
    "kick": [(bar, step, velocity, timing_offset, accent), ...],
    "snare": [...],
    "hat": [...],
    "open_hat": [...],
    "percussion": [...]
}
```

This is the internal representation used by all exporters. It preserves the logical grid structure while allowing per-instrument per-bar iteration.
