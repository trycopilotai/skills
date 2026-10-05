#!/usr/bin/env python3
"""Render assets/social-preview.png.

Every value on the card is read from the repository rather
than typed here: the marketplace name and the install line
come from .claude-plugin/marketplace.json, and the skill count
comes from catalogue.json. A card is the one surface nobody
looks at while working, so it is the one most likely to keep
advertising something that stopped being true.

Needs headless Chrome. Not wired into `make check`, because CI
has no browser; run it by hand after changing the marketplace
name or adding a skill, and commit the result.

    python3 assets/build.gpt.py
"""

import json
import subprocess
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent
ROOT = ASSETS.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

BG = "#0d1117"
FG = "#e6edf3"
DIM = "#8b949e"      # 6.15:1 on BG
BLUE = "#58a6ff"     # 7.49:1 on BG

FONT = (
    "ui-monospace, SFMono-Regular, Menlo, Monaco, "
    "'Cascadia Mono', 'Roboto Mono', monospace"
)

CARD = """<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ background:{bg}; width:1280px; height:640px; }}
  body {{ font-family:{font}; color:{fg}; display:flex;
    flex-direction:column; align-items:center;
    justify-content:center; text-align:center; }}
  .mark {{ width:132px; height:132px; margin-bottom:34px; }}
  h1 {{ font-size:96px; letter-spacing:-2px; font-weight:700; }}
  .tag {{ font-size:31px; margin-top:18px; font-weight:600; }}
  .cmd {{ font-size:26px; color:{blue}; margin-top:34px; }}
  .sub {{ font-size:23px; color:{dim}; margin-top:26px; }}
</style></head><body>
  <svg class="mark" viewBox="0 0 512 512" role="img" aria-label="skills">
    <rect width="512" height="512" rx="112" fill="#161b22"/>
    <rect x="4" y="4" width="504" height="504" rx="108"
          fill="none" stroke="#30363d" stroke-width="8"/>
    <rect x="112" y="112" width="128" height="128" rx="26" fill="#58a6ff"/>
    <rect x="272" y="112" width="128" height="128" rx="26" fill="#3fb950"/>
    <rect x="112" y="272" width="128" height="128" rx="26" fill="#d29922"/>
    <rect x="272" y="272" width="128" height="128" rx="26"
          fill="none" stroke="#8b949e" stroke-width="16"/>
  </svg>
  <h1>skills</h1>
  <div class="tag">{tagline}</div>
  <div class="cmd">/plugin marketplace add trycopilotai/skills</div>
  <div class="sub">github.com/trycopilotai/skills</div>
</body></html>
"""


def main() -> int:
    marketplace = json.loads(
        (ROOT / ".claude-plugin/marketplace.json").read_text())
    codex_marketplace = json.loads(
        (ROOT / ".agents/plugins/marketplace.json").read_text())
    catalogue = json.loads((ROOT / "catalogue.json").read_text())

    name = marketplace["name"]
    codex_name = codex_marketplace["name"]
    count = len(catalogue["skills"])
    pending = sum(s.get("status") != "published" for s in catalogue["skills"])
    tagline = "%d agent skill%s, pinned and checked." % (
        count, "" if count == 1 else "s") if not pending else "%d agent skills, %d upstream pending." % (count, pending)

    # The card prints one marketplace name for two client
    # files. If those ever disagree, the card is advertising a
    # name that only half the readers can install from.
    if name != codex_name:
        raise SystemExit(
            "marketplace names disagree: %r in .claude-plugin, %r in "
            ".agents/plugins" % (name, codex_name))

    if name != "trycopilotai":
        raise SystemExit(
            "marketplace name is %r; the card's install line is written "
            "for trycopilotai and would be wrong" % name)

    ASSETS.mkdir(exist_ok=True)
    src = ASSETS / "_card.html"
    out = ASSETS / "social-preview.png"
    src.write_text(
        CARD.format(bg=BG, fg=FG, dim=DIM, blue=BLUE, font=FONT,
                    tagline=tagline),
        encoding="utf-8")
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=1", "--screenshot=" + str(out),
         "--window-size=1280,640", "file://" + str(src)],
        check=True, capture_output=True)
    src.unlink()
    print("wrote %s (%s, %d skill%s)"
          % (out.name, name, count, "" if count == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
