#!/usr/bin/env python3
"""Render Markdown to formal HTML and optionally PDF.

Usage:
    python3 formal_render.py INPUT.md
    python3 formal_render.py INPUT.md --no-pdf
    python3 formal_render.py INPUT.md --html OUTPUT.html
    python3 formal_render.py INPUT.md --pdf OUTPUT.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIRECTORY))

import formal_html_to_pdf as html_to_pdf  # noqa: E402
import formal_md_to_html as markdown_to_html  # noqa: E402


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render Markdown to formal HTML and PDF."
    )
    parser.add_argument("input", type=Path, help="source Markdown")
    parser.add_argument(
        "--html",
        type=Path,
        help="destination HTML",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        help="destination PDF",
    )
    parser.add_argument(
        "--title",
        help="override the document title",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="render HTML only",
    )
    args = parser.parse_args(arguments)

    markdown = args.input.read_text(encoding="utf-8")
    if args.html is not None:
        html_output = args.html
    else:
        html_output = markdown_to_html.default_output(args.input)
    html_output.parent.mkdir(parents=True, exist_ok=True)
    html_output.write_text(
        markdown_to_html.render(markdown, title=args.title),
        encoding="utf-8",
    )
    print(html_output)

    if args.no_pdf:
        return 0

    if args.pdf is not None:
        pdf_output = args.pdf
    else:
        pdf_output = html_output.with_suffix(".pdf")
    backend = html_to_pdf.to_pdf(html_output, pdf_output)
    print("{}\t(via {})".format(pdf_output, backend))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
