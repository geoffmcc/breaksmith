# Breaksmith

Breaksmith is an audio-aware drum and groove generator. It analyzes loops or tracks and produces editable MIDI, Strudel, JSON, and rendered audio previews.

The generator is rule-based: it reads source activity (onsets, low-end, high-end, energy, silence) and uses style-specific rules to place drum hits. Every output is deterministic for the same source, seed, style, and controls.

## Why Breaksmith

- **Fast starting point**: get a structured drum arrangement from any loop in seconds.
- **Editable output**: MIDI files import directly into Ableton, Logic, or any DAW. Strudel code works in the browser. JSON preserves the logical grid with per-hit microtiming.
- **Source-aware**: patterns respond to the source's timing, density, and spectral character — they are not random or template-based.
- **Genre support**: drum-and-bass (7 styles) and hip-hop (7 styles) with distinct rhythmic grammars.
- **Iterate quickly**: generate variants, adjust density per layer, compare styles, and shorten previews for rapid audition.

## Current Capabilities

- BPM detection with user override (`--bpm`)
- Manual grid-start and downbeat alignment (`--grid-start`, `--downbeat-start`)
- Beat and tempo confidence reporting
- Loop-fit diagnostics: `clean`, `small_tail`, `extra_beat`, `partial_bar`
- Exact bar count generation (`--bars`) or automatic source-length matching
- Arrangement presets (`--structure short`, `build-drop`, `minimal`)
- Click-track rendering for grid verification (`--render-click`)
- Drum-and-bass generation: 7 styles with per-style numeric presets
- Hip-hop generation: 7 styles with per-style numeric presets
- Genre-dependent default controls (density, swing, humanize, variation, source restraint)
- Source-aware restraint: density follows source bar energy
- Phrase awareness: density, fills, and variation modulate within each 4-bar phrase
- Groove templates: `straight`, `mpc`, `laid_back`, `pushed`, `shuffled` for consistent feel
- Per-layer density multipliers (`--kick-density`, `--snare-density`, etc.)
- Multiple variants per seed (`--variants`)
- Velocity curves for MIDI export (`linear`, `exponential`, `compressed`, `hard`)
- Deterministic output (same source, seed, style, controls = same pattern)
- Reproducibility metadata (source SHA256, pattern SHA256, full input manifest)
- MIDI, JSON, Strudel, and WAV preview export
- Comparison preview across all styles (`--preview-comparison`)

## Quick Start

```bash
cd breaksmith
uv sync
```

Analyze a loop and verify the grid:

```bash
uv run breaksmith analyze path/to/loop.wav --render-click
```

Generate a liquid DnB groove with audio preview:

```bash
uv run breaksmith generate path/to/loop.wav \
  --genre dnb \
  --style liquid \
  --bars 8 \
  --preview
```

Import `output/liquid/pattern.mid` into your DAW and replace the sounds.

## Installation

### Requirements

- **Python**: 3.11 or 3.12
- **uv**: Python package and project manager ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **FFmpeg**: Required for MP3, M4A, and other compressed audio formats. Install via your package manager (Ubuntu: `sudo apt install ffmpeg`, macOS: `brew install ffmpeg`, Windows: `winget install ffmpeg`)

### Setup

```bash
uv python install 3.12
uv sync --python 3.12
```

On WSL with Windows drives (`/mnt/c/`), you may see a harmless hardlink warning. Set this to suppress it:

```bash
export UV_LINK_MODE=copy
```

### Verify

```bash
uv run breaksmith --help
uv run breaksmith analyze --help
uv run breaksmith generate --help
```

## Normal Workflow

1. **Analyze** the source audio and review the timing diagnostics.
2. **Verify the grid** by listening to `source-with-click.wav`.
3. **Correct** BPM or grid start if the click is misaligned.
4. **Generate** a genre, style, and variant that fits the source.
5. **Audition** the rendered preview or import the MIDI into your DAW.
6. **Refine** by adjusting density, per-layer controls, groove, or trying other styles.
7. **Replace** the generated sounds with your own drum kit in the DAW.

