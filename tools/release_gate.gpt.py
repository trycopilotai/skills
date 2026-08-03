#!/usr/bin/env python3
"""Refuse to call this repository publishable on trust.

`make validate` checks that the repository is internally
consistent. It cannot check the one thing that decides whether
a listing is honest: that the upstream tag each entry names
exists in public, points at the commit meta/ pins, and holds
the bytes this repository vendored. Every input to that
question lives on a remote.

So this asks the remote. For each entry it resolves the tag,
compares it against `upstream_sha`, clones at that tag, and
digests the upstream package the same way `make validate`
digests the vendored copy. An entry is publishable only when
all of that agrees.

It fails closed, in the strong sense: not being able to answer
counts as a failure. An unreachable remote, a missing tag, a
pin still recorded as UNRESOLVED, and bytes that differ all
produce the same verdict, HELD, and the same non-zero exit.
The alternative reading, "the check did not run, so nothing
was wrong", is how an entry gets published against a tag that
was never pushed.

    python3 tools/release_gate.gpt.py [--entry NAME]

Exit status is 0 only when every entry examined is
publishable.
"""

import argparse
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNRESOLVED = "UNRESOLVED"
DEFAULT_UPSTREAM_PATH = "skill/SKILL.md"


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
VALIDATE = _load_sibling("validate.gpt.py", "skills_validate")


def held(name: str, reason: str) -> tuple:
    return (name, False, reason)


def examine(fm: dict) -> tuple:
    """Decide one entry's verdict against its public remote."""
    name = fm.get("name", "<unnamed>")
    repo = fm.get("upstream", "")
    ref = fm.get("upstream_ref", "")
    pinned = fm.get("upstream_sha", "")
    vendored_path = fm.get("vendored_path", "")
    recorded_digest = fm.get("vendored_sha256", "")
    upstream_path = fm.get("upstream_path", DEFAULT_UPSTREAM_PATH)

    if not (repo and ref and vendored_path and recorded_digest):
        return held(name, "meta/ entry is incomplete")
    # The pin is reported before the status because it is the
    # cause and the status is the consequence: an entry with no
    # commit id is required to call itself pending, so saying
    # "status is pending" would name the symptom.
    if pinned == UNRESOLVED:
        return held(
            name,
            f"pin is {UNRESOLVED}; {repo}@{ref} has not been published",
        )
    if fm.get("status") != "published":
        return held(
            name, f"status is {fm.get('status')!r}, not 'published'"
        )
    if not re.fullmatch(r"[0-9a-f]{40}", pinned or ""):
        return held(name, f"upstream_sha {pinned!r} is not a commit id")

    url = repo if "://" in repo else f"https://{repo}"

    # Ask the remote what the tag is before fetching anything.
    # `ls-remote` answers the question the pin exists to settle,
    # and answers it without trusting a local clone that may
    # carry a tag which was never pushed.
    listed = subprocess.run(
        ["git", "ls-remote", "--tags", url, f"refs/tags/{ref}",
         f"refs/tags/{ref}^{{}}"],
        capture_output=True, text=True,
    )
    if listed.returncode != 0:
        detail = "unreachable"
        if listed.stderr.strip():
            detail = listed.stderr.strip().splitlines()[-1]
        return held(name, f"cannot reach {url}: {detail}")

    resolved = {}
    for line in listed.stdout.strip().splitlines():
        sha, _, refname = line.partition("\t")
        resolved[refname.strip()] = sha.strip()
    if not resolved:
        return held(name, f"{url} has no tag {ref}")

    # An annotated tag lists both the tag object and, under
    # `^{}`, the commit it points at. The commit is what a pin
    # means, so it wins when both are present.
    remote_sha = resolved.get(
        f"refs/tags/{ref}^{{}}", resolved.get(f"refs/tags/{ref}", "")
    )
    if remote_sha != pinned:
        return held(
            name,
            f"{ref} is {remote_sha[:12]} upstream, pinned {pinned[:12]}",
        )

    with tempfile.TemporaryDirectory() as td:
        clone = subprocess.run(
            ["git", "-c", "advice.detachedHead=false", "clone", "--quiet",
             "--depth", "1", "--branch", ref, url, f"{td}/src"],
            capture_output=True, text=True,
        )
        if clone.returncode != 0:
            detail = "clone failed"
            if clone.stderr.strip():
                detail = clone.stderr.strip().splitlines()[-1]
            return held(name, f"cannot clone {url}@{ref}: {detail}")
        try:
            src = PATHS.resolve_inside(
                Path(td) / "src", upstream_path, source=f"{name}: upstream_path"
            )
        except PATHS.UnsafePath as exc:
            return held(name, str(exc))
        if not src.exists():
            return held(name, f"{upstream_path} is not present at {ref}")
        try:
            upstream_digest = PACKAGE_DIGEST.sha256(src)
        except PACKAGE_DIGEST.UnsafePackage as exc:
            return held(name, str(exc))

    try:
        local = PATHS.resolve_vendored(ROOT, vendored_path, source=name)
    except PATHS.UnsafePath as exc:
        return held(name, str(exc))
    if not local.exists():
        return held(name, f"vendored_path missing: {vendored_path}")
    try:
        local_digest = PACKAGE_DIGEST.sha256(local)
    except PACKAGE_DIGEST.UnsafePackage as exc:
        return held(name, str(exc))

    if local_digest != recorded_digest:
        return held(
            name,
            f"vendored bytes digest {local_digest[:16]}…, meta/ records "
            f"{recorded_digest[:16]}…",
        )
    if upstream_digest != recorded_digest:
        return held(
            name,
            f"{ref} ships {upstream_digest[:16]}…, this repository vendored "
            f"{recorded_digest[:16]}…",
        )
    return (name, True, f"{repo}@{ref} {pinned[:12]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--entry",
        action="append",
        default=[],
        help="examine only this skill name; repeatable",
    )
    args = ap.parse_args(argv)

    verdicts = []
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        fm = VALIDATE.frontmatter_yaml(meta)
        if args.entry and fm.get("name") not in args.entry:
            continue
        verdicts.append(examine(fm))

    if not verdicts:
        print("no entries examined; nothing can be called publishable")
        return 1

    for name, publishable, reason in verdicts:
        state = "PUBLISHABLE" if publishable else "HELD"
        print(f"  {state:<12} {name}: {reason}")

    blocked = [name for name, ok, _ in verdicts if not ok]
    if blocked:
        print(
            f"\nHELD  {len(blocked)} of {len(verdicts)} entries cannot be "
            f"published: {', '.join(blocked)}"
        )
        return 1
    print(f"\nOK    {len(verdicts)} entries verified against their remotes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
