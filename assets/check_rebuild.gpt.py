#!/usr/bin/env python3
"""Rebuild the social preview and fail if the bytes moved.

The card is the one surface nobody looks at while working, so
it is the one most likely to keep advertising something that
stopped being true: it prints a skill count, and adding a
skill does not touch it. `assets/build.gpt.py` reads that
count from the repository, which makes the card derivable
rather than typed, but derivable is only useful if something
re-derives it.

This does, in a copy of the checkout, and compares the result
byte for byte against what is committed. A committed card
that no longer matches its sources fails here rather than
going out with the wrong number on it.

Needs headless Chrome, which is why it is a separate target
from `make check` rather than part of it.

    python3 assets/check_rebuild.gpt.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREVIEW = Path("assets/social-preview.png")


def dimensions(png: bytes) -> tuple:
    """Read width and height out of the PNG's IHDR chunk."""
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("social preview is not a PNG")
    if png[12:16] != b"IHDR":
        raise ValueError("social preview has no leading IHDR")
    return int.from_bytes(png[16:20]), int.from_bytes(png[20:24])


def main() -> int:
    shipped = (ROOT / PREVIEW).read_bytes()
    shipped_size = dimensions(shipped)

    with tempfile.TemporaryDirectory() as temporary:
        copy = Path(temporary) / "skills"
        shutil.copytree(
            ROOT, copy,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )
        result = subprocess.run(
            [sys.executable, "assets/build.gpt.py"],
            cwd=copy, env=os.environ.copy(), capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            return result.returncode

        rebuilt = (copy / PREVIEW).read_bytes()
        rebuilt_size = dimensions(rebuilt)
        if rebuilt_size != shipped_size:
            print(
                f"social preview is {shipped_size[0]}x{shipped_size[1]}, "
                f"rebuild is {rebuilt_size[0]}x{rebuilt_size[1]}",
                file=sys.stderr,
            )
            return 1
        if shipped != rebuilt:
            print(
                "social preview drifted from its sources; run "
                "`python3 assets/build.gpt.py` and commit the result",
                file=sys.stderr,
            )
            return 1

    print(
        f"OK    social preview reproduces byte for byte "
        f"({shipped_size[0]}x{shipped_size[1]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