## Commands

### `breaksmith analyze`

Analyze an audio file and write a timing analysis:

```bash
uv run breaksmith analyze path/to/loop.wav
```

Options:

| Option | Description | Default |
|---|---|---|
| `--output` | Output path for analysis JSON | `analysis.json` |
| `--bpm` | Override BPM estimation | auto-detected |
| `--steps-per-bar` | Grid resolution (multiple of 4) | `16` |
| `--grid-start` | Manual grid start in seconds | detected |
| `--downbeat-start` | Manual downbeat in seconds | detected |
| `--render-click` | Render diagnostic click + source-with-click WAVs | off |
| `--features-csv` | Write step-level feature maps as CSV | off |

Examples:

```bash
uv run breaksmith analyze input.wav
uv run breaksmith analyze input.wav --bpm 172
uv run breaksmith analyze input.wav --bpm 172 --grid-start 0.125 --render-click
uv run breaksmith analyze input.wav --bpm 172 --features-csv features.csv
```

The output includes:

- **Tempo confidence**: how reliable the BPM estimate is. Low with sustained material.
- **Beat confidence**: how many beat positions were detected vs expected. Low means verify by ear.
- **Detected beat count**: number of beat positions found.
- **Grid start**: where the grid begins (detected or manual).
- **Downbeat**: first downbeat position.
- **Duration fit**: classification of the source duration:
  - `clean`: source is exactly N bars
  - `small_tail`: source has a tiny amount beyond N bars (ignored)
  - `extra_beat`: source has roughly one extra beat (common with exported loops)
  - `partial_bar`: source does not align with a whole number of bars
- **Source features**: onset, low, high, and energy activity maps.

### `breaksmith generate`

Analyze audio and generate drum patterns:

```bash
uv run breaksmith generate path/to/loop.wav
```

Options are grouped below. See [`docs/CLI.md`](docs/CLI.md) for the full reference.

**Genre and style**:

| Option | Values | Default |
|---|---|---|
| `--genre` | `dnb`, `hiphop` | inferred from style |
| `--style` | 14 style names + `all` | `all` (all styles for genre) |
| `--structure` | `short`, `build-drop`, `minimal` | none (flat bars) |

**Core controls**:

| Option | Range | Default |
|---|---|---|
| `--bars` | positive int | source bar count |
| `--density` | 0.0–1.0 | genre-dependent |
| `--variation` | 0.0–1.0 | genre-dependent |
| `--swing` | 0.0–0.5 | genre-dependent |
| `--humanize` | 0.0–1.0 | genre-dependent |
| `--seed` | int | `42` |
| `--variants` | positive int | `1` |

**Genre defaults**:

| Control | DnB default | Hip-hop default |
|---|---|---|
| `--density` | 0.5 | 0.35 |
| `--swing` | 0.0 | 0.12 |
| `--humanize` | 0.0 | 0.15 |
| `--variation` | 0.25 | 0.30 |
| `--source-restraint` | 0.0 | 0.3 |

**Advanced controls**:

| Option | Range | Default |
|---|---|---|
| `--source-restraint` | 0.0–1.0 | genre-dependent |
| `--phrase-awareness` | 0.0–1.0 | 0.3 |
| `--groove` | see below | `straight` |
| `--midi-velocity-curve` | `linear`, `exponential`, `compressed`, `hard` | `linear` |

**Per-layer density**:

| Option | Range | Default |
|---|---|---|
| `--kick-density` | 0.0–1.0 | 1.0 (no override) |
| `--snare-density` | 0.0–1.0 | 1.0 |
| `--hat-density` | 0.0–1.0 | 1.0 |
| `--open-hat-density` | 0.0–1.0 | 1.0 |
| `--percussion-density` | 0.0–1.0 | 1.0 |

**Groove templates**: `straight`, `mpc`, `laid_back`, `pushed`, `shuffled`

**Preview and workflow**:

