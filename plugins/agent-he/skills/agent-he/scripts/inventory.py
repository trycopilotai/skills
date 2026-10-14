#!/usr/bin/env python3
"""Pass-one page inventory for a heuristic evaluation.

Most heuristic-evaluation findings live in the shipped
source, not in the render. This sweeps a set of URLs without
a browser and reports what pass one is for: status and size,
`lang`, title, social metadata, favicon, raw-entity leakage,
alt-text gaps, media element counts, form controls, and any
rate-limit headers the origin returns.

Standard library only. `curl` remains the right tool for a
single ad-hoc request; this is the sweep.

Usage
-----
  python3 inventory.py URL [URL ...] [options]

Options
-------
  --extras       also probe /robots.txt, /sitemap.xml,
                 /favicon.ico and a deliberately bad URL,
                 derived from the first URL's origin
  --delay SEC    seconds between requests (default 1.0)
  --timeout SEC  per-request timeout (default 20.0)
  --json         machine-readable output
  --agent STR    User-Agent header

Be polite. This hits somebody's production site.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_AGENT = "agent-he/1.0 (heuristic evaluation; +https://github.com/trycopilotai/agent-he)"

RATE_LIMIT_HEADERS = (
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "ratelimit-policy",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "retry-after",
)

# A raw entity that survived into rendered text is a
# double-escaping bug: `&amp;#8211;` decodes once to
# `&#8211;` and then prints literally.
RAW_ENTITY = re.compile(r"&(?:#\d{2,6}|#x[0-9a-fA-F]{2,6}|[a-zA-Z][a-zA-Z0-9]{1,31});")

_TAG = re.compile(r"<[^>]+>")
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META = re.compile(r"<meta\b([^>]*)>", re.IGNORECASE)
_LINK = re.compile(r"<link\b([^>]*)>", re.IGNORECASE)
_IMG = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
_ATTR = re.compile(r"([:A-Za-z_-][:A-Za-z0-9_.-]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")
_HEADING = re.compile(r"<h([1-6])\b", re.IGNORECASE)
_INLINE_SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)


def attributes(fragment):
    """Parse the attributes of one tag body into a dict."""
    found = {}
    for match in _ATTR.finditer(fragment):
        value = match.group(2)
        if value and value[0] in "\"'":
            value = value[1:-1]
        found[match.group(1).lower()] = value
    return found


def visible_text(markup):
    """Strip scripts, styles and tags; keep the text a reader sees."""
    stripped = _SCRIPT_OR_STYLE.sub(" ", markup)
    stripped = _TAG.sub(" ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def analyze_html(markup):
    """Everything pass one can learn from a page's source.

    Pure function — no network. Every field is either a fact
    about the bytes or a count.
    """
    report = {}

    html_match = _HTML_TAG.search(markup)
    if html_match:
        html_attrs = attributes(html_match.group(1))
        report["lang"] = html_attrs.get("lang")
        report["dir"] = html_attrs.get("dir")
    else:
        report["lang"] = None
        report["dir"] = None
    report["has_lang"] = bool(report["lang"])

    title_match = _TITLE.search(markup)
    if title_match:
        report["title"] = html.unescape(title_match.group(1)).strip()
    else:
        report["title"] = None

    metas = []
    for match in _META.finditer(markup):
        metas.append(attributes(match.group(1)))
    report["meta_count"] = len(metas)

    def meta_content(*keys):
        for meta in metas:
            name = meta.get("property") or meta.get("name") or ""
            if name.lower() in keys:
                return meta.get("content")
        return None

    report["description"] = meta_content("description")
    report["viewport"] = meta_content("viewport")
    report["has_viewport"] = bool(report["viewport"])

    open_graph = []
    twitter = []
    for meta in metas:
        name = (meta.get("property") or meta.get("name") or "").lower()
        if name.startswith("og:"):
            open_graph.append(name)
        if name.startswith("twitter:"):
            twitter.append(name)
    report["open_graph"] = sorted(set(open_graph))
    report["twitter_card"] = sorted(set(twitter))
    report["has_social_metadata"] = bool(open_graph or twitter)

    icons = []
    canonical = None
    for match in _LINK.finditer(markup):
        link = attributes(match.group(1))
        rel = (link.get("rel") or "").lower()
        if "icon" in rel:
            icons.append(link.get("href"))
        if rel == "canonical":
            canonical = link.get("href")
    report["icon_links"] = [href for href in icons if href]
    report["has_icon_link"] = bool(report["icon_links"])
    report["canonical"] = canonical

    images = []
    for match in _IMG.finditer(markup):
        images.append(attributes(match.group(1)))
    report["img_count"] = len(images)
    report["img_missing_alt"] = len([i for i in images if "alt" not in i])
    report["img_empty_alt"] = len([i for i in images if i.get("alt") == ""])

    headings = {}
    for match in _HEADING.finditer(markup):
        level = "h" + match.group(1)
        headings[level] = headings.get(level, 0) + 1
    report["headings"] = headings

    report["audio_count"] = len(re.findall(r"<audio\b", markup, re.IGNORECASE))
    report["video_count"] = len(re.findall(r"<video\b", markup, re.IGNORECASE))
    report["iframe_count"] = len(re.findall(r"<iframe\b", markup, re.IGNORECASE))
    report["form_count"] = len(re.findall(r"<form\b", markup, re.IGNORECASE))
    report["input_count"] = len(re.findall(r"<(?:input|select|textarea)\b", markup, re.IGNORECASE))
    report["button_count"] = len(re.findall(r"<button\b", markup, re.IGNORECASE))
    report["link_count"] = len(re.findall(r"<a\b[^>]*\bhref=", markup, re.IGNORECASE))

    inline_bytes = 0
    for match in _INLINE_SCRIPT.finditer(markup):
        inline_bytes += len(match.group(1).encode("utf-8"))
    report["inline_script_bytes"] = inline_bytes

    # Decode once, exactly as a browser does. An entity that
    # survives that decode was double-escaped at the source
    # and prints as machine text on the page.
    text = html.unescape(visible_text(markup))
    report["visible_text_bytes"] = len(text.encode("utf-8"))
    leaks = sorted(set(RAW_ENTITY.findall(text)))
    report["raw_entities_in_text"] = leaks
    report["has_entity_leak"] = bool(leaks)
    if report["title"]:
        report["raw_entities_in_title"] = sorted(set(RAW_ENTITY.findall(report["title"])))
    else:
        report["raw_entities_in_title"] = []

    return report


def analyze_robots(text):
    """Directive-bearing lines in a robots.txt, comments excluded."""
    directives = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        directives.append(stripped)
    return {
        "lines": len(text.splitlines()),
        "directive_count": len(directives),
        "directives": directives,
        "comments_only": len(directives) == 0 and len(text.strip()) > 0,
    }


def probe(url, timeout=20.0, agent=DEFAULT_AGENT):
    """Fetch one URL and describe what came back."""
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    record = {"url": url}
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            record["status"] = response.status
            headers = dict(response.headers.items())
            record["final_url"] = response.geturl()
    except urllib.error.HTTPError as error:
        body = error.read()
        record["status"] = error.code
        headers = dict(error.headers.items())
        record["final_url"] = url
    except Exception as error:  # network, DNS, TLS, timeout
        record["status"] = None
        record["error"] = "{0}: {1}".format(type(error).__name__, error)
        record["elapsed_ms"] = int((time.time() - started) * 1000)
        return record

    record["elapsed_ms"] = int((time.time() - started) * 1000)
    record["bytes"] = len(body)
    lowered = {key.lower(): value for key, value in headers.items()}
    record["content_type"] = lowered.get("content-type")
    record["redirected"] = record["final_url"] != url
    limits = {}
    for name in RATE_LIMIT_HEADERS:
        if name in lowered:
            limits[name] = lowered[name]
    record["rate_limit_headers"] = limits

    text = body.decode("utf-8", errors="replace")
    content_type = record["content_type"] or ""
    if "html" in content_type.lower() or text.lstrip()[:200].lower().startswith(("<!doctype html", "<html")):
        record["kind"] = "html"
        record["html"] = analyze_html(text)
    elif url.rstrip("/").endswith("robots.txt"):
        record["kind"] = "robots"
        record["robots"] = analyze_robots(text)
    else:
        record["kind"] = "other"
    return record


def extra_urls(first_url, bad_path="/agent-he-deliberately-missing/"):
    """The four probes every pass one should include."""
    parts = urllib.parse.urlsplit(first_url)
    origin = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return [
        origin + "/robots.txt",
        origin + "/sitemap.xml",
        origin + "/favicon.ico",
        origin + bad_path,
    ]


def _flag(condition, bad_text, good_text=""):
    if condition:
        return bad_text
    return good_text


def render_text(records):
    """Human-readable sweep summary."""
    lines = []
    for record in records:
        lines.append("=" * 68)
        lines.append(record["url"])
        if record.get("error"):
            lines.append("  ERROR  " + record["error"])
            continue
        summary = "  {0}  {1} bytes  {2} ms".format(
            record["status"], record.get("bytes", 0), record["elapsed_ms"]
        )
        lines.append(summary)
        if record.get("content_type"):
            lines.append("  content-type: " + record["content_type"])
        if record.get("redirected"):
            lines.append("  redirected to: " + record["final_url"])
        if record.get("rate_limit_headers"):
            for name in sorted(record["rate_limit_headers"]):
                lines.append("  {0}: {1}".format(name, record["rate_limit_headers"][name]))
        if record.get("status") == 200 and record.get("bytes") == 0:
            lines.append("  FINDING  200 with a zero-byte body")
        if record.get("status") == 404 and record.get("bytes") == 0:
            lines.append("  FINDING  404 with a zero-byte body — no error page")

        page = record.get("html")
        if page:
            if not page["has_lang"]:
                lines.append("  FINDING  <html> has no lang attribute (WCAG 3.1.1, Level A)")
            else:
                lines.append("  lang: " + str(page["lang"]))
            lines.append("  title: " + str(page["title"]))
            if page["raw_entities_in_title"]:
                lines.append(
                    "  FINDING  raw entities in the title: "
                    + ", ".join(page["raw_entities_in_title"])
                )
            if page["raw_entities_in_text"]:
                lines.append(
                    "  FINDING  raw entities in visible text: "
                    + ", ".join(page["raw_entities_in_text"][:8])
                )
            if not page["has_social_metadata"]:
                lines.append("  FINDING  no Open Graph or Twitter-card metadata")
            else:
                lines.append(
                    "  social: {0} og, {1} twitter".format(
                        len(page["open_graph"]), len(page["twitter_card"])
                    )
                )
            if not page["has_viewport"]:
                lines.append("  FINDING  no viewport meta tag")
            if not page["has_icon_link"]:
                lines.append("  note     no <link rel=icon>; check /favicon.ico")
            if page["img_missing_alt"]:
                lines.append(
                    "  FINDING  {0} of {1} <img> have no alt attribute".format(
                        page["img_missing_alt"], page["img_count"]
                    )
                )
            lines.append(
                "  counts: {0} links, {1} buttons, {2} inputs, {3} audio, "
                "{4} video, {5} iframe".format(
                    page["link_count"],
                    page["button_count"],
                    page["input_count"],
                    page["audio_count"],
                    page["video_count"],
                    page["iframe_count"],
                )
            )
            lines.append("  headings: " + json.dumps(page["headings"], sort_keys=True))
            lines.append("  inline script: {0} bytes".format(page["inline_script_bytes"]))

        robots = record.get("robots")
        if robots:
            lines.append(
                "  robots.txt: {0} lines, {1} directives".format(
                    robots["lines"], robots["directive_count"]
                )
            )
            if robots["comments_only"]:
                lines.append("  FINDING  robots.txt has comments and no directives")
    lines.append("=" * 68)
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="inventory.py",
        description="Pass-one page inventory for a heuristic evaluation.",
    )
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--extras", action="store_true", help="also probe robots, sitemap, favicon and a bad URL")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    targets = list(args.urls)
    if args.extras:
        for url in extra_urls(targets[0]):
            if url not in targets:
                targets.append(url)

    records = []
    for index, url in enumerate(targets):
        if index > 0 and args.delay > 0:
            time.sleep(args.delay)
        records.append(probe(url, timeout=args.timeout, agent=args.agent))

    if args.json:
        print(json.dumps(records, indent=2, sort_keys=True))
    else:
        print(render_text(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
