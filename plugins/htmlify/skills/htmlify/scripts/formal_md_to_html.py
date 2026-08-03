#!/usr/bin/env python3
"""Render a documented Markdown subset as formal HTML.

The output is a monochrome, US Letter document intended for
browser viewing and printing. The renderer uses only the
Python standard library.

Usage:
    python3 formal_md_to_html.py INPUT.md
    python3 formal_md_to_html.py INPUT.md --output OUTPUT.html
    python3 formal_md_to_html.py INPUT.md --title "Document title"
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from urllib.parse import urlsplit


STYLE = """\
@page {
  size: Letter;
  margin: 0;
}
:root {
  color-scheme: light;
  --ink: #000;
  --muted: #444;
  --rule: #b8b8b8;
  --soft: #f1f1f1;
  --paper: #fff;
  --accent: #000;
  --accent-soft: #f4f4f4;
}
* {
  box-sizing: border-box;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
html {
  background: #e6e6e6;
  color: var(--ink);
  font-family: Helvetica, Arial, sans-serif;
  font-size: 12px;
  line-height: 1.43;
}
body {
  margin: 0;
  padding: 24px 0;
}
main.paper {
  position: relative;
  width: 8.5in;
  min-height: 11in;
  margin: 0 auto;
  padding: 0.5in 0.68in 0.62in;
  background: var(--paper);
  border-top: 8px solid var(--accent);
  box-shadow: 0 16px 42px rgba(0, 0, 0, 0.18);
}
h1,
h2,
h3 {
  margin: 0;
  color: #000;
  font-family: Helvetica, Arial, sans-serif;
  line-height: 1.16;
}
h1 {
  max-width: 6.8in;
  margin-bottom: 12px;
  font-size: 20px;
  font-weight: 700;
}
h2 {
  margin-top: 24px;
  border-top: 2px solid #000;
  padding-top: 12px;
  font-size: 16px;
  break-after: avoid;
}
h2.appendix {
  break-before: auto;
}
h3 {
  margin-top: 16px;
  font-size: 16px;
  font-weight: 800;
  break-after: avoid;
}
p,
ul,
ol {
  margin: 8.5px 0;
}
ul,
ol {
  padding-left: 20px;
}
li {
  margin: 4.5px 0;
}
strong {
  color: #000;
}
main.paper > h1 + p {
  margin: 12px 0 18px;
  padding: 11px 13px;
  border-left: 4px solid var(--accent);
  background: var(--accent-soft);
  color: #000;
  font-size: 12px;
}
.table-wrap {
  width: 100%;
  overflow: visible;
  margin: 10px 0 15px;
  break-inside: avoid;
}
table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  overflow: hidden;
  border: 1px solid var(--rule);
  font-size: 12px;
  line-height: 1.3;
}
th,
td {
  border: 0;
  border-bottom: 1px solid var(--rule);
  padding: 5.5px 6.5px;
  vertical-align: top;
}
th + th,
td + td {
  border-left: 1px solid var(--rule);
}
th {
  background: var(--soft);
  font-weight: 700;
  color: #000;
}
tr:nth-child(even) td {
  background: #f8f8f8;
}
tr:last-child td {
  border-bottom: 0;
}
tr {
  break-inside: avoid;
}
blockquote {
  margin: 12px 0;
  padding: 9px 13px;
  border-left: 4px solid var(--accent);
  background: #fafafa;
}
blockquote p {
  margin: 6px 0;
}
hr {
  border: 0;
  border-top: 1px solid var(--rule);
  margin: 18px 0;
}
pre {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
code {
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}
a {
  color: #000;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}
@media print {
  html,
  body {
    background: #fff;
    padding: 0;
  }
  main.paper {
    width: auto;
    min-height: 0;
    box-shadow: none;
    margin: 0;
    border-top: 8px solid var(--accent);
  }
}
"""

_CODE_SENTINEL = "\x00C{}\x00"
_LINK_SENTINEL = "\x00L{}\x00"
_HR_RE = re.compile(r"^ {0,3}([-*_])(?: *\1){2,} *$")
_ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_OL_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_UL_RE = re.compile(r"^[-*+]\s+(.*)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _apply_emphasis(text: str) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])",
        r"<em>\1</em>",
        text,
    )
    text = re.sub(
        r"(?<![\w_])_(?!\s)([^_]+?)(?<!\s)_(?![\w_])",
        r"<em>\1</em>",
        text,
    )
    return text


def _safe_href(href: str) -> bool:
    if href.startswith("//"):
        return False
    parsed = urlsplit(href)
    scheme = parsed.scheme.lower()
    if not scheme:
        return True
    if scheme in {"http", "https", "mailto"}:
        return True
    return False


def _unescape_pipe_backslashes(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        backslashes = match.group(1)
        return "\\" * (len(backslashes) // 2) + "|"

    return re.sub(r"(\\+)\|", replace, text)


def _inline(text: str) -> str:
    codes: list[str] = []
    links: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        codes.append(html.escape(match.group(1), quote=False))
        return _CODE_SENTINEL.format(len(codes) - 1)

    def stash_link(match: re.Match[str]) -> str:
        label_source = _unescape_pipe_backslashes(match.group(1))
        label = html.escape(label_source, quote=False)
        label = _apply_emphasis(label)
        href = _unescape_pipe_backslashes(match.group(2))
        if _safe_href(href):
            emitted_href = href.replace("\\", "%5C")
            escaped_href = html.escape(emitted_href, quote=True)
            rendered = '<a href="{}">{}</a>'.format(
                escaped_href,
                label,
            )
        else:
            rendered = html.escape(match.group(0), quote=False)
        links.append(rendered)
        return _LINK_SENTINEL.format(len(links) - 1)

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = _LINK_RE.sub(stash_link, text)
    text = _unescape_pipe_backslashes(text)
    text = html.escape(text, quote=False)
    text = _apply_emphasis(text)

    for index, code in enumerate(codes):
        text = text.replace(
            _CODE_SENTINEL.format(index),
            "<code>{}</code>".format(code),
        )
    for index, link in enumerate(links):
        text = text.replace(_LINK_SENTINEL.format(index), link)
    return text


def _strip_front_matter(
    lines: list[str],
) -> tuple[list[str], str | None]:
    if not lines or lines[0].strip() != "---":
        return lines, None

    title = None
    for index in range(1, len(lines)):
        if lines[index].strip() != "---":
            continue
        for frontmatter_line in lines[1:index]:
            match = re.match(
                r"\s*title\s*:\s*(.+?)\s*$",
                frontmatter_line,
            )
            if match:
                title = match.group(1).strip().strip("\"'")
        return lines[index + 1 :], title
    return lines, None


def _is_table_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = [
        cell.strip()
        for cell in line.strip().strip("|").split("|")
    ]
    if not cells:
        return False
    return all(
        re.fullmatch(r":?-{1,}:?", cell) is not None
        for cell in cells
    )


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    trailing_pipe_is_escaped = False
    if line.endswith("|"):
        preceding_backslashes = 0
        cursor = len(line) - 2
        while cursor >= 0 and line[cursor] == "\\":
            preceding_backslashes += 1
            cursor -= 1
        trailing_pipe_is_escaped = preceding_backslashes > 0
    cells: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(line):
        character = line[index]
        if character == "\\":
            run_end = index
            while run_end < len(line) and line[run_end] == "\\":
                run_end += 1
            run_length = run_end - index
            if run_end < len(line) and line[run_end] == "|":
                current.extend("\\" * (run_length - 1))
                current.append("|")
                index = run_end + 1
                continue
            current.extend("\\" * run_length)
            index = run_end
            continue
        if character == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(character)
        index += 1
    cells.append("".join(current).strip())
    if (
        line.endswith("|")
        and not trailing_pipe_is_escaped
        and cells[-1] == ""
    ):
        cells.pop()
    return cells


def _alignments(separator: str) -> list[str]:
    alignments: list[str] = []
    for cell in _split_row(separator):
        left = cell.startswith(":")
        right = cell.endswith(":")
        if left and right:
            alignments.append("center")
        elif right:
            alignments.append("right")
        else:
            alignments.append("left")
    return alignments


def _gather_list(
    lines: list[str],
    index: int,
    count: int,
) -> tuple[str, int]:
    first_ordered_match = _OL_RE.match(lines[index].strip())
    ordered = first_ordered_match is not None
    ordered_start = "1"
    if first_ordered_match is not None:
        ordered_start = first_ordered_match.group(1)
    items: list[str] = []
    current: list[str] | None = None

    while index < count:
        raw = lines[index]
        stripped = raw.strip()
        if not stripped:
            next_index = index + 1
            while (
                next_index < count
                and not lines[next_index].strip()
            ):
                next_index += 1
            if next_index >= count:
                break
            next_line = lines[next_index].strip()
            if _UL_RE.match(next_line) or _OL_RE.match(next_line):
                index = next_index
                continue
            break

        unordered_match = _UL_RE.match(stripped)
        ordered_match = _OL_RE.match(stripped)
        if ordered_match and ordered:
            if current is not None:
                items.append(" ".join(current))
            current = [ordered_match.group(2)]
            index += 1
        elif unordered_match and not ordered:
            if current is not None:
                items.append(" ".join(current))
            current = [unordered_match.group(1)]
            index += 1
        elif raw.startswith((" ", "\t")) and current is not None:
            current.append(stripped)
            index += 1
        else:
            break

    if current is not None:
        items.append(" ".join(current))

    if ordered:
        if ordered_start == "1":
            open_tag = "<ol>"
        else:
            open_tag = '<ol start="{}">'.format(ordered_start)
        close_tag = "</ol>"
    else:
        open_tag = "<ul>"
        close_tag = "</ul>"
    body = "\n".join(
        "<li>{}</li>".format(_inline(item)) for item in items
    )
    return "{}\n{}\n{}".format(open_tag, body, close_tag), index


def _render_blockquote(lines: list[str]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    inner = "\n".join(
        "<p>{}</p>".format(_inline(paragraph))
        for paragraph in paragraphs
    )
    return "<blockquote>\n{}\n</blockquote>".format(inner)


def _alignment_style(
    alignments: list[str],
    index: int,
) -> str:
    alignment = "left"
    if index < len(alignments):
        alignment = alignments[index]
    return ' style="text-align:{}"'.format(alignment)


def _render_table(
    header: list[str],
    alignments: list[str],
    body: list[list[str]],
) -> str:
    head = "".join(
        "<th{}>{}</th>".format(
            _alignment_style(alignments, index),
            _inline(cell),
        )
        for index, cell in enumerate(header)
    )
    rows: list[str] = []
    for row in body:
        cells = "".join(
            "<td{}>{}</td>".format(
                _alignment_style(alignments, index),
                _inline(cell),
            )
            for index, cell in enumerate(row)
        )
        rows.append("<tr>{}</tr>".format(cells))
    return (
        '<div class="table-wrap">\n'
        "<table>\n"
        "<thead>\n"
        "<tr>{}</tr>\n"
        "</thead>\n"
        "<tbody>\n"
        "{}\n"
        "</tbody>\n"
        "</table>\n"
        "</div>"
    ).format(head, "\n".join(rows))


def _convert(markdown: str) -> tuple[str, str | None]:
    lines = (
        markdown.replace("\r\n", "\n")
        .replace("\r", "\n")
        .split("\n")
    )
    lines, frontmatter_title = _strip_front_matter(lines)
    output: list[str] = []
    title = frontmatter_title
    index = 0
    count = len(lines)

    while index < count:
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            index += 1
            buffer: list[str] = []
            while (
                index < count
                and not lines[index].strip().startswith("```")
            ):
                buffer.append(
                    html.escape(lines[index], quote=False)
                )
                index += 1
            if index < count:
                index += 1
            output.append(
                "<pre><code>{}</code></pre>".format(
                    "\n".join(buffer)
                )
            )
            continue

        if _HR_RE.match(line):
            output.append("<hr />")
            index += 1
            continue

        heading_match = _ATX_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            source_text = heading_match.group(2)
            rendered_text = _inline(source_text)
            if level == 1 and title is None:
                title = source_text.strip()
            if level == 2 and re.match(
                r"appendix\b",
                source_text.strip(),
                re.IGNORECASE,
            ):
                output.append(
                    '<h2 class="appendix">{}</h2>'.format(
                        rendered_text
                    )
                )
            else:
                rendered_level = min(level, 3)
                output.append(
                    "<h{0}>{1}</h{0}>".format(
                        rendered_level,
                        rendered_text,
                    )
                )
            index += 1
            continue

        if (
            "|" in line
            and index + 1 < count
            and _is_table_separator(lines[index + 1])
        ):
            header = _split_row(line)
            alignments = _alignments(lines[index + 1])
            index += 2
            body: list[list[str]] = []
            while (
                index < count
                and lines[index].strip()
                and "|" in lines[index]
            ):
                body.append(_split_row(lines[index]))
                index += 1
            output.append(_render_table(header, alignments, body))
            continue

        if stripped.startswith(">"):
            buffer = []
            while (
                index < count
                and lines[index].strip().startswith(">")
            ):
                buffer.append(
                    re.sub(r"^\s*>\s?", "", lines[index])
                )
                index += 1
            output.append(_render_blockquote(buffer))
            continue

        if _UL_RE.match(stripped) or _OL_RE.match(stripped):
            block, index = _gather_list(lines, index, count)
            output.append(block)
            continue

        buffer = [stripped]
        index += 1
        while index < count:
            next_line = lines[index].strip()
            if not next_line:
                break
            if next_line.startswith(("#", ">", "```")):
                break
            if _HR_RE.match(lines[index]):
                break
            if _UL_RE.match(next_line) or _OL_RE.match(next_line):
                break
            if (
                "|" in lines[index]
                and index + 1 < count
                and _is_table_separator(lines[index + 1])
            ):
                break
            buffer.append(next_line)
            index += 1
        output.append(
            "<p>{}</p>".format(_inline(" ".join(buffer)))
        )

    return "\n".join(output), title


def render(markdown: str, title: str | None = None) -> str:
    body, document_title = _convert(markdown)
    page_title = title or document_title or "Document"
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8" />\n'
        '    <meta name="viewport" '
        'content="width=device-width, initial-scale=1" />\n'
        "    <title>{title}</title>\n"
        "    <style>\n{style}\n    </style>\n"
        "  </head>\n"
        "  <body>\n"
        '    <main class="paper">\n'
        "{body}\n"
        "    </main>\n"
        "  </body>\n"
        "</html>\n"
    ).format(
        title=html.escape(page_title, quote=False),
        style=STYLE,
        body=body,
    )


def default_output(source: Path) -> Path:
    name = source.name
    for suffix in (".gpt.md", ".markdown", ".md"):
        if name.endswith(suffix):
            stem = name[: -len(suffix)]
            return source.with_name(stem + ".html")
    return source.with_suffix(".html")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render Markdown as formal HTML."
    )
    parser.add_argument("input", type=Path, help="source Markdown")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="destination HTML",
    )
    parser.add_argument(
        "--title",
        help="override the document title",
    )
    args = parser.parse_args(arguments)

    markdown = args.input.read_text(encoding="utf-8")
    if args.output is not None:
        output = args.output
    else:
        output = default_output(args.input)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render(markdown, title=args.title),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