| Option | Description |
|---|---|
| `--preview` | Render WAV audio preview |
| `--preview-bars` | Shorter preview (default: full pattern length) |
| `--preview-comparison` | Concatenate all style previews into one WAV |

**Example: balanced liquid DnB**

```bash
uv run breaksmith generate input.wav \
  --genre dnb \
  --style liquid \
  --bars 8 \
  --density 0.5 \
  --preview
```

**Example: sparse liquid DnB**

```bash
uv run breaksmith generate input.wav \
  --genre dnb \
  --style liquid \
  --bars 8 \
  --density 0.25 \
  --source-restraint 0.4 \
  --preview
```

**Example: rolling DnB**

```bash
uv run breaksmith generate input.wav \
  --genre dnb \
  --style rolling \
  --bars 16 \
  --preview
```

**Example: boom-bap hip-hop**

```bash
uv run breaksmith generate input.wav \
  --genre hiphop \
  --style boom_bap \
  --bars 8 \
  --preview
```

**Example: laid-back hip-hop**

```bash
uv run breaksmith generate input.wav \
  --genre hiphop \
  --style laid_back \
  --bars 8 \
  --groove laid_back \
  --preview
```

**Example: manual low-density override**

```bash
uv run breaksmith generate input.wav \
  --genre dnb \
  --style aggressive \
  --bars 8 \
  --density 0.3 \
  --kick-density 0.5 \
  --hat-density 0.3 \
  --preview
```

## Genres and Styles

### Drum & Bass (7 styles)

| Style | Description |
|---|---|
| `minimal` | Sparse, clean groove with strong space between hits. Wide velocity range. |
| `rolling` | Continuous forward momentum with syncopated kicks and active hats. |
| `aggressive` | High density, strong accents, frequent fills, forceful velocities. |
| `liquid` | Smooth and musical with controlled hats, subtle ghost notes, softer fills. |
| `jungle` | Breakbeat-inspired syncopation, busier snares, shuffled percussion. |
| `halfstep` | Half-time weight with large spaces, heavy kick/snare, sparse hats. Single snare position. |
| `techstep` | Dark, mechanical feel with tight syncopation and sharp accents. |

### Hip-Hop (7 styles)

| Style | Description |
|---|---|
| `boom_bap` | Classic hip-hop with strong kick/snare relationship, snare on 2 and 4. |
| `lo_fi` | Softer, swung groove with loose timing, lower velocities, and restraint. |
| `dusty` | Hard but imperfect pocket with moderate swing and character. |
| `soulful` | Smooth pocket with supportive dynamics and gentle phrase changes. |
| `laid_back` | Minimal and spacious with late snares and a relaxed pocket. |
| `east_coast` | Firmer boom-bap attack with tighter swing and a strong snare presence. |
| `sparse` | Very few events with strong anchor points and large empty spaces. |

Genre determines the rhythmic grammar: DnB has 16th-note hat stride; hip-hop has 8th-note hat stride with inherent swing. Style determines the groove vocabulary (kick density, syncopation, fill frequency, velocity ranges). There is no "sparse/balanced/active" variant system — density is controlled continuously via `--density`.

## Controls in Detail

**Density** (`--density`, 0.0–1.0): Master density that scales all instrument probabilities. Genre-dependent default. Each style has base density values per instrument that are modulated by this control and the per-layer density multipliers.

**Layer density** (`--kick-density`, `--snare-density`, `--hat-density`, `--open-hat-density`, `--percussion-density`, 0.0–1.0): Multipliers applied on top of the master density. Default 1.0 (no change). Set to 0.0 to silence a layer entirely.

**Variation** (`--variation`, 0.0–1.0): Controls how much randomness affects kick scoring and instrument selection. Higher values produce more bar-to-bar variety.

**Swing** (`--swing`, 0.0–0.5): Additional off-grid delay on even-numbered steps. Adds to each style's built-in `swing_amount`. Genre-dependent default (0.0 for DnB, 0.12 for hip-hop).

