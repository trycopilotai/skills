#!/usr/bin/env python3
"""Digest one vendored SKILL.md, or a whole skill package.

The first skill listed here vendored a single file, so a
single file keeps its historical meaning: the raw sha256 of
its bytes. Re-deriving `replx`'s recorded digest through this
module has to produce the same string it produced through
`hashlib` directly, or adding a second skill would silently
rewrite the first one's pin.

A directory is hashed as a sorted tree: for each file, its
POSIX-relative path, a NUL, its bytes, and a trailing NUL.
The path is inside the hash because bytes alone cannot tell
`scripts/render.py` from `scripts/renderer.py`, and a rename
with no content change is still a change to what gets
installed. Sorting is what makes it deterministic across
filesystems that walk in different orders.

Symbolic links are refused rather than followed. The package
is upstream-controlled data, and a link is the one entry that
can make a digest describe bytes from outside the tree the
digest claims to cover.
"""

import hashlib
from pathlib import Path


class UnsafePackage(ValueError):
    """A package holds a path that cannot be vendored."""


def sha256(path: Path) -> str:
    """Digest a file's bytes, or a directory as a sorted tree."""
    if path.is_symlink():
        raise UnsafePackage(f"symbolic links are not allowed: {path}")
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        raise FileNotFoundError(path)

    digest = hashlib.sha256()
    for member in sorted(path.rglob("*")):
        if member.is_symlink():
            relative = member.relative_to(path).as_posix()
            raise UnsafePackage(
                f"symbolic links are not allowed: {relative}"
            )
        if not member.is_file():
            continue
        relative = member.relative_to(path).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(member.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
