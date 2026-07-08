# Troubleshooting

## Setup Issues

### `uv: command not found`

uv is not installed or not in PATH.

**Fix**: Install uv. See [installation guide](https://docs.astral.sh/uv/getting-started/installation/).

### Hardlink warning during `uv sync`

```
warning: failed to hardlink file; falling back to full copy
```

Caused by running `uv sync` across filesystem boundaries (e.g., WSL `/mnt/c/` mount). This is harmless — uv falls back to copying.

**Fix**: Set environment variable to suppress the warning:

```bash
export UV_LINK_MODE=copy
```

### `uv python install` fails

The requested Python version may not be available or already installed.

**Fix**: Check available versions and install explicitly:

```bash
uv python list
uv python install 3.12
```

### FFmpeg errors on compressed audio

```
Error: FFmpeg not found
```

Breaksmith uses FFmpeg to decode compressed audio (MP3, M4A, FLAC, OGG). WAV files do not require FFmpeg.

**Fix**: Install FFmpeg:
- Ubuntu/Debian/WSL: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: `winget install ffmpeg`

### `uv run breaksmith` not found

The virtual environment may not be set up, or the script entry point is misconfigured.

**Fix**: Run `uv sync` first. Verify the script is defined in `pyproject.toml`.

```bash
uv sync
grep -A5 "\[project.scripts\]" pyproject.toml
```

## Analysis Issues

### Wrong BPM detected

Breaksmith uses librosa's `beat.beat_track` for BPM estimation. Common failure modes:

| Scenario | Typical Result |
|---|---|
| Source has weak transients (pads, strings, sustained synths) | Random BPM, low confidence |
| Source is half-time or double-time relative to expected BPM | Detected BPM is 2× or ½× expected |
| Source has internal tempo changes | BPM is a weighted average |
| Source is a long track (not a loop) | BPM may drift |

**Fix**: Always provide `--bpm` when you know the correct tempo.

```bash
uv run breaksmith analyze input.wav --bpm 174
```

### Low beat confidence

Beat confidence reports how many beat positions were detected relative to the expected count. Low confidence (~0.5 or below) means the beat tracker could not find clear beat positions.

**Common causes**:
- Sustained material without clear transients
- Very sparse or minimal material
- Source with heavy reverb or wash
- Source that is not a drum loop

**Fix**: Verify timing by ear using the click track:

```bash
uv run breaksmith analyze input.wav --render-click
```

Listen to `source-with-click.wav`. If the click is aligned, the grid is correct even if confidence is low.

### Beat count mismatch

If the detected beat count is significantly different from `bars × beats_per_bar`, the grid is misaligned.

**Fix**: Use `--grid-start` to adjust the starting point:

```bash
uv run breaksmith analyze input.wav --grid-start 0.125
```

### Duration fit is not `clean`

| Fit | Meaning | Fix |
|---|---|---|
| `small_tail` | Source has a tiny amount beyond N bars | No action needed — tail is ignored |
| `extra_beat` | Source has roughly one extra beat | Use `--bars` to set exact count, or accept the automatic selection |
| `partial_bar` | Source does not align with whole bars | Provide `--bars` with known bar count, or try a different `--grid-start` |

### Feature CSV is empty or has wrong values

Feature maps are computed on the grid, not per-sample. Each row is one grid step. If `--steps-per-bar` is changed, the same analysis may look different because the grid resolution changed.

**Fix**: Use `--features-csv` with the default `--steps-per-bar 16` for comparison with other outputs.

## Click Track Issues

### Click is misaligned with the source

If `source-with-click.wav` has clicks that drift relative to the audio, the grid start or BPM is wrong.

**Fix**:
1. Determine the correct BPM and grid start by ear.
2. Run analysis with overrides:

```bash
uv run breaksmith analyze input.wav --bpm 172 --grid-start 0.1 --render-click
```

3. Listen to the new `source-with-click.wav`. Repeat until the click is steady.

### Click is off by an 8th note or 16th note

The beat tracker chose the correct tempo but wrong subdivision.

**Fix**: Provide the beat-anchored BPM:

```bash
uv run breaksmith analyze input.wav --bpm 86   # half of 172
uv run breaksmith analyze input.wav --bpm 172  # correct 16th-note rate
```

### No click track rendered

The `--render-click` flag was not provided.

**Fix**: Re-run analysis with the flag:

```bash
uv run breaksmith analyze input.wav --render-click
```

Existing analysis is overwritten unless `--output` is used.

## Generation Issues

### Preview sounds too busy

The master density is too high for the source. Low-energy bars are being filled aggressively.

**Fix**:
- Lower `--density` (e.g., 0.5 → 0.3)
- Increase `--source-restraint` so quiet bars stay quiet
- Lower per-layer density for specific instruments

```bash
uv run breaksmith generate input.wav --density 0.3 --source-restraint 0.4 --preview
```

### Preview sounds too sparse

Density is too low, or the style has a naturally sparse profile.

**Fix**:
- Raise `--density` (e.g., 0.3 → 0.6)
- Lower `--source-restraint`
- Try a denser style (e.g., `rolling` or `aggressive` for DnB)

### Preview ends abruptly

The default preview length matches the generation length.

**Fix**: Use `--preview-bars` to set a specific length:

```bash
uv run breaksmith generate input.wav --bars 16 --preview --preview-bars 8
```

This generates 16 bars of pattern but only renders the first 8 for preview.

### Preview does not match the groove I wanted

The groove feel is built from multiple layers:
- Style preset `swing_amount` (built-in)
- CLI `--swing` (adds to style swing)
- CLI `--groove` (per-step template)
- CLI `--humanize` (random jitter)

Try adjusting each layer:

```bash
# Tight, mechanical
uv run breaksmith generate input.wav --swing 0.0 --groove straight --humanize 0.0

# Laid-back hip-hop
uv run breaksmith generate input.wav --genre hiphop --groove laid_back --swing 0.08

# Loose, humanized
uv run breaksmith generate input.wav --humanize 0.3 --groove mpc
```

### Variants all sound too similar

Variants only shift the seed by 1 each time, which produces subtle changes. Increasing `--variation` will make each variant more distinct.

```bash
uv run breaksmith generate input.wav --variants 5 --variation 0.6
```

### Wrong genre/style combination

Some styles only work within their genre. For example, `minimal` requires `--genre dnb`.

**Fix**: Use the correct genre with the style, or use `--genre` explicitly:

```bash
uv run breaksmith generate input.wav --genre dnb --style minimal
```

### Poor Strudel output readability

Strudel output groups hits by instrument per bar. For very dense bars, the `x.x.x.x.` strings become long but remain readable.

**Fix**: Reduce density:

```bash
uv run breaksmith generate input.wav --density 0.4
```

### No preview generated

The `--preview` flag is required. Without it, only MIDI, JSON, and Strudel files are written.

**Fix**: Re-run with `--preview`.

### Comparison preview not generated

The `--preview-comparison` flag is required in addition to `--preview`:

```bash
uv run breaksmith generate input.wav --preview --preview-comparison
```

## MIDI Import Issues

### Notes are on wrong drum sounds

Your DAW may use a different drum map than GM.

**Fix**: Remap the MIDI notes in your DAW.

| Drum | GM Note | Common Alternative |
|---|---|---|
| Kick | 36 (C2) | 35 (B1) for acoustic kick |
| Snare | 38 (D2) | 40 (E2) for electric snare |
| Closed hat | 42 (F#2) | 44 (G#2) for pedal hat |
| Open hat | 46 (A#2) | 26 (C#1) for some drum machines |

### Velocity is too low or too high

Change the velocity curve:

```bash
uv run breaksmith generate input.wav --midi-velocity-curve hard   # all hits max
uv run breaksmith generate input.wav --midi-velocity-curve compressed  # narrower range
```

### Timing feels off in the DAW

MIDI timing offsets (swing, groove, humanize) are baked into note positions. If your DAW's grid quantizes the notes, you may lose the microtiming.

**Fix**: Set your DAW's note display to show raw positions (not quantized). The timing offsets are intentional.

## File Path Issues

### Path contains spaces

```
error: argument source: expected one argument
```

The path is being split on spaces.

**Fix**: Quote the path:

```bash
uv run breaksmith generate "path/to/my loop.wav"
```

### Audio file not found

```
[Errno 2] No such file or directory
```

On WSL, paths start with `/mnt/c/` not `C:\`.

**Fix**: Use the full WSL path:

```bash
uv run breaksmith generate "path/to/loop.wav"
```

### Output directory not writable

Permission errors when writing to `output/`.

**Fix**: Ensure the working directory is writable.

```bash
ls -la $(pwd)
```

## Reproducibility Issues

### Pattern does not match a previous run

Possible causes:
- Different source file (even same path, different content)
- Different seed, style, genre, bars, or controls
- Different version of Breaksmith (SHA256 in metadata)
- Source file was modified after the original generation

**Fix**: Check the `input_manifest` in the `pattern.json` metadata for the exact inputs used.

```bash
uv run breaksmith generate input.wav --seed 42 --style liquid --genre dnb --bars 8
```

This should always produce the same output for the same source file.

### SHA256 mismatch

The `source_sha256` in `pattern.json` metadata confirms which source file was used. If re-running on a different file (even with the same name), the pattern will differ.

## Getting Help

If troubleshooting does not resolve the issue:

1. Run with full output to see any error messages:
   ```bash
   uv run breaksmith analyze input.wav --render-click
   ```
2. Check the analysis JSON for BPM, confidence, and duration fit:
   ```bash
   uv run breaksmith analyze input.wav
   cat analysis.json | python -m json.tool | head -40
   ```
3. Verify your source file is valid audio:
   ```bash
   ffprobe input.wav 2>&1 | grep -E "Duration|Stream"
   ```
4. Test with a known-good source (a short, clean WAV loop with clear transients).
5. Run the test suite to verify nothing is broken:
   ```bash
   uv run pytest
   ```