**Humanize** (`--humanize`, 0.0–1.0): Random timing jitter (±8% of a step) and velocity fluctuation (±10 MIDI velocity units). Genre-dependent default.

**Seed** (`--seed`): Deterministic RNG seed. Same source, seed, style, and controls always produce the same pattern.

**Source restraint** (`--source-restraint`, 0.0–1.0): How strongly the source's per-bar energy modulates density. At 0.0, the source energy is ignored. At 1.0, density follows source energy closely.

**Phrase awareness** (`--phrase-awareness`, 0.0–1.0, default 0.3): Each 4-bar phrase gets a subtle arc — bars near the start are more restrained, bars near the end have more fills, open hats, and variation. Set to 0.0 to disable.

**Groove** (`--groove`): Applies consistent per-step timing offsets to every hit, on top of swing and humanization.

- `straight`: no offsets (all steps on the grid)
- `mpc`: classic MPC 16-level swing (off-beat 16ths slightly late)
- `laid_back`: off-beats consistently late
- `pushed`: off-beats slightly early (driving feel)
- `shuffled`: every second 16th note pushed late (strong shuffle)

## Source-Aware Behavior

Breaksmith extracts these features from the source audio during analysis:

- **Onset activity**: transient strength at each step. Used for snare placement, ghost-note probability, and kick/hat scoring.
- **Low activity**: energy below 180 Hz. Used for kick placement decisions.
- **High activity**: energy above 3000 Hz. Used for hat and percussion density.
- **Bar energy**: average loudness per bar. Modulates density when `--source-restraint` is active.
- **Silence, brightness, sustain, spectral flux**: available in analysis JSON but not yet used by the generator.

The generator does not fill every space with drums. Hits are placed based on source activity, style preset probabilities, and variation. Quiet sections may remain sparse.

## Output Files

```
output/
├── analysis.json              # Full audio analysis dump
├── minimal/
│   ├── pattern.json           # Drum pattern (hits, velocities, microtiming)
│   ├── pattern.mid            # Multi-track MIDI (Type 1, GM drum map)
│   ├── pattern.strudel.js     # Editable Strudel pattern
│   └── pattern-preview.wav    # Rendered audio preview (with --preview)
├── rolling/
│   └── ...
├── comparison.wav             # All-style comparison (with --preview-comparison)
└── liquid/
    └── variant_0/              # (with --variants 3)
        ├── pattern.json
        └── ...
```

When `--style all` is used, all 7 styles for the genre are generated.

See [`docs/OUTPUT_FORMATS.md`](docs/OUTPUT_FORMATS.md) for detailed format descriptions.

## Ableton Workflow

1. Locate the generated MIDI file (e.g., `output/liquid/pattern.mid`).
2. Drag it from the file browser into an Ableton Live track (Session or Arrangement view).
3. The MIDI contains separate tracks for kick, snare, closed hat, open hat, and percussion.
4. Load a Drum Rack and map the GM drum notes (36=Kick, 38=Snare, 42=Closed Hat, 46=Open Hat, 37=Percussion).
5. Replace the generated sounds with your own samples by dragging them onto the Drum Rack pads.
6. Velocity values (1–127) and microtiming offsets are preserved. Adjust swing, groove, or individual note timing as needed.
7. Edit or remove fills by modifying notes in the MIDI clip.

If the rendered preview sounds good, use it as a reference. If the groove needs adjustment, tweak density, groove template, or per-layer controls and regenerate.

## Strudel Workflow

