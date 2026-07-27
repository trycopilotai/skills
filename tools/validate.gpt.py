#!/usr/bin/env python3
"""Validate the marketplace catalogue and every skill it ships.

Checks, in order:
  1. marketplace.json parses and has name, owner, plugins.
  2. The marketplace name is kebab-case and not reserved.
  3. Every plugin entry has name and source, and the source
     resolves on disk when it is a relative path.
  4. Every plugin has a .claude-plugin/plugin.json that parses
     and carries the fields a client reads.
  5. Every SKILL.md frontmatter satisfies the Agent Skills
     spec, including the rule that name matches its
     directory.
  6. Every meta/ entry declares an explicit display order and
     honest side-effect flags.
  7. meta/ and marketplace.json agree, so the two copies of
     each skill's name, licence, and description cannot drift.
  8. Every vendored skill still matches the sha256 recorded
     in meta/, so an upstream copy cannot rot silently.

Exits non-zero on the first category with failures.
"""

import hashlib
import importlib.util
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

# What a skill is allowed to do. Every skill declares all three,
# because an omitted flag renders as "read-only" in the index and
# an unearned read-only badge is worse than no badge.
SIDE_EFFECTS = ("writes", "network", "executes")

# Fields plugin.json must carry for a client to render the entry.
PLUGIN_JSON_FIELDS = ("name", "version", "description", "license")

errors: list[str] = []
checks = 0


def _load_paths():
    """Import tools/paths.gpt.py, whose name is not importable."""
    spec = importlib.util.spec_from_file_location(
        "skills_paths", Path(__file__).resolve().parent / "paths.gpt.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PATHS = _load_paths()


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
    try:
        mkt = json.loads(mkt_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"FAIL  .claude-plugin/marketplace.json does not parse: {exc}")
        return 1

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
        check(
            bool(NAME_RE.match(pname)),
            f"plugin name {pname!r} is not kebab-case",
        )

        # A missing source is reported, not dereferenced. Falling
        # through to `"ref" in src` with src=None raises TypeError
        # and takes the whole validator down, so the one entry
        # that most needs reporting is the one that hides every
        # other error behind a traceback.
        if not check("source" in entry, f"plugin {pname!r} has no source"):
            continue
        src = entry.get("source")

        if isinstance(src, dict):
            # Remote sources must be pinned to a tag or a commit.
            check(
                "ref" in src or "sha" in src,
                f"plugin {pname!r} has a remote source with no ref or sha pin",
            )
            continue
        if not isinstance(src, str):
            check(
                False,
                f"plugin {pname!r} has a source of unsupported type "
                f"{type(src).__name__}; expected a path or an object",
            )
            continue

        pdir = (ROOT / plugin_root / src.removeprefix("./")).resolve()
        if not check(pdir.is_dir(), f"plugin {pname!r} source does not exist: {pdir}"):
            continue

        pj = pdir / ".claude-plugin/plugin.json"
        if check(
            pj.exists(),
            f"plugin {pname!r} is missing .claude-plugin/plugin.json",
        ):
            try:
                manifest = json.loads(pj.read_text())
            except json.JSONDecodeError as exc:
                check(False, f"plugin {pname!r}: plugin.json does not parse: {exc}")
                manifest = None
            if isinstance(manifest, dict):
                for field in PLUGIN_JSON_FIELDS:
                    check(
                        bool(str(manifest.get(field, "")).strip()),
                        f"plugin {pname!r}: plugin.json has no {field!r}",
                    )
                check(
                    manifest.get("name") == pname,
                    f"plugin {pname!r}: plugin.json name is "
                    f"{manifest.get('name')!r}, which disagrees with the "
                    f"marketplace entry",
                )
            elif manifest is not None:
                check(False, f"plugin {pname!r}: plugin.json is not an object")

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

    # Side-effect flags decide the badge the index prints. An
    # absent or misspelled flag reads as false, so a skill that
    # runs commands would advertise itself as read-only.
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        for flag in SIDE_EFFECTS:
            raw = fm.get(flag)
            if not check(
                raw is not None,
                f"{meta.name}: missing required side-effect flag {flag!r}. "
                f"An omitted flag renders as read-only.",
            ):
                continue
            check(
                raw in ("true", "false"),
                f"{meta.name}: {flag!r} must be true or false, got {raw!r}",
            )

    # meta/ and marketplace.json each carry a copy of the same
    # three facts. Two copies drift; this is what notices.
    entries = {
        e.get("name"): e for e in mkt.get("plugins", []) if e.get("name")
    }
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        sname = fm.get("name", "")
        if not check(
            sname in entries,
            f"{meta.name}: name {sname!r} has no plugin entry in "
            f"marketplace.json",
        ):
            continue
        entry = entries[sname]
        check(
            entry.get("license", "") == fm.get("license", ""),
            f"{meta.name}: license {fm.get('license')!r} disagrees with "
            f"marketplace.json's {entry.get('license')!r}",
        )
        check(
            entry.get("description", "").strip() == fm.get("use", "").strip(),
            f"{meta.name}: 'use' disagrees with the marketplace.json "
            f"description for {sname!r}. They are two copies of one "
            f"sentence; edit meta/ and re-copy.",
        )

    # Vendored copies must match the sha256 recorded in meta/.
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        vp, want = fm.get("vendored_path"), fm.get("vendored_sha256")
        if not (vp and want):
            continue
        try:
            f = PATHS.resolve_vendored(ROOT, vp, source=meta.name)
        except PATHS.UnsafePath as exc:
            check(False, str(exc))
            continue
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
    key = None
    for line in path.read_text().split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Fold a block scalar's continuation lines into its key,
        # so a `use: >-` body is comparable with the one-line
        # description marketplace.json holds.
        if line.startswith("  ") and key and not line.startswith("  - "):
            out[key] = (out.get(key, "") + " " + line.strip()).strip()
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            out[key] = "" if val in (">-", ">", "|", "|-") else val
    return out


if __name__ == "__main__":
    sys.exit(main())
