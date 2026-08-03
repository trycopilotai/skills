#!/usr/bin/env python3
"""Refresh vendored skill packages from their upstream repos.

Each meta/*.skill.yml names an upstream repo, a pinned ref, a
vendored path, and the sha256 the vendored copy should have.
This fetches the pinned ref, copies the skill in, and rewrites
vendored_sha256. Run it, then commit both the skill and the
meta file together.

What gets copied is one file or one whole directory, and the
two are not interchangeable. A skill that is only prose is a
single SKILL.md; a skill that ships scripts or per-client
agent metadata is a package, and vendoring only its SKILL.md
would install something that cannot run. `upstream_path` in
meta/ names the source, and `vendored_path` names where it
lands; whether each is a file or a directory follows from
what upstream actually has.

`upstream_sha` is a pin, so it is verified rather than
overwritten: a tag that has moved since it was recorded stops
the run. Pass --repin when the move is the point, such as when
you have just raised upstream_ref to a new tag.

An entry whose pin is still UNRESOLVED is skipped rather than
fetched. Its upstream tag does not exist yet, so there is
nothing to compare the vendored bytes against, and a clone
that fails for that reason would read as a network problem.
`make release-gate` is what refuses to let such an entry
ship.

    python3 tools/sync_skills.gpt.py [--repin]
"""
import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The layout the first skill repo used, kept as the default so
# an entry that predates `upstream_path` still resolves.
DEFAULT_UPSTREAM_PATH = "skill/SKILL.md"

# A pin that is deliberately not yet a commit id. See
# tools/release_gate.gpt.py.
UNRESOLVED = "UNRESOLVED"


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


def parse(p):
    return dict(re.findall(r"^([A-Za-z0-9_-]+):\s*(\S.*)$", p.read_text(), re.M))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repin",
        action="store_true",
        help="accept an upstream_sha that differs from the recorded pin",
    )
    args = ap.parse_args(argv)

    changed = 0
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        f = parse(meta)
        repo, ref, vp = f.get("upstream"), f.get("upstream_ref"), f.get("vendored_path")
        if not (repo and ref and vp):
            continue

        recorded = f.get("upstream_sha", "")
        if recorded == UNRESOLVED:
            print(
                f"  {f['name']}: skipped, pin is {UNRESOLVED}. "
                f"{repo}@{ref} does not exist yet."
            )
            continue

        try:
            dst = PATHS.resolve_vendored(ROOT, vp, source=meta.name)
        except PATHS.UnsafePath as exc:
            print(f"  refusing to write outside the repository: {exc}")
            return 1

        # Where the package sits upstream is per-skill: one repo
        # keeps a bare `skill/SKILL.md`, another keeps the whole
        # `skills/<name>/` a client loads.
        upstream_path = f.get("upstream_path", DEFAULT_UPSTREAM_PATH)

        with tempfile.TemporaryDirectory() as td:
            # `upstream` is normally a bare host/org/repo, which
            # means https. A value that already carries a scheme
            # is used as given, so the guards below can be tested
            # against a local repository instead of reaching the
            # network from a unit test.
            url = repo if "://" in repo else f"https://{repo}"
            clone = subprocess.run(
                ["git", "-c", "advice.detachedHead=false", "clone", "--quiet",
                 "--depth", "1", "--branch", ref, url, f"{td}/src"],
                capture_output=True, text=True)
            if clone.returncode != 0:
                print(f"  {meta.name}: cannot fetch {url}@{ref}\n"
                      f"      {clone.stderr.strip().splitlines()[-1] if clone.stderr.strip() else 'clone failed'}")
                return 1
            # `upstream_path` is meta/ data like any other, so it
            # is contained against the clone rather than joined to
            # it. A `../` there would otherwise read bytes from
            # outside the repository being vendored.
            try:
                src = PATHS.resolve_inside(
                    Path(td) / "src", upstream_path,
                    source=f"{meta.name}: upstream_path")
            except PATHS.UnsafePath as exc:
                print(f"  refusing to read outside the clone: {exc}")
                return 1
            if not src.exists():
                print(f"  {meta.name}: {upstream_path} not found at {ref}")
                return 1
            sha_upstream = subprocess.run(
                ["git", "-C", f"{td}/src", "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True).stdout.strip()

            # Verify the pin before copying anything in. A tag is
            # mutable, so "clone --branch v0.1.0" is not evidence
            # that you got the v0.1.0 anyone reviewed.
            if recorded and recorded != sha_upstream and not args.repin:
                print(
                    f"  {meta.name}: {repo}@{ref} has moved.\n"
                    f"      pinned   {recorded}\n"
                    f"      upstream {sha_upstream}\n"
                    f"      The tag no longer points at the commit this\n"
                    f"      repository vendored. Review the difference,\n"
                    f"      then re-run with --repin to accept it."
                )
                return 1

            # A directory destination cannot be overwritten in
            # place: copying file by file would leave a file that
            # upstream deleted sitting in the vendored tree, and
            # deleting first would leave nothing at all if the
            # copy then failed. Stage the replacement beside the
            # destination and swap, so an interrupted run leaves
            # either the old package or the new one.
            dst.parent.mkdir(parents=True, exist_ok=True)
            before = None
            if dst.exists():
                try:
                    before = PACKAGE_DIGEST.sha256(dst)
                except PACKAGE_DIGEST.UnsafePackage as exc:
                    print(f"  {meta.name}: {exc}")
                    return 1
            try:
                sha = PACKAGE_DIGEST.sha256(src)
            except PACKAGE_DIGEST.UnsafePackage as exc:
                print(f"  {meta.name}: {exc}")
                return 1

            with tempfile.TemporaryDirectory(
                prefix=f".{dst.name}.sync-", dir=dst.parent
            ) as swap_raw:
                swap = Path(swap_raw)
                staged, previous = swap / "next", swap / "previous"
                if src.is_dir():
                    shutil.copytree(src, staged, symlinks=True)
                else:
                    shutil.copy2(src, staged)
                if dst.exists():
                    dst.replace(previous)
                try:
                    staged.replace(dst)
                except OSError:
                    if previous.exists():
                        previous.replace(dst)
                    raise

        t = meta.read_text()
        t = re.sub(r"^vendored_sha256:.*$", f"vendored_sha256: {sha}", t, flags=re.M)
        if not recorded or args.repin:
            t = re.sub(r"^upstream_sha:.*$", f"upstream_sha: {sha_upstream}", t, flags=re.M)
        meta.write_text(t)

        if before != sha:
            state = "updated"
            changed += 1
        else:
            state = "unchanged"
        note = ""
        if recorded and args.repin and recorded != sha_upstream:
            note = f"  (repinned {recorded[:12]} -> {sha_upstream[:12]})"
        print(f"  {f['name']}: {state} from {repo}@{ref}{note}")

    print(f"{changed} skill(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
