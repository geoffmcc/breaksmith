from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="breaksmith-gui",
        description="Launch the Breaksmith Desktop GUI.",
    )
    parser.add_argument("audio", nargs="?", help="Optional audio file to open on startup")
    parser.add_argument("--offscreen", action="store_true", help="Use Qt offscreen mode for smoke tests")
    args = parser.parse_args()
    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from .window import run_gui

    raise SystemExit(run_gui(args.audio))


if __name__ == "__main__":
    main()