1. Open `pattern.strudel.js` in a text editor, or copy the contents.
2. Paste into the [Strudel REPL](https://strudel.tidalcycles.org/).
3. The pattern uses default Strudel sounds: `bd` (kick), `sd` (snare), `hh` (closed hat), `oh` (open hat), `rim` (percussion).
4. Edit the mini-notation strings to change the pattern — the grid is fully readable.
5. Timing offsets (swing, humanization, groove) are documented in comments but not rendered in Strudel's grid notation, since Strudel has its own timing model.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `uv: command not found` | uv not installed | Install uv (see Installation section) |
| Hardlink warning on `uv sync` | Cross-filesystem sync on WSL | `export UV_LINK_MODE=copy` |
| Wrong BPM | Source has weak transients or variable tempo | Provide `--bpm` |
| Half-time or double-time detection | Beat tracker chose wrong subdivision | Provide `--bpm` to anchor |
| Click track is off by 1/4 or 1/8 note | Grid start or downbeat is wrong | Use `--grid-start` or `--downbeat-start` |
| Low beat confidence | Sustained material (pads, strings) without clear transients | Verify timing with `--render-click` |
| Source is almost but not exactly N bars | Export artifact or loop trimming | Use `--bars` to set exact count |
| Preview sounds too busy | Density is too high for the source | Lower `--density` or raise `--source-restraint` |
| Preview ends abruptly | Preview length = pattern length | Use `--preview-bars` to extend or match |
| FFmpeg/decode error | Unsupported format or missing FFmpeg | Convert to WAV or install FFmpeg |
| Path contains spaces | Shell splitting | Quote the path: `"path/to/file.wav"` |
| Unsupported genre/style combination | Style doesn't match genre | Use matching genre+style (e.g., `minimal` with `dnb`) |
| Missing preview | `--preview` not provided | Add `--preview` flag |

See [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) for deeper diagnostics.

## Known Limitations

- Assumes 4/4 time. Other time signatures are not supported.
- Works best with steady-tempo loops. Rubato or heavily swung material will have low timing confidence.
- No destructive source trimming — bar count is selected at generation time but the source is not modified.
- No stem separation — source activity features are descriptive, not separated into individual instruments.
- No chord recognition or harmonic analysis.
- No full DAW project export (no Ableton Live Set, no Logic project).
- Downbeat detection is simple and may be wrong for material with pickups, fades, or irregular phrasing.
- Strudel output preserves grid readability; microtiming is documented in comments but not reflected in Strudel's performance.
- Preview audio uses synthesized drum sounds (no sample library). It is intended for groove audition, not mix reference.
- No drum kit configuration or sample loading.

## Documentation Index

- [Full CLI Reference](docs/CLI.md) — every option with examples
- [Musical Model](docs/MUSICAL_MODEL.md) — how generation works under the hood
- [Output Formats](docs/OUTPUT_FORMATS.md) — JSON, MIDI, Strudel, preview details
- [Troubleshooting](docs/TROUBLESHOOTING.md) — symptom/cause/fix reference
- [Roadmap](docs/ROADMAP.md) — project direction
- [Contributing](CONTRIBUTING.md) — development guide
- [Baseline Architecture](docs/baseline-architecture.md) — original architecture documentation
- [Source Activity Maps](docs/source-activity-maps.md) — feature map documentation
- [Timing Diagnostics](docs/timing-diagnostics.md) — grid and timing tools

## Development

```bash
uv sync
uv run pytest      # 83 tests
uv run ruff check .  # lint
```

### Project layout

```
breaksmith/
├── analysis.py              # Audio analysis (librosa)
├── cli.py                   # CLI argument parsing and dispatch
├── click.py                 # Click track rendering
├── generator.py             # DnB pattern generation
├── generator_shared.py      # Shared controls and utilities
├── hiphop.py                # Hip-hop pattern generation
├── models.py                # Data models, grammars, presets
├── synth.py                 # Audio preview synthesis
└── exporters/
    ├── json_export.py       # JSON and CSV export
    ├── midi.py              # MIDI file export
    └── strudel.py           # Strudel pattern export
```

### Contributing notes

- Keep output deterministic for the same inputs.
- Preserve the genre/style distinction — genre defines grammar, style defines groove.
- Update `docs/CLI.md` when adding or changing CLI options.
- Add tests for new features. Run `pytest` and `ruff check` before committing.
- Do not commit generated output, `.venv`, or temporary audio files.
- Evaluate musical changes by listening as well as testing.

## License

MIT License. See [LICENSE](LICENSE).
