#!/usr/bin/env python3
"""Validate the marketplace catalogue and every skill it ships.

Checks, in order:
  1. marketplace.json parses and has name, owner, plugins.
  2. The marketplace name is kebab-case and not reserved.
  3. Every plugin entry has name and source, and the source
     resolves on disk when it is a relative path.
  4. Every plugin has .claude-plugin/plugin.json.
  5. Every SKILL.md frontmatter satisfies the Agent Skills
     spec, including the rule that name matches its
     directory.
  6. Every vendored skill still matches the sha256 recorded
     in meta/, so an upstream copy cannot rot silently.

Exits non-zero on the first category with failures.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Reserved by Anthropic; re-checked on every marketplace load.
RESERVED = {
    "claude-code-marketplace", "claude-code-plugins",
    "claude-plugins-official", "claude-plugins-community",
    "claude-community", "anthropic-marketplace", "anthropic-plugins",
    "agent-skills", "anthropic-agent-skills", "knowledge-work-plugins",
    "life-sciences", "claude-for-legal",
    "claude-for-financial-services", "financial-services-plugins",
    "first-party-plugins", "healthcare",
}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

errors: list[str] = []
checks = 0


def check(condition: bool, message: str) -> bool:
    global checks
    checks += 1
    if not condition:
        errors.append(message)
        return False
    return True


def frontmatter(path: Path) -> dict:
    """Parse the leading YAML block without a yaml dependency."""
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}
    body = text.split("---\n", 2)
    if len(body) < 3:
        return {}
    out: dict[str, str] = {}
    key = None
    for line in body[1].split("\n"):
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key = m.group(1)
            out[key] = m.group(2).strip()
        elif key and line.startswith(" "):
            out[key] = (out.get(key, "") + " " + line.strip()).strip()
    return out


def main() -> int:
    mkt_path = ROOT / ".claude-plugin/marketplace.json"
    if not check(mkt_path.exists(), "missing .claude-plugin/marketplace.json"):
        print("\n".join(errors))
        return 1
    mkt = json.loads(mkt_path.read_text())

    for field in ("name", "owner", "plugins"):
        check(field in mkt, f"marketplace.json missing required field {field!r}")
    name = mkt.get("name", "")
    check(bool(NAME_RE.match(name)), f"marketplace name {name!r} is not kebab-case")
    check(name not in RESERVED, f"marketplace name {name!r} is reserved by Anthropic")
    check("name" in mkt.get("owner", {}), "marketplace owner is missing a name")

    plugin_root = mkt.get("metadata", {}).get("pluginRoot", ".")
    for entry in mkt.get("plugins", []):
        pname = entry.get("name", "<unnamed>")
        check("name" in entry, f"plugin entry {entry!r} has no name")
        check("source" in entry, f"plugin {pname!r} has no source")
        check(
            bool(NAME_RE.match(pname)),
            f"plugin name {pname!r} is not kebab-case",
        )

        src = entry.get("source")
        if not isinstance(src, str):
            # Remote sources must be pinned to a tag or a commit.
            check(
                "ref" in src or "sha" in src,
                f"plugin {pname!r} has a remote source with no ref or sha pin",
            )
            continue

        pdir = (ROOT / plugin_root / src.removeprefix("./")).resolve()
        if not check(pdir.is_dir(), f"plugin {pname!r} source does not exist: {pdir}"):
            continue
        check(
            (pdir / ".claude-plugin/plugin.json").exists(),
            f"plugin {pname!r} is missing .claude-plugin/plugin.json",
        )

        for skill_md in sorted((pdir / "skills").glob("*/SKILL.md")):
            sdir = skill_md.parent.name
            fm = frontmatter(skill_md)
            check(bool(fm), f"{skill_md.relative_to(ROOT)} has no frontmatter")
            sname = fm.get("name", "")
            check(
                bool(NAME_RE.match(sname)),
                f"{sdir}: skill name {sname!r} violates the naming rules",
            )
            check(len(sname) <= 64, f"{sdir}: skill name is over 64 characters")
            check(
                sname == sdir,
                f"{sdir}: frontmatter name {sname!r} must match its directory",
            )
            desc = fm.get("description", "")
            check(bool(desc), f"{sdir}: description is empty")
            check(
                len(desc) <= 1024,
                f"{sdir}: description is {len(desc)} chars, over the 1024 limit",
            )
            lines = len(skill_md.read_text().splitlines())
            check(lines <= 500, f"{sdir}: SKILL.md is {lines} lines, over the 500 guideline")

    # Display order must be explicit, numeric, and unambiguous.
    # Without this the catalogue silently falls back to
    # alphabetical the first time someone forgets the key.
    seen_order: dict[int, str] = {}
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        raw = fm.get("order", "")
        if not check(raw != "", f"{meta.name}: missing required 'order'"):
            continue
        if not check(
            raw.lstrip("-").isdigit(),
            f"{meta.name}: order must be an integer, got {raw!r}",
        ):
            continue
        value = int(raw)
        check(
            value not in seen_order,
            f"{meta.name}: order {value} already used by "
            f"{seen_order.get(value, '')}",
        )
        seen_order.setdefault(value, meta.name)

    # Vendored copies must match the sha256 recorded in meta/.
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        vp, want = fm.get("vendored_path"), fm.get("vendored_sha256")
        if not (vp and want):
            continue
        f = ROOT / vp
        if not check(f.exists(), f"{meta.name}: vendored_path missing: {vp}"):
            continue
        got = hashlib.sha256(f.read_bytes()).hexdigest()
        check(
            got == want,
            f"{meta.name}: {vp} drifted from upstream.\n"
            f"      recorded {want[:16]}…, on disk {got[:16]}…\n"
            f"      run `make sync` then commit, or correct vendored_sha256",
        )

    if errors:
        print(f"FAIL  {len(errors)} of {checks} checks\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK    {checks} checks passed")
    return 0


def frontmatter_yaml(path: Path) -> dict:
    """meta/*.skill.yml is a bare mapping with no --- fences."""
    out: dict[str, str] = {}
    for line in path.read_text().split("\n"):
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


if __name__ == "__main__":
    sys.exit(main())
