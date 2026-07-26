#!/usr/bin/env python3
"""Refresh vendored SKILL.md copies from their upstream repos.

Each meta/*.skill.yml names an upstream repo, a pinned ref, a
vendored path, and the sha256 the vendored copy should have.
This fetches the pinned ref, copies the skill in, and rewrites
vendored_sha256. Run it, then commit both the skill and the
meta file together.
"""
import hashlib, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_SKILL_PATH = "skill/SKILL.md"   # the layout every skill repo uses


def parse(p):
    return dict(re.findall(r"^([A-Za-z0-9_-]+):\s*(\S.*)$", p.read_text(), re.M))


def main():
    changed = 0
    for meta in sorted((ROOT / "meta").glob("*.skill.yml")):
        f = parse(meta)
        repo, ref, vp = f.get("upstream"), f.get("upstream_ref"), f.get("vendored_path")
        if not (repo and ref and vp):
            continue
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                ["git", "clone", "--quiet", "--depth", "1", "--branch", ref,
                 f"https://{repo}", f"{td}/src"], check=True)
            src = Path(td) / "src" / UPSTREAM_SKILL_PATH
            if not src.exists():
                print(f"  {meta.name}: {UPSTREAM_SKILL_PATH} not found at {ref}")
                return 1
            dst = ROOT / vp
            dst.parent.mkdir(parents=True, exist_ok=True)
            before = dst.read_bytes() if dst.exists() else b""
            shutil.copyfile(src, dst)
            sha = hashlib.sha256(dst.read_bytes()).hexdigest()
            sha_upstream = subprocess.run(
                ["git", "-C", f"{td}/src", "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True).stdout.strip()
        t = meta.read_text()
        t = re.sub(r"^vendored_sha256:.*$", f"vendored_sha256: {sha}", t, flags=re.M)
        t = re.sub(r"^upstream_sha:.*$", f"upstream_sha: {sha_upstream}", t, flags=re.M)
        meta.write_text(t)
        state = "updated" if before != dst.read_bytes() else "unchanged"
        changed += before != dst.read_bytes()
        print(f"  {f['name']}: {state} from {repo}@{ref}")
    print(f"{changed} skill(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
