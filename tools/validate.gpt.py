#!/usr/bin/env python3
"""Validate the marketplace catalogue and every skill it ships.

Checks, in order:
  1. Both marketplace files parse, and the Claude Code one
     has name, owner, plugins.
  2. The marketplace names agree, are kebab-case, and are not
     reserved.
  3. Every plugin entry has name and source, and the source
     resolves on disk when it is a relative path.
  4. Every plugin has a .claude-plugin/plugin.json that parses
     and carries the fields a client reads, plus a matching
     .codex-plugin/plugin.json when it claims Codex.
  5. Every SKILL.md frontmatter satisfies the Agent Skills
     spec, including the rule that name matches its
     directory.
  6. Every meta/ entry declares an explicit display order,
     honest side-effect flags, a worked example, and the
     clients it actually ships for.
  7. meta/ and marketplace.json agree, so the copies of each
     skill's name, licence, and description cannot drift.
  8. Every vendored skill file or package still matches the
     sha256 recorded in meta/, so an upstream copy cannot rot
     silently.

Exits non-zero on the first category with failures.
"""

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

# Refs that move. A pin to one of these is not a pin.
MUTABLE_REFS = {"main", "master", "HEAD", "trunk", "develop", "dev"}

# A skill is either listed as shipping, or listed as not yet
# shipping. Anything else is a status nobody defined, and the
# generated index would print it verbatim to readers.
STATUSES = {"published", "pending-publication"}

# The literal that stands in for a commit id that does not
# exist yet. It is allowed only for an entry that also says it
# is not published, and tools/release_gate.gpt.py is what stops
# such an entry from shipping.
UNRESOLVED = "UNRESOLVED"

# The clients this marketplace can install into. Claude Code is
# not optional: this repository is a Claude Code marketplace
# that Codex can also read, so an entry that dropped it would
# have no home for its own plugin source.
CLIENTS = ("claude-code", "codex")
REQUIRED_CLIENT = "claude-code"

# What a skill is allowed to do. Every skill declares all three,
# because an omitted flag renders as "read-only" in the index and
# an unearned read-only badge is worse than no badge.
SIDE_EFFECTS = ("writes", "network", "executes")

# Fields plugin.json must carry for a client to render the entry.
PLUGIN_JSON_FIELDS = ("name", "version", "description", "license")

# What Codex reads in addition, to render a plugin in its own
# installer rather than just load it.
CODEX_INTERFACE_FIELDS = (
    "displayName", "shortDescription", "longDescription",
    "developerName", "category", "websiteURL",
)
CODEX_POLICY = {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}

# The per-skill file Codex reads for its invocation surface.
OPENAI_INTERFACE_FIELDS = (
    "display_name", "short_description", "default_prompt",
)

errors: list[str] = []
checks = 0


