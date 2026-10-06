#!/usr/bin/env python3
"""Render the swe-day "Active Run" next-action banner.

This program decides nothing. ``swe_day_lock.py`` owns the phase model
and derives which human gate is pending; this reads that and prints a
banner of one to three lines: the state line, an optional free-text
line that starts ``note:``, and, when a gate is pending, the gate.

OWNER is human whenever a gate is pending or the lock's metadata is
missing or unusable. ``no active swe-day`` is printed only when no lock
directory exists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Rendering reads; it must not leave a bytecode cache beside the skill.
sys.dont_write_bytecode = True

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import swe_day_lock as lock  # noqa: E402

UNREADABLE_BANNER = (
    "▶ swe-day ACTIVE · phase unknown · "
    "NEXT: operator reviews a lock whose metadata is missing or unusable · "
    "OWNER: human · BLOCKED-ON: operator"
)


def one_line(value: object) -> str:
    """Free text as one line with no control characters."""
    printable = "".join(ch if ch.isprintable() else " " for ch in str(value))
    return " ".join(printable.split())


def compute_banner(state: dict) -> str:
    summary = lock.describe(state)
    blocked_on = "none"
    if summary["owner"] == "human":
        blocked_on = "operator"
    lines = [
        f"▶ swe-day ACTIVE · phase {state['phase']} · "
        f"NEXT: {summary['next']} · OWNER: {summary['owner']} · "
        f"BLOCKED-ON: {blocked_on}"
    ]
    note = state.get("phase_note")
    if note:
        lines.append("  note: " + one_line(note))
    if summary["gate"] is not None:
        lines.append(
            "  (downstream agent actions are gated behind "
            f"'{summary['gate']}' — not offered until you clear it)"
        )
    return "\n".join(lines)


def command_render(args: argparse.Namespace) -> int:
    try:
        lock_path = lock.resolve_lock_path(args.repo, args.lock_path)
    except lock.LockPathError as error:
        print(str(error), file=sys.stderr)
        return lock.EXIT_PATH
    if not lock.lock_exists(lock_path):
        print("no active swe-day")
        return 0
    # A lock that exists is a run in progress even when its metadata
    # cannot be used: acquire refuses it, so this must not call it idle.
    try:
        state = lock.load_state(lock_path)
    except (lock.Unreadable, OSError):
        print(UNREADABLE_BANNER)
        return 0
    print(compute_banner(state))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render the swe-day Active Run next-action banner.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root containing the lock path.",
    )
    parser.add_argument(
        "--lock-path",
        default=lock.DEFAULT_LOCK_PATH,
        help="Repo-relative lock directory path. It must stay inside --repo.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    render = subparsers.add_parser("render")
    render.set_defaults(handler=command_render)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    # A note is free text and a terminal may not be UTF-8; the banner
    # is printed with escapes rather than not printed.
    sys.stdout.reconfigure(errors="backslashreplace")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
