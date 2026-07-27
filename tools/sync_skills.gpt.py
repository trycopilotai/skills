#!/usr/bin/env python3
"""Refresh vendored SKILL.md copies from their upstream repos.

Each meta/*.skill.yml names an upstream repo, a pinned ref, a
vendored path, and the sha256 the vendored copy should have.
This fetches the pinned ref, copies the skill in, and rewrites
vendored_sha256. Run it, then commit both the skill and the
meta file together.

`upstream_sha` is a pin, so it is verified rather than
overwritten: a tag that has moved since it was recorded stops
the run. Pass --repin when the move is the point, such as when
you have just raised upstream_ref to a new tag.

    python3 tools/sync_skills.gpt.py [--repin]
"""
import argparse
import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_SKILL_PATH = "skill/SKILL.md"   # the layout every skill repo uses


def _load_paths():
    """Import tools/paths.gpt.py, whose name is not importable."""
    spec = importlib.util.spec_from_file_location(
        "skills_paths", Path(__file__).resolve().parent / "paths.gpt.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PATHS = _load_paths()


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

        try:
            dst = PATHS.resolve_vendored(ROOT, vp, source=meta.name)
        except PATHS.UnsafePath as exc:
            print(f"  refusing to write outside the repository: {exc}")
            return 1

        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                ["git", "-c", "advice.detachedHead=false", "clone", "--quiet",
                 "--depth", "1", "--branch", ref,
                 f"https://{repo}", f"{td}/src"], check=True)
            src = Path(td) / "src" / UPSTREAM_SKILL_PATH
            if not src.exists():
                print(f"  {meta.name}: {UPSTREAM_SKILL_PATH} not found at {ref}")
                return 1
            sha_upstream = subprocess.run(
                ["git", "-C", f"{td}/src", "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True).stdout.strip()

            # Verify the pin before copying anything in. A tag is
            # mutable, so "clone --branch v0.1.0" is not evidence
            # that you got the v0.1.0 anyone reviewed.
            recorded = f.get("upstream_sha", "")
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

            dst.parent.mkdir(parents=True, exist_ok=True)
            before = dst.read_bytes() if dst.exists() else b""
            shutil.copyfile(src, dst)
            sha = hashlib.sha256(dst.read_bytes()).hexdigest()

        t = meta.read_text()
        t = re.sub(r"^vendored_sha256:.*$", f"vendored_sha256: {sha}", t, flags=re.M)
        if not recorded or args.repin:
            t = re.sub(r"^upstream_sha:.*$", f"upstream_sha: {sha_upstream}", t, flags=re.M)
        meta.write_text(t)

        state = "updated" if before != dst.read_bytes() else "unchanged"
        changed += before != dst.read_bytes()
        note = ""
        if recorded and args.repin and recorded != sha_upstream:
            note = f"  (repinned {recorded[:12]} -> {sha_upstream[:12]})"
        print(f"  {f['name']}: {state} from {repo}@{ref}{note}")

    print(f"{changed} skill(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
