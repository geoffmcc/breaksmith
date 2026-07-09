# Breaksmith Desktop GUI

Launch the desktop app with:

```bash
uv run breaksmith-gui
```

Open a file from `File > Open Audio`, the toolbar, or drag-and-drop. Breaksmith reads real audio metadata and renders a downsampled waveform from decoded samples.

## Workflow

1. Load an audio file.
2. Press `Analyze` to run the shared Breaksmith analysis engine.
3. Review selected BPM, raw BPM, confidence, fit classification, candidates, warnings, and beat markers on the waveform.
4. Set manual BPM or grid-start overrides if needed.
5. Configure genre, style, bars, variations, seed, density, swing, humanize, variation, groove, and preview rendering.
6. Press `Generate` to write MIDI, Strudel, JSON, and optional WAV previews into a unique run directory.
7. Double-click a result to play its rendered preview.
8. Use `Open Run Directory` to locate all artifacts.

## Presets

Use `Save Preset` to persist current generation settings as JSON. Use `Load Preset` to restore settings. Presets are validated and stored in the platform user-data directory unless exported elsewhere.

The same preset files can be used from the CLI:

```bash
uv run breaksmith generate input.wav --preset path/to/preset.json --output output
```

## Run History

The Run History tab scans the configured output parent for child directories containing `manifest.json`. Double-click a run to inspect its manifest without recomputing or overwriting outputs.

## Logs

`Tools > View Logs` opens the GUI log directory. Logs include startup environment, job failures, and technical details for diagnostics.
