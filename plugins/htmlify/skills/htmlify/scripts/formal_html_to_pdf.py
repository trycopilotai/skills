#!/usr/bin/env python3
"""Print trusted HTML to PDF with an available backend.

The command tries WeasyPrint, a Chromium-family browser,
then wkhtmltopdf. It writes each attempt to a temporary
sibling and replaces the requested destination only after a
backend reports success with a non-empty file.

Usage:
    python3 formal_html_to_pdf.py INPUT.html
    python3 formal_html_to_pdf.py INPUT.html --output OUTPUT.pdf
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path


Backend = Callable[[Path, Path], bool]

_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)


def _find_chrome() -> str | None:
    command_names = (
        "google-chrome",
        "chromium",
        "chromium-browser",
        "chrome",
        "msedge",
    )
    for name in command_names:
        found = shutil.which(name)
        if found:
            return found
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _via_weasyprint(source: Path, destination: Path) -> bool:
    try:
        import weasyprint  # type: ignore
    except Exception:
        return False

    try:
        weasyprint.HTML(filename=str(source)).write_pdf(
            str(destination)
        )
    except Exception:
        return False
    return destination.exists()


def _chrome_command(
    executable: str,
    headless_flag: str,
    source: Path,
    destination: Path,
) -> list[str]:
    return [
        executable,
        headless_flag,
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--print-to-pdf={}".format(destination.resolve()),
        source.resolve().as_uri(),
    ]


def _via_chrome(source: Path, destination: Path) -> bool:
    executable = _find_chrome()
    if not executable:
        return False

    flags = ("--headless=new", "--headless")
    for flag in flags:
        result = subprocess.run(
            _chrome_command(
                executable,
                flag,
                source,
                destination,
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if (
            result.returncode == 0
            and destination.exists()
            and destination.stat().st_size > 0
        ):
            return True
        if destination.exists():
            destination.unlink()
    return False


def _via_wkhtmltopdf(
    source: Path,
    destination: Path,
) -> bool:
    executable = shutil.which("wkhtmltopdf")
    if not executable:
        return False
    result = subprocess.run(
        [
            executable,
            "--page-size",
            "Letter",
            "--margin-top",
            "0",
            "--margin-bottom",
            "0",
            "--margin-left",
            "0",
            "--margin-right",
            "0",
            str(source),
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    if not destination.exists():
        return False
    return destination.stat().st_size > 0


def _backend_candidates() -> Sequence[tuple[str, Backend]]:
    return (
        ("weasyprint", _via_weasyprint),
        ("chrome", _via_chrome),
        ("wkhtmltopdf", _via_wkhtmltopdf),
    )


def _temporary_destination(destination: Path) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix="." + destination.name + ".",
        suffix=".tmp.pdf",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(raw_path)
    temporary.unlink()
    return temporary


def to_pdf(source: Path, destination: Path) -> str:
    if not source.is_file():
        raise FileNotFoundError(source)

    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = _temporary_destination(destination)
    failures: list[str] = []

    try:
        for name, backend in _backend_candidates():
            if candidate.exists():
                candidate.unlink()
            try:
                succeeded = backend(source, candidate)
            except Exception as error:
                failures.append("{}: {}".format(name, error))
                continue

            if (
                succeeded
                and candidate.exists()
                and candidate.stat().st_size > 0
            ):
                candidate.replace(destination)
                return name
            failures.append("{}: unavailable or failed".format(name))
    finally:
        if candidate.exists():
            candidate.unlink()

    detail = "; ".join(failures)
    raise RuntimeError(
        "No PDF backend produced output. "
        "Install WeasyPrint, Chrome, Chromium, Microsoft "
        "Edge, or wkhtmltopdf. Attempts: {}".format(detail)
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print trusted HTML to PDF."
    )
    parser.add_argument("input", type=Path, help="source HTML")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="destination PDF",
    )
    args = parser.parse_args(arguments)

    if args.output is not None:
        output = args.output
    else:
        output = args.input.with_suffix(".pdf")
    backend = to_pdf(args.input, output)
    print("{}\t(via {})".format(output, backend))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