def _load_sibling(filename, name):
    """Import a tools/ module whose name is not importable."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PATHS = _load_sibling("paths.gpt.py", "skills_paths")
PACKAGE_DIGEST = _load_sibling("package_digest.gpt.py", "package_digest")


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


def load_json_object(path: Path, label: str) -> dict | None:
    """Load a JSON object, reporting parse and shape failures."""
    if not check(path.exists(), f"missing {label}"):
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        check(False, f"{label} does not parse: {exc}")
        return None
    if not isinstance(payload, dict):
        check(False, f"{label} is not an object")
        return None
    return payload


def load_openai_interface(path: Path, label: str) -> dict | None:
    """Parse the small YAML subset agents/openai.yaml uses.

    Same reasoning as `frontmatter`: no third-party packages,
    so this reads the shape the file actually has rather than
    general YAML. Every value is a quoted string, which is why
    json.loads is enough to unquote one.
    """
    if not check(path.exists(), f"{label}: missing agents/openai.yaml"):
        return None
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    if not check(
        bool(lines) and lines[0] == "interface:",
        f"{label}: agents/openai.yaml must start with 'interface:'",
    ):
        return None

    interface: dict[str, str] = {}
    index = 1
    while index < len(lines):
        line = lines[index]
        index += 1
        match = re.match(r"^  ([a-z][a-z0-9_]*):(?:\s+(.+))?$", line)
        if not check(
            match is not None,
            f"{label}: agents/openai.yaml has an unsupported line {line!r}",
        ):
            continue
        field = match.group(1)
        raw = match.group(2) or ""
        if not raw:
            fragments = []
            while index < len(lines) and lines[index].startswith("    "):
                fragments.append(lines[index].strip())
                index += 1
            raw = " ".join(fragments)
        if not check(
            bool(raw), f"{label}: agents/openai.yaml {field!r} has no value"
        ):
            continue
        if not check(
            field not in interface,
            f"{label}: agents/openai.yaml repeats {field!r}",
        ):
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            check(
                False,
                f"{label}: agents/openai.yaml {field!r} must be a "
                f"quoted string",
            )
            continue
        if not check(
            isinstance(value, str),
            f"{label}: agents/openai.yaml {field!r} must be a string",
        ):
            continue
        interface[field] = value
    return interface


def main() -> int:
    mkt_path = ROOT / ".claude-plugin/marketplace.json"
    mkt = load_json_object(mkt_path, ".claude-plugin/marketplace.json")
    codex_path = ROOT / ".agents/plugins/marketplace.json"
    codex_mkt = load_json_object(codex_path, ".agents/plugins/marketplace.json")
    if mkt is None or codex_mkt is None:
        print("\n".join(errors))
        return 1

    for field in ("name", "owner", "plugins"):
        check(field in mkt, f"marketplace.json missing required field {field!r}")
    name = mkt.get("name") or ""
    check(bool(NAME_RE.match(name)), f"marketplace name {name!r} is not kebab-case")
    check(name not in RESERVED, f"marketplace name {name!r} is reserved by Anthropic")
    owner = mkt.get("owner")
    check(
        isinstance(owner, dict) and bool(str(owner.get("name", "")).strip()),
        "marketplace owner is missing a name",
    )

    # The Codex marketplace is a second file describing the same
    # plugins to a different installer. It lists a subset: a
    # plugin appears there only once it actually ships the Codex
    # manifest and agent metadata, so the two files disagreeing
    # is the signal that a skill is half-wired.
    for field in ("name", "interface", "plugins"):
        check(
            field in codex_mkt,
            f"Codex marketplace missing required field {field!r}",
        )
    codex_name = codex_mkt.get("name") or ""
    check(
        codex_name == name,
        f"Codex marketplace name {codex_name!r} disagrees with Claude "
        f"Code marketplace name {name!r}",
    )
    codex_interface = codex_mkt.get("interface")
    check(
        isinstance(codex_interface, dict)
        and bool(str(codex_interface.get("displayName", "")).strip()),
        "Codex marketplace interface is missing displayName",
    )
    raw_codex_entries = codex_mkt.get("plugins")
    if not isinstance(raw_codex_entries, list):
        check(False, "Codex marketplace 'plugins' is not a list")
        raw_codex_entries = []
    codex_by_name: dict[str, dict] = {}
    for entry in raw_codex_entries:
        if not isinstance(entry, dict):
            check(False, f"Codex plugin entry {entry!r} is not an object")
            continue
        if not check(
            bool(entry.get("name")), f"Codex plugin entry {entry!r} has no name"
        ):
            continue
        codex_by_name[entry["name"]] = entry

    # `metadata.pluginRoot` reads like a base directory for every
    # plugin `source`, and it is not one. Claude Code 2.1.220
    # resolves `source` against the marketplace root and ignores
    # pluginRoot entirely, so a marketplace carrying
    # {"pluginRoot": "./plugins"} with {"source": "./replx"}
    # parses, validates, and then fails at install time with
    # "Source path does not exist". Every source is written out
    # in full for that reason, and the key is refused so the
    # shorter form cannot come back.
    metadata = mkt.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            check(False, "marketplace metadata is not an object")
        else:
            check(
                "pluginRoot" not in metadata,
                "metadata.pluginRoot is not honoured by Claude Code; write "
                "each plugin source out in full instead",
            )

    entries = mkt.get("plugins")
    if not isinstance(entries, list):
        check(False, "marketplace.json 'plugins' is not a list")
        entries = []

    # meta/ is read here as well as in the per-field loops below,
    # because which clients a plugin ships for decides which
    # manifests the plugin directory must carry.
    metas = [
        (path, frontmatter_yaml(path))
        for path in sorted((ROOT / "meta").glob("*.skill.yml"))
    ]
    meta_by_name = {fm.get("name", ""): fm for _, fm in metas}

    for entry in entries:
        # A null or non-object entry is valid JSON and used to
        # raise AttributeError here, hiding every other error.
        if not isinstance(entry, dict):
            check(False, f"plugin entry {entry!r} is not an object")
            continue
        pname = entry.get("name") or "<unnamed>"
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
            # A remote source must be pinned to something that
            # cannot move. The key being present is not a pin:
            # {"ref": "main"} and {"ref": ""} both passed, and
            # CONTRIBUTING promises never to track a branch.
            ref = str(src.get("ref") or "").strip()
            sha = str(src.get("sha") or "").strip()
            if not check(
                bool(ref or sha),
                f"plugin {pname!r} has a remote source with no ref or sha pin",
            ):
                continue
            if sha:
                check(
                    bool(re.fullmatch(r"[0-9a-f]{40}", sha)),
                    f"plugin {pname!r}: sha {sha!r} is not a full commit id",
                )
            if ref and not sha:
                check(
                    ref not in MUTABLE_REFS and not ref.startswith("refs/heads/"),
                    f"plugin {pname!r}: ref {ref!r} is a branch, which moves. "
                    f"Pin a tag or a sha.",
                )
            continue
        if not isinstance(src, str):
            check(
                False,
                f"plugin {pname!r} has a source of unsupported type "
                f"{type(src).__name__}; expected a path or an object",
            )
            continue

        # Both installers resolve a source against the
        # marketplace root, so both must be given the same
        # literal path to the same directory.
        expected_source = f"./{PATHS.PLUGIN_ROOT}/{pname}"
        check(
            src == expected_source,
            f"plugin {pname!r} source {src!r} must be {expected_source!r}",
        )
        try:
            pdir = PATHS.resolve_inside(
                ROOT, src.removeprefix("./"),
                source=f"plugin {pname!r} source")
        except PATHS.UnsafePath as exc:
            check(False, str(exc))
            continue
        if not check(pdir.is_dir(), f"plugin {pname!r} source does not exist: {pdir}"):
            continue

        fm_entry = meta_by_name.get(pname, {})
        clients = fm_entry.get("clients")
        if not isinstance(clients, list) or not clients:
            # An entry that predates the field ships for Claude
            # Code only. The default is safe because the checks
            # below compare it against what is on disk, so a
            # plugin that quietly grew a Codex manifest without
            # declaring it fails rather than passing by default.
            clients = [REQUIRED_CLIENT]
        for client in clients:
            check(
                client in CLIENTS,
                f"plugin {pname!r}: unknown client {client!r} in meta/; "
                f"expected one of {list(CLIENTS)}",
            )
        check(
            len(clients) == len(set(clients)),
            f"plugin {pname!r}: meta/ repeats a client in {clients!r}",
        )
        check(
            REQUIRED_CLIENT in clients,
            f"plugin {pname!r}: meta/ must list {REQUIRED_CLIENT!r}; this "
            f"is a Claude Code marketplace that Codex also reads",
        )
        wants_codex = "codex" in clients

        claude_manifest = None
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
                claude_manifest = manifest
            elif manifest is not None:
                check(False, f"plugin {pname!r}: plugin.json is not an object")

        # The vendored manifest states a version, and meta/
        # states the tag it was vendored from. If those two can
        # disagree, the marketplace can advertise 0.2.3 while
        # shipping the bytes of some other tag.
        upstream_ref = str(fm_entry.get("upstream_ref", "")).strip()
        if claude_manifest is not None and upstream_ref:
            check(
                str(claude_manifest.get("version", "")).strip()
                == upstream_ref.removeprefix("v"),
                f"plugin {pname!r}: plugin.json version "
                f"{claude_manifest.get('version')!r} does not match the "
                f"vendored tag {upstream_ref!r}",
            )

        # Codex reads a second manifest from the same directory.
        # Shipping one without declaring it, or declaring it
        # without shipping one, are both failures: a user of
        # either client would otherwise be told about a plugin
        # their client cannot load.
        codex_pj = pdir / ".codex-plugin/plugin.json"
        codex_manifest = None
        codex_interface_manifest = None
        check(
            codex_pj.exists() == wants_codex,
            f"plugin {pname!r}: meta/ clients {clients!r} disagrees with "
            f"{'a present' if codex_pj.exists() else 'a missing'} "
            f".codex-plugin/plugin.json",
        )
        check(
            (pname in codex_by_name) == wants_codex,
            f"plugin {pname!r}: meta/ clients {clients!r} disagrees with "
            f"the Codex marketplace, which does"
            f"{'' if pname in codex_by_name else ' not'} list it",
        )

        if wants_codex and codex_pj.exists():
            codex_manifest = load_json_object(
                codex_pj, f"plugin {pname!r}: .codex-plugin/plugin.json"
            )
        if isinstance(codex_manifest, dict):
            for field in PLUGIN_JSON_FIELDS:
                check(
                    bool(str(codex_manifest.get(field, "")).strip()),
                    f"plugin {pname!r}: Codex plugin.json has no {field!r}",
                )
            if claude_manifest is not None:
                for field in PLUGIN_JSON_FIELDS + ("homepage", "repository"):
                    check(
                        claude_manifest.get(field) == codex_manifest.get(field),
                        f"plugin {pname!r}: Claude Code and Codex manifests "
                        f"disagree on {field!r}",
                    )
            raw_interface = codex_manifest.get("interface")
            if not isinstance(raw_interface, dict):
                check(
                    False,
                    f"plugin {pname!r}: Codex plugin.json interface is not "
                    f"an object",
                )
            else:
                codex_interface_manifest = raw_interface
                for field in CODEX_INTERFACE_FIELDS:
                    check(
                        bool(str(raw_interface.get(field, "")).strip()),
                        f"plugin {pname!r}: Codex plugin.json interface has "
                        f"no {field!r}",
                    )
                prompts = raw_interface.get("defaultPrompt")
                check(
                    isinstance(prompts, list)
                    and len(prompts) == 1
                    and isinstance(prompts[0], str)
                    and bool(prompts[0].strip()),
                    f"plugin {pname!r}: Codex plugin.json interface "
                    f"defaultPrompt must hold one nonempty string",
                )

        if wants_codex and pname in codex_by_name:
            codex_entry = codex_by_name[pname]
            check(
                bool(str(codex_entry.get("category") or "").strip()),
                f"Codex plugin {pname!r} has no category",
            )
            policy = codex_entry.get("policy")
            if not isinstance(policy, dict):
                check(False, f"Codex plugin {pname!r} policy is not an object")
            else:
                for field, expected in CODEX_POLICY.items():
                    check(
                        policy.get(field) == expected,
                        f"Codex plugin {pname!r} policy {field} must be "
                        f"{expected!r}",
                    )
            codex_source = codex_entry.get("source")
            if not isinstance(codex_source, dict):
                check(False, f"Codex plugin {pname!r} source is not an object")
            else:
                check(
                    codex_source.get("source") == "local",
                    f"Codex plugin {pname!r} source must be 'local'; this "
                    f"marketplace ships vendored packages",
                )
                codex_src_path = codex_source.get("path")
                if not isinstance(codex_src_path, str):
                    check(
                        False, f"Codex plugin {pname!r} source has no path"
                    )
                else:
                    try:
                        codex_pdir = PATHS.resolve_inside(
                            ROOT, codex_src_path.removeprefix("./"),
                            source=f"Codex plugin {pname!r} source")
                    except PATHS.UnsafePath as exc:
                        check(False, str(exc))
                    else:
                        # Both installers must land on one
                        # directory. Two paths that each resolve
                        # is not the same as two paths that agree.
                        check(
                            codex_pdir == pdir,
                            f"Codex plugin {pname!r} resolves to "
                            f"{codex_pdir}, not {pdir}",
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

            # Codex loads its invocation surface from a file
            # beside SKILL.md, not from the plugin manifest, so
            # a Codex skill that lacks it installs and then
            # cannot be invoked by name.
            openai_yaml = skill_md.parent / "agents/openai.yaml"
            check(
                openai_yaml.exists() == wants_codex,
                f"{sdir}: meta/ clients {clients!r} disagrees with "
                f"{'a present' if openai_yaml.exists() else 'a missing'} "
                f"agents/openai.yaml",
            )
            if not (wants_codex and openai_yaml.exists()):
                continue
            openai_interface = load_openai_interface(openai_yaml, sdir)
            if openai_interface is None:
                continue
            for field in OPENAI_INTERFACE_FIELDS:
                check(
                    bool(str(openai_interface.get(field, "")).strip()),
                    f"{sdir}: agents/openai.yaml has no {field!r}",
                )
            # Codex invokes a skill as `$name`. A default prompt
            # that names a different skill is a prompt that
            # installs one thing and demonstrates another.
            check(
                f"${sname}" in openai_interface.get("default_prompt", ""),
                f"{sdir}: agents/openai.yaml default_prompt must contain "
                f"'${sname}'",
            )
            if codex_interface_manifest is None:
                continue
            for openai_field, manifest_field in (
                ("display_name", "displayName"),
                ("short_description", "shortDescription"),
            ):
                check(
                    openai_interface.get(openai_field)
                    == codex_interface_manifest.get(manifest_field),
                    f"{sdir}: Codex manifest and agents/openai.yaml "
                    f"disagree on {openai_field!r}",
                )
            manifest_prompts = codex_interface_manifest.get("defaultPrompt")
            if isinstance(manifest_prompts, list):
                check(
                    manifest_prompts == [openai_interface.get("default_prompt")],
                    f"{sdir}: Codex manifest and agents/openai.yaml "
                    f"disagree on 'default_prompt'",
                )

    # Every Codex entry must name a plugin this marketplace
    # actually ships. The reverse is allowed: a plugin can be
    # Claude Code only, which is what a subset means here.
    claude_names = {
        e.get("name") for e in entries if isinstance(e, dict) and e.get("name")
    }
    for codex_only in sorted(set(codex_by_name) - claude_names):
        check(
            False,
            f"Codex marketplace lists {codex_only!r}, which is not a plugin "
            f"in the Claude Code marketplace",
        )

    # A status the index would print verbatim to a reader.
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        status = fm.get("status", "")
        check(
            status in STATUSES,
            f"{meta.name}: status {status!r} must be one of "
            f"{sorted(STATUSES)}",
        )

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

    # The renames map, which Claude Code reads on startup to
    # migrate a user off a name that changed. A wrong entry
    # silently strands them, so both halves are checked.
    renames = mkt.get("renames")
    if renames is not None:
        if isinstance(renames, dict):
            current = {e.get("name") for e in entries if isinstance(e, dict)}
            for old_name, new_name in renames.items():
                check(
                    old_name not in current,
                    f"renames maps {old_name!r}, which is still a live "
                    f"plugin name. A name cannot be both current and former.",
                )
                if new_name is None:
                    continue
                check(
                    new_name in current,
                    f"renames points {old_name!r} at {new_name!r}, which is "
                    f"not a plugin in this marketplace",
                )
        else:
            check(False, "marketplace.json 'renames' is not an object")

    # A pin that can be deleted is not a pin. sync only
    # compares upstream_sha when it is already present, so a
    # pull request that removes the line makes a moved tag
    # acceptable and nothing notices.
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        if not fm.get("upstream"):
            continue
        sha = fm.get("upstream_sha", "")
        if not check(
            bool(sha),
            f"{meta.name}: missing required 'upstream_sha'. Without it "
            f"`make sync` cannot detect a tag that moved.",
        ):
            continue
        if sha == UNRESOLVED:
            # The one way to have no commit id: say so in the
            # field, and say so in the status too. Writing a
            # guess here would be worse than writing nothing,
            # because every later check would then pass.
            check(
                fm.get("status") == "pending-publication",
                f"{meta.name}: upstream_sha is {UNRESOLVED}, so status must "
                f"be 'pending-publication', not {fm.get('status')!r}",
            )
        else:
            check(
                bool(re.fullmatch(r"[0-9a-f]{40}", sha)),
                f"{meta.name}: upstream_sha {sha!r} is not a full commit id",
            )
        check(
            bool(fm.get("upstream_ref")),
            f"{meta.name}: has an upstream but no 'upstream_ref'",
        )

    # CONTRIBUTING requires a worked example. Until this field
    # existed the requirement was unenforceable, which is the
    # same as absent.
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        ex = fm.get("example", "")
        if not check(
            bool(ex),
            f"{meta.name}: missing required 'example'. CONTRIBUTING "
            f"requires a worked example produced by running the skill.",
        ):
            continue
        check(
            ex.startswith("http"),
            f"{meta.name}: example must be a URL, got {ex!r}",
        )

    # meta/ and marketplace.json each carry a copy of the same
    # three facts. Two copies drift; this is what notices.
    # `entries` was rebuilt here from the raw list rather than
    # reusing the validated one above, so the null guard did not
    # apply and this crashed on the same input.
    by_name = {
        e.get("name"): e
        for e in entries
        if isinstance(e, dict) and e.get("name")
    }
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = frontmatter_yaml(meta)
        sname = fm.get("name", "")
        if not check(
            sname in by_name,
            f"{meta.name}: name {sname!r} has no plugin entry in "
            f"marketplace.json",
        ):
            continue
        entry = by_name[sname]
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
        try:
            got = PACKAGE_DIGEST.sha256(f)
        except PACKAGE_DIGEST.UnsafePackage as exc:
            check(False, f"{meta.name}: {exc}")
            continue
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
    out: dict = {}
    key = None
    for line in path.read_text().split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # A `  - ` line is a sequence item. Collecting these
        # rather than dropping them is what lets `clients` be
        # checked against the manifests on disk.
        if line.startswith("  - ") and key:
            if not isinstance(out.get(key), list):
                out[key] = []
            out[key].append(line[4:].strip())
            continue
        # Fold a block scalar's continuation lines into its key,
        # so a `use: >-` body is comparable with the one-line
        # description marketplace.json holds.
        if line.startswith("  ") and key and not isinstance(out.get(key), list):
            out[key] = (str(out.get(key, "")) + " " + line.strip()).strip()
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val in (">-", ">", "|", "|-"):
                out[key] = ""
            elif val == "[]":
                out[key] = []
            else:
                out[key] = val
    return out


if __name__ == "__main__":
    sys.exit(main())
