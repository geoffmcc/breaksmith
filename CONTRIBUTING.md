# Contributing

## Development Setup

```bash
uv sync
uv run pytest
```

## Code Style

- Run `ruff check .` before committing.
- Keep output deterministic for the same inputs.
- Type hints on all public functions and dataclasses.
- No unused imports or variables.

## Architecture

- **genre** defines the rhythmic grammar (note stride, bar grid, default controls).
- **style** defines the groove vocabulary (density per instrument, syncopation, fill frequency, velocity ranges).
- **meter** defines the time signature (step grid, beat groupings, accent positions).
- **GenerationControls** is the single parameter object flowing into all generators.
- Generators are pure functions: `generate_pattern(source: dict, controls: GenerationControls) -> Pattern`.
- Add new genres by creating a generator module and a style preset dict.
- Add new styles by adding entries to the style preset dict.
- Add new meters by adding a `Meter` preset in `models.py` and updating `parse_time_signature()`.
- Add new controls by adding a field to `GenerationControls` and threading it through.

## Tests

- 108 tests in `tests/test_generator.py`.
- Tests cover deterministic output, genre-style pairs, control ranges, preset loading, variant generation, per-layer density, source restraint, phrase awareness, groove templates, meter support (4/4, 3/4, 6/8, beat grouping), and import of all modules.
- Add tests for new features.
- Run with `uv run pytest`.
- Run with `-v` for verbose output: `uv run pytest -v`.

## CLI

- CLI is defined in `breaksmith/cli.py` using `argparse` with subcommands.
- Always update `docs/CLI.md` when adding or changing CLI options.
- Keep help text concise but descriptive — it is the primary documentation users see.

## Documentation

- Update `docs/CLI.md` for CLI option changes.
- Update `docs/MUSICAL_MODEL.md` for generation pipeline or model changes.
- Update `docs/OUTPUT_FORMATS.md` for export format changes.
- Update `docs/TROUBLESHOOTING.md` for new common issues.

## Output Formats

- **MIDI**: `breaksmith/exporters/midi.py`. Type 1 multi-track, GM drum map.
- **JSON**: `breaksmith/exporters/json_export.py`. Logical grid with microtiming.
- **Strudel**: `breaksmith/exporters/strudel.py`. Readable mini-notation.
- **Preview**: `breaksmith/synth.py`. 5 synthesized instruments, 0.25s per hit.

## What Not to Commit

- Generated `output/` content, `.venv/`, temp audio files, or WAV/CSV artifacts.

## Review Workflow

1. Author changes.
2. Update `docs/CLI.md` for any new CLI options.
3. Run `uv run pytest` and `uv run ruff check .`.
4. Stage all files: `git add -A`.
5. Commit: `git commit -m "description"` (use `-S` to sign if you have GPG set up).
6. Push: `git push`.
