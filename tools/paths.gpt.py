#!/usr/bin/env python3
"""Resolve paths that came out of meta/*.skill.yml.

`vendored_path` is data, not code, and a pull request can set
it to anything. Joining it to the repository root with no
containment check is enough to write outside the checkout:
`../../../.ssh/authorized_keys` escapes, and an absolute path
discards the root entirely, because `Path("/a") / "/etc/x"`
is `/etc/x`.

Both the sync tool and the validator consume that field, so
both go through here rather than each growing its own guard.
"""

from pathlib import Path, PurePosixPath

# Every vendored skill lives under this directory. It matches
# metadata.pluginRoot in .claude-plugin/marketplace.json.
PLUGIN_ROOT = "plugins"


class UnsafePath(Exception):
    """A meta/ path that does not stay inside PLUGIN_ROOT."""


def resolve_inside(base: Path, rel: str, source: str = "input") -> Path:
    """Resolve `rel` under `base`, or raise UnsafePath.

    The general form. `resolve_vendored` is this plus the rule
    that a vendored skill lives under PLUGIN_ROOT; this one is
    for marketplace-controlled paths such as `metadata.pluginRoot`
    and a plugin `source`, which are also data a pull request
    writes.
    """
    if not isinstance(rel, str) or not rel.strip():
        raise UnsafePath(f"{source}: path is empty")
    if "\\" in rel:
        raise UnsafePath(f"{source}: path {rel!r} uses backslashes")
    pure = PurePosixPath(rel)
    if pure.is_absolute():
        raise UnsafePath(f"{source}: path {rel!r} is absolute")
    if len(rel) > 1 and rel[1] == ":":
        raise UnsafePath(f"{source}: path {rel!r} looks like a drive path")
    if ".." in pure.parts:
        raise UnsafePath(f"{source}: path {rel!r} traverses upward")

    allowed = base.resolve()
    target = (base / pure).resolve()
    if target != allowed and allowed not in target.parents:
        raise UnsafePath(
            f"{source}: path {rel!r} resolves to {target}, which is "
            f"outside {allowed}"
        )
    return target


def resolve_vendored(root: Path, rel: str, source: str = "meta") -> Path:
    """Resolve `rel` under `root/plugins`, or raise UnsafePath.

    Rejects absolute paths, Windows drive letters, traversal,
    and anything whose real location leaves the subtree, which
    covers symlinks because the check runs after resolution.
    """
    if not isinstance(rel, str) or not rel.strip():
        raise UnsafePath(f"{source}: vendored_path is empty")
    if rel != rel.strip():
        raise UnsafePath(f"{source}: vendored_path {rel!r} is padded")
    if "\\" in rel:
        raise UnsafePath(
            f"{source}: vendored_path {rel!r} uses backslashes; "
            f"use forward slashes"
        )

    pure = PurePosixPath(rel)
    if pure.is_absolute():
        raise UnsafePath(f"{source}: vendored_path {rel!r} is absolute")
    if len(rel) > 1 and rel[1] == ":":
        raise UnsafePath(
            f"{source}: vendored_path {rel!r} looks like a drive path"
        )
    if ".." in pure.parts:
        raise UnsafePath(f"{source}: vendored_path {rel!r} traverses upward")
    if pure.parts and pure.parts[0] != PLUGIN_ROOT:
        raise UnsafePath(
            f"{source}: vendored_path {rel!r} must start with "
            f"{PLUGIN_ROOT}/"
        )

    allowed = (root / PLUGIN_ROOT).resolve()
    target = (root / pure).resolve()
    if target != allowed and allowed not in target.parents:
        raise UnsafePath(
            f"{source}: vendored_path {rel!r} resolves to {target}, "
            f"which is outside {allowed}"
        )
    return target
