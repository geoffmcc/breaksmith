# Windows Packaging

Build a GUI executable with PyInstaller from the repository root:

```bash
uv sync --group package
uv run --group package pyinstaller packaging/pyinstaller/breaksmith-gui.spec
```

The GUI executable is windowed and uses the same Python package as the CLI. FFmpeg is not bundled; users should install it separately when compressed audio decoding is needed.

Current packaging scaffold does not include a custom application icon. Add a redistributable `.ico` asset before producing a branded public release.
