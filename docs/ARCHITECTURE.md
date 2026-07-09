# Breaksmith Architecture

Breaksmith is structured as one core product with two interfaces:

```text
Breaksmith Core
├── Breaksmith CLI
└── Breaksmith Desktop GUI
```

## Core

The reusable application layer lives in `breaksmith/app.py`. It defines typed request and result models for analysis, generation, progress, source metadata, waveform peaks, generated results, artifacts, and run history queries.

The core depends on analysis, generation, exporters, synth rendering, and run-directory services. It does not import PySide6 and can run headlessly.

## CLI Adapter

`breaksmith/cli.py` preserves the existing `breaksmith analyze` and `breaksmith generate` commands and now delegates real work to `analyze_source()` and `generate_patterns()`.

The CLI remains scriptable and headless. It also exposes `breaksmith runs` for inspecting prior run manifests and `breaksmith generate --preset` for preset-based automation.

## GUI Adapter

`breaksmith/gui/` contains the PySide6 desktop application. It imports the core services and presents source loading, waveform display, playback, analysis, generation, presets, artifacts, and run history.

Expensive work is executed through `FunctionJob` on `QThreadPool`. Worker callbacks emit structured `ProgressEvent` objects and support cooperative cancellation through a cancel token.

## Artifacts And Runs

Run-directory naming, collision handling, artifact registration, and manifest writing are centralized in `breaksmith/run.py`. Manifests are written atomically with a temporary file and replace-on-success. `load_run_manifest()` validates JSON shape and rejects unsafe absolute or traversal artifact paths.

## Presets

Generation presets are human-readable JSON files using a versioned schema in `breaksmith/presets.py`. User presets are stored under the platform user-data directory, not the installed package.

## Dependency Direction

The dependency direction is:

```text
GUI -> app core -> analysis/generation/export/run
CLI -> app core -> analysis/generation/export/run
```

Core modules do not depend on GUI modules.
