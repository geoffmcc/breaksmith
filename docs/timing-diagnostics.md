# Timing Diagnostics

Breaksmith's timing tools are designed to make the generated grid audible and inspectable before deeper musical generation decisions are made.

## Grid Start And Downbeat

By default, Breaksmith estimates the first usable beat from the source audio. If beat tracking is unreliable or starts too late, it anchors the grid at the beginning of the file and emits a warning.

Use `--grid-start` when the musical grid starts after a pickup, silence, or export offset:

```bash
uv run breaksmith analyze input.wav --bpm 172 --grid-start 0.125
```

Use `--downbeat-start` when you want to explicitly mark the first downbeat. In the current engine, the downbeat and grid start share the same timing point; `--downbeat-start` overrides `--grid-start` when both are provided.

```bash
uv run breaksmith analyze input.wav --bpm 172 --downbeat-start 0.125
```

Use the same override during generation:

```bash
uv run breaksmith generate input.wav --bpm 172 --grid-start 0.125 --bars 8
```

## Timing Confidence

Analysis JSON includes:

- `grid_start_seconds`
- `downbeat_seconds`
- `grid_start_source`
- `tempo_confidence`
- `beat_confidence`
- `detected_beat_count`
- `expected_beat_count`

When `--bpm` is supplied, `tempo_confidence` is treated as high because the tempo is user-defined. `beat_confidence` still reflects how many beat positions were detected relative to the expected grid. Low beat confidence means the user should verify timing by ear.

## Click Renders

Render diagnostic clicks with:

```bash
uv run breaksmith analyze input.wav --bpm 172 --render-click
```

This writes:

```text
click.wav
source-with-click.wav
```

The click-only file places a brighter downbeat click at each bar start and a regular click on the other beats. The source-with-click file mixes those clicks over the original source without modifying the source file.

Use the click render to confirm:

- the first bar starts in the right place
- the BPM matches the source
- loops with pickups use the intended grid start
- `--bars` clamping is based on the intended musical boundary

## Current Limitations

- Downbeat and grid start have separate CLI overrides (`--grid-start`, `--downbeat-start`) but the grid timing model still uses a single timing reference internally.
- Tempo and beat confidence are simple diagnostic scores, not a full probabilistic timing model.
- Click renders are diagnostic WAVs only; they are not part of generated drum patterns.
