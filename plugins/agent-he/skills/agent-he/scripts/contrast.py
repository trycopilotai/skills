#!/usr/bin/env python3
"""WCAG contrast arithmetic for a heuristic evaluation.

Contrast is measured, never eyeballed. This computes the
relative-luminance ratio defined by WCAG 2.x and reports it
against the thresholds that matter:

  4.5:1  normal text                 (1.4.3, AA)
  3.0:1  large text                  (1.4.3, AA)
  3.0:1  UI component boundaries and
         graphical objects           (1.4.11, AA)
  7.0:1  normal text                 (1.4.6, AAA)
  4.5:1  large text                  (1.4.6, AAA)

Standard library only.

Subcommands
-----------
  ratio FG BG            one pair
  vars FILE              extract CSS custom properties
  matrix FILE            cross product of custom properties

Examples
--------
  python3 contrast.py ratio '#6b7280' '#ffffff'
  python3 contrast.py vars site.css
  python3 contrast.py matrix site.css --fg ink,muted --bg bg,surface
  python3 contrast.py matrix site.css --all --min 3.0
  python3 contrast.py matrix site.css --scope dark --min 4.5

Measure both themes. A palette that passes in light can
fail in dark, and the source stylesheet holds both.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# --------------------------------------------------------------------------
# Colour parsing
# --------------------------------------------------------------------------

NAMED_COLORS = {
    "aliceblue": "#f0f8ff",
    "antiquewhite": "#faebd7",
    "aqua": "#00ffff",
    "aquamarine": "#7fffd4",
    "azure": "#f0ffff",
    "beige": "#f5f5dc",
    "bisque": "#ffe4c4",
    "black": "#000000",
    "blanchedalmond": "#ffebcd",
    "blue": "#0000ff",
    "blueviolet": "#8a2be2",
    "brown": "#a52a2a",
    "burlywood": "#deb887",
    "cadetblue": "#5f9ea0",
    "chartreuse": "#7fff00",
    "chocolate": "#d2691e",
    "coral": "#ff7f50",
    "cornflowerblue": "#6495ed",
    "cornsilk": "#fff8dc",
    "crimson": "#dc143c",
    "cyan": "#00ffff",
    "darkblue": "#00008b",
    "darkcyan": "#008b8b",
    "darkgoldenrod": "#b8860b",
    "darkgray": "#a9a9a9",
    "darkgreen": "#006400",
    "darkgrey": "#a9a9a9",
    "darkkhaki": "#bdb76b",
    "darkmagenta": "#8b008b",
    "darkolivegreen": "#556b2f",
    "darkorange": "#ff8c00",
    "darkorchid": "#9932cc",
    "darkred": "#8b0000",
    "darksalmon": "#e9967a",
    "darkseagreen": "#8fbc8f",
    "darkslateblue": "#483d8b",
    "darkslategray": "#2f4f4f",
    "darkslategrey": "#2f4f4f",
    "darkturquoise": "#00ced1",
    "darkviolet": "#9400d3",
    "deeppink": "#ff1493",
    "deepskyblue": "#00bfff",
    "dimgray": "#696969",
    "dimgrey": "#696969",
    "dodgerblue": "#1e90ff",
    "firebrick": "#b22222",
    "floralwhite": "#fffaf0",
    "forestgreen": "#228b22",
    "fuchsia": "#ff00ff",
    "gainsboro": "#dcdcdc",
    "ghostwhite": "#f8f8ff",
    "gold": "#ffd700",
    "goldenrod": "#daa520",
    "gray": "#808080",
    "green": "#008000",
    "greenyellow": "#adff2f",
    "grey": "#808080",
    "honeydew": "#f0fff0",
    "hotpink": "#ff69b4",
    "indianred": "#cd5c5c",
    "indigo": "#4b0082",
    "ivory": "#fffff0",
    "khaki": "#f0e68c",
    "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5",
    "lawngreen": "#7cfc00",
    "lemonchiffon": "#fffacd",
    "lightblue": "#add8e6",
    "lightcoral": "#f08080",
    "lightcyan": "#e0ffff",
    "lightgoldenrodyellow": "#fafad2",
    "lightgray": "#d3d3d3",
    "lightgreen": "#90ee90",
    "lightgrey": "#d3d3d3",
    "lightpink": "#ffb6c1",
    "lightsalmon": "#ffa07a",
    "lightseagreen": "#20b2aa",
    "lightskyblue": "#87cefa",
    "lightslategray": "#778899",
    "lightslategrey": "#778899",
    "lightsteelblue": "#b0c4de",
    "lightyellow": "#ffffe0",
    "lime": "#00ff00",
    "limegreen": "#32cd32",
    "linen": "#faf0e6",
    "magenta": "#ff00ff",
    "maroon": "#800000",
    "mediumaquamarine": "#66cdaa",
    "mediumblue": "#0000cd",
    "mediumorchid": "#ba55d3",
    "mediumpurple": "#9370db",
    "mediumseagreen": "#3cb371",
    "mediumslateblue": "#7b68ee",
    "mediumspringgreen": "#00fa9a",
    "mediumturquoise": "#48d1cc",
    "mediumvioletred": "#c71585",
    "midnightblue": "#191970",
    "mintcream": "#f5fffa",
    "mistyrose": "#ffe4e1",
    "moccasin": "#ffe4b5",
    "navajowhite": "#ffdead",
    "navy": "#000080",
    "oldlace": "#fdf5e6",
    "olive": "#808000",
    "olivedrab": "#6b8e23",
    "orange": "#ffa500",
    "orangered": "#ff4500",
    "orchid": "#da70d6",
    "palegoldenrod": "#eee8aa",
    "palegreen": "#98fb98",
    "paleturquoise": "#afeeee",
    "palevioletred": "#db7093",
    "papayawhip": "#ffefd5",
    "peachpuff": "#ffdab9",
    "peru": "#cd853f",
    "pink": "#ffc0cb",
    "plum": "#dda0dd",
    "powderblue": "#b0e0e6",
    "purple": "#800080",
    "rebeccapurple": "#663399",
    "red": "#ff0000",
    "rosybrown": "#bc8f8f",
    "royalblue": "#4169e1",
    "saddlebrown": "#8b4513",
    "salmon": "#fa8072",
    "sandybrown": "#f4a460",
    "seagreen": "#2e8b57",
    "seashell": "#fff5ee",
    "sienna": "#a0522d",
    "silver": "#c0c0c0",
    "skyblue": "#87ceeb",
    "slateblue": "#6a5acd",
    "slategray": "#708090",
    "slategrey": "#708090",
    "snow": "#fffafa",
    "springgreen": "#00ff7f",
    "steelblue": "#4682b4",
    "tan": "#d2b48c",
    "teal": "#008080",
    "thistle": "#d8bfd8",
    "tomato": "#ff6347",
    "turquoise": "#40e0d0",
    "violet": "#ee82ee",
    "wheat": "#f5deb3",
    "white": "#ffffff",
    "whitesmoke": "#f5f5f5",
    "yellow": "#ffff00",
    "yellowgreen": "#9acd32",
}

_HEX = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_FUNC = re.compile(r"^(rgba?|hsla?)\s*\(([^)]*)\)$", re.IGNORECASE)


class ColorError(ValueError):
    """Raised when a colour string cannot be parsed."""


def _clamp(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _parse_channel(token, scale=255.0):
    token = token.strip()
    if token.endswith("%"):
        return _clamp(float(token[:-1]) / 100.0 * 255.0, 0.0, 255.0)
    return _clamp(float(token) * (255.0 / scale), 0.0, 255.0)


def _parse_alpha(token):
    token = token.strip()
    if token.endswith("%"):
        return _clamp(float(token[:-1]) / 100.0, 0.0, 1.0)
    return _clamp(float(token), 0.0, 1.0)


def _hsl_to_rgb(hue, sat, light):
    hue = hue % 360.0
    chroma = (1.0 - abs(2.0 * light - 1.0)) * sat
    second = chroma * (1.0 - abs((hue / 60.0) % 2.0 - 1.0))
    match = light - chroma / 2.0
    if hue < 60.0:
        red, green, blue = chroma, second, 0.0
    elif hue < 120.0:
        red, green, blue = second, chroma, 0.0
    elif hue < 180.0:
        red, green, blue = 0.0, chroma, second
    elif hue < 240.0:
        red, green, blue = 0.0, second, chroma
    elif hue < 300.0:
        red, green, blue = second, 0.0, chroma
    else:
        red, green, blue = chroma, 0.0, second
    return (
        (red + match) * 255.0,
        (green + match) * 255.0,
        (blue + match) * 255.0,
    )


def parse_color(text):
    """Parse a CSS colour into an (r, g, b, a) tuple.

    Channels are 0-255 floats; alpha is a 0-1 float.
    Accepts #rgb, #rgba, #rrggbb, #rrggbbaa, rgb(), rgba(),
    hsl(), hsla(), CSS named colours and `transparent`.
    """
    if text is None:
        raise ColorError("no colour given")
    raw = str(text).strip()
    if not raw:
        raise ColorError("empty colour")
    lowered = raw.lower()
    if lowered == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if lowered in NAMED_COLORS:
        raw = NAMED_COLORS[lowered]
        lowered = raw

    hex_match = _HEX.match(raw)
    if hex_match:
        digits = hex_match.group(1)
        if len(digits) in (3, 4):
            digits = "".join(char * 2 for char in digits)
        if len(digits) not in (6, 8):
            raise ColorError("bad hex colour: " + raw)
        red = int(digits[0:2], 16)
        green = int(digits[2:4], 16)
        blue = int(digits[4:6], 16)
        alpha = 1.0
        if len(digits) == 8:
            alpha = int(digits[6:8], 16) / 255.0
        return (float(red), float(green), float(blue), alpha)

    func_match = _FUNC.match(raw)
    if func_match:
        name = func_match.group(1).lower()
        body = func_match.group(2).replace("/", " ").replace(",", " ")
        parts = [item for item in body.split() if item]
        if len(parts) < 3:
            raise ColorError("bad colour function: " + raw)
        alpha = 1.0
        if len(parts) >= 4:
            alpha = _parse_alpha(parts[3])
        if name.startswith("rgb"):
            red = _parse_channel(parts[0])
            green = _parse_channel(parts[1])
            blue = _parse_channel(parts[2])
            return (red, green, blue, alpha)
        hue_token = parts[0].replace("deg", "")
        hue = float(hue_token)
        sat = float(parts[1].rstrip("%")) / 100.0
        light = float(parts[2].rstrip("%")) / 100.0
        red, green, blue = _hsl_to_rgb(hue, sat, light)
        return (red, green, blue, alpha)

    raise ColorError("unrecognised colour: " + raw)


def composite(fg, bg):
    """Composite a translucent foreground over an opaque background."""
    alpha = fg[3]
    if alpha >= 1.0:
        return (fg[0], fg[1], fg[2], 1.0)
    return (
        fg[0] * alpha + bg[0] * (1.0 - alpha),
        fg[1] * alpha + bg[1] * (1.0 - alpha),
        fg[2] * alpha + bg[2] * (1.0 - alpha),
        1.0,
    )


# --------------------------------------------------------------------------
# WCAG arithmetic
# --------------------------------------------------------------------------


def _linearize(channel):
    srgb = channel / 255.0
    if srgb <= 0.04045:
        return srgb / 12.92
    return ((srgb + 0.055) / 1.055) ** 2.4


def relative_luminance(color):
    """WCAG 2.x relative luminance of an (r, g, b, a) colour."""
    red = _linearize(color[0])
    green = _linearize(color[1])
    blue = _linearize(color[2])
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(fg, bg):
    """Contrast ratio between two colours, foreground first.

    A translucent foreground is composited over the
    background before the ratio is taken, which is what a
    browser does.
    """
    if isinstance(bg, str):
        background = parse_color(bg)
    else:
        background = bg
    if isinstance(fg, str):
        foreground = parse_color(fg)
    else:
        foreground = fg
    if background[3] < 1.0:
        background = composite(background, (255.0, 255.0, 255.0, 1.0))
    foreground = composite(foreground, background)
    lum_fg = relative_luminance(foreground)
    lum_bg = relative_luminance(background)
    lighter = max(lum_fg, lum_bg)
    darker = min(lum_fg, lum_bg)
    return (lighter + 0.05) / (darker + 0.05)


THRESHOLDS = (
    ("AA normal text (1.4.3)", 4.5),
    ("AA large text (1.4.3)", 3.0),
    ("AA non-text / UI boundary (1.4.11)", 3.0),
    ("AAA normal text (1.4.6)", 7.0),
    ("AAA large text (1.4.6)", 4.5),
)


def verdicts(ratio):
    """Pass/fail against each WCAG threshold, as a dict."""
    result = {}
    for label, minimum in THRESHOLDS:
        result[label] = ratio >= minimum
    return result


# --------------------------------------------------------------------------
# CSS custom properties
# --------------------------------------------------------------------------

_CUSTOM_PROP = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;{}]*)")
_VAR_REF = re.compile(r"var\(\s*--([A-Za-z0-9_-]+)\s*(?:,([^)]*))?\)")
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _declarations(body):
    found = {}
    for chunk in body.split(";"):
        match = _CUSTOM_PROP.match(chunk.strip())
        if match:
            found[match.group(1)] = match.group(2).strip()
    return found


def extract_blocks(css):
    """Split a stylesheet into its declaration blocks.

    Returns a list of dicts with `at` (the enclosing at-rule
    preludes, outermost first), `selector`, and
    `properties` (custom properties only). Blocks that
    declare no custom property are dropped.

    Themed stylesheets declare the same custom property
    several times — once on `:root`, again under
    `[data-theme="dark"]` or a `prefers-color-scheme` media
    query. Flattening them would silently mix the two
    palettes, so they are kept apart here and selected with
    `scope` below.
    """
    text = _COMMENT.sub(" ", css)
    blocks = []
    stack = []
    buffer = []
    for char in text:
        if char == "{":
            stack.append("".join(buffer).strip())
            buffer = []
            continue
        if char == "}":
            if stack:
                properties = _declarations("".join(buffer))
                if properties:
                    blocks.append(
                        {
                            "at": [item for item in stack[:-1] if item],
                            "selector": " ".join(stack[-1].split()),
                            "properties": properties,
                        }
                    )
                stack.pop()
            buffer = []
            continue
        buffer.append(char)
    return blocks


def extract_custom_properties(css, scope=None):
    """Custom properties in effect for a given theme scope.

    With no `scope`, only the base block is applied — the
    selector of the first block that declares a custom
    property, which is `:root` in practice. Pass `scope` to
    layer every block whose at-rule prelude or selector
    mentions it (`--scope dark` picks up both
    `[data-theme="dark"]` and `prefers-color-scheme: dark`).
    """
    blocks = extract_blocks(css)
    if not blocks:
        return {}
    base_selector = blocks[0]["selector"]
    merged = {}
    for block in blocks:
        if block["at"]:
            continue
        if block["selector"] != base_selector:
            continue
        merged.update(block["properties"])
    if scope is None:
        return merged
    needle = scope.lower()
    for block in blocks:
        context = " ".join(block["at"]) + " " + block["selector"]
        if needle in context.lower():
            merged.update(block["properties"])
    return merged


def resolve_var(name, properties, depth=0):
    """Resolve a custom property, following `var()` chains."""
    if depth > 16:
        raise ColorError("var() chain too deep at --" + name)
    if name not in properties:
        raise ColorError("no such custom property: --" + name)
    value = properties[name]
    match = _VAR_REF.search(value)
    if not match:
        return value
    target = match.group(1)
    if target in properties:
        return resolve_var(target, properties, depth + 1)
    fallback = match.group(2)
    if fallback is None:
        raise ColorError("unresolvable var(--" + target + ")")
    return fallback.strip()


def color_properties(css, scope=None):
    """Custom properties whose value parses as a colour."""
    properties = extract_custom_properties(css, scope=scope)
    colors = {}
    for name in properties:
        try:
            value = resolve_var(name, properties)
            parse_color(value)
        except (ColorError, ValueError):
            continue
        colors[name] = value
    return colors


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _format_ratio(ratio):
    return "{0:.2f}:1".format(ratio)


def _cmd_ratio(args):
    ratio = contrast_ratio(args.foreground, args.background)
    if args.json:
        payload = {
            "foreground": args.foreground,
            "background": args.background,
            "ratio": round(ratio, 4),
            "verdicts": verdicts(ratio),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print("{0} on {1}".format(args.foreground, args.background))
    print("  ratio: " + _format_ratio(ratio))
    for label, minimum in THRESHOLDS:
        if ratio >= minimum:
            mark = "PASS"
        else:
            mark = "FAIL"
        print("  {0:<38} {1} (needs {2:.1f}:1)".format(label, mark, minimum))
    return 0


def _cmd_vars(args):
    colors = color_properties(_read(args.file), scope=args.scope)
    if args.json:
        print(json.dumps(colors, indent=2, sort_keys=True))
        return 0
    if not colors:
        print("no colour-valued custom properties found")
        return 0
    width = max(len(name) for name in colors)
    for name in sorted(colors):
        print("--{0:<{1}}  {2}".format(name, width, colors[name]))
    return 0


def _split_list(text):
    if text is None:
        return None
    return [item.strip() for item in text.split(",") if item.strip()]


def _cmd_matrix(args):
    colors = color_properties(_read(args.file), scope=args.scope)
    if not colors:
        print("no colour-valued custom properties found", file=sys.stderr)
        return 1
    names = sorted(colors)
    foregrounds = _split_list(args.fg)
    backgrounds = _split_list(args.bg)
    if foregrounds is None:
        foregrounds = names
    if backgrounds is None:
        backgrounds = names
    missing = [n for n in foregrounds + backgrounds if n not in colors]
    if missing:
        print("unknown custom properties: " + ", ".join(missing), file=sys.stderr)
        return 1

    rows = []
    for fg_name in foregrounds:
        for bg_name in backgrounds:
            if fg_name == bg_name:
                continue
            ratio = contrast_ratio(colors[fg_name], colors[bg_name])
            if args.min is not None and ratio >= args.min:
                continue
            rows.append(
                {
                    "foreground": fg_name,
                    "foreground_value": colors[fg_name],
                    "background": bg_name,
                    "background_value": colors[bg_name],
                    "ratio": round(ratio, 4),
                    "verdicts": verdicts(ratio),
                }
            )
    rows.sort(key=lambda row: row["ratio"])

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("no pairs to report")
        return 0
    print("| foreground | background | ratio | AA text | AA large/UI | AAA text |")
    print("| ---------- | ---------- | ----- | ------- | ----------- | -------- |")
    for row in rows:
        ratio = row["ratio"]
        print(
            "| --{0} | --{1} | {2} | {3} | {4} | {5} |".format(
                row["foreground"],
                row["background"],
                _format_ratio(ratio),
                _mark(ratio >= 4.5),
                _mark(ratio >= 3.0),
                _mark(ratio >= 7.0),
            )
        )
    return 0


def _mark(passed):
    if passed:
        return "pass"
    return "**FAIL**"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="contrast.py",
        description="WCAG contrast arithmetic for heuristic evaluation.",
    )
    sub = parser.add_subparsers(dest="command")

    ratio = sub.add_parser("ratio", help="contrast ratio of one pair")
    ratio.add_argument("foreground")
    ratio.add_argument("background")
    ratio.add_argument("--json", action="store_true")
    ratio.set_defaults(func=_cmd_ratio)

    variables = sub.add_parser("vars", help="colour custom properties in a file")
    variables.add_argument("file", help="CSS or HTML file, or - for stdin")
    variables.add_argument(
        "--scope",
        help="theme scope to layer on the base block, e.g. dark",
    )
    variables.add_argument("--json", action="store_true")
    variables.set_defaults(func=_cmd_vars)

    matrix = sub.add_parser("matrix", help="cross product of custom properties")
    matrix.add_argument("file", help="CSS or HTML file, or - for stdin")
    matrix.add_argument(
        "--scope",
        help="theme scope to layer on the base block, e.g. dark",
    )
    matrix.add_argument("--fg", help="comma-separated property names")
    matrix.add_argument("--bg", help="comma-separated property names")
    matrix.add_argument("--all", action="store_true", help="every pair (the default)")
    matrix.add_argument(
        "--min",
        type=float,
        help="only report pairs below this ratio",
    )
    matrix.add_argument("--json", action="store_true")
    matrix.set_defaults(func=_cmd_matrix)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except ColorError as error:
        print("error: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
