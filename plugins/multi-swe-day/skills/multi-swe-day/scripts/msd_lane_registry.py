#!/usr/bin/env python3
"""msd_lane_registry — the multi-swe-day disjoint-lane invariant.

The registry half of multi-swe-day, analog of swe_day_lock.py. It
records which builder owns which repo-relative lanes (file/dir paths)
and refuses to register a lane that overlaps a lane already held — or
merely proposed — by another builder (a builder whose status is
`aborted` does not block, and a slug that registers again replaces
its own row). Overlap is path-normalized and
covers exact, ancestor, and descendant relationships, so registering
`src/` collides with an existing `src/auth/login.ts` and vice versa.

This is the leader-only sole-writer surface for lane ownership. A
register/confirm/update/release/init mutation run with `--lock-path`
must prove it holds the
swe-day lock by passing `--lock-owner` (and `--session-id` when the
lock pins a session) that match the lock's `metadata.json`; the
temp-file+rename write stops one writer's torn registry, not
wrong-writer writes and not two writers at once.
`status` is read-only and needs no lock proof.

Schema (one JSON object at the registry path):
  {
    "schema_version": 2,
    "updated_at": "<utc>",
    "leader": "<leader-slug>",
    "run": {
      "phase": "<phase>", "next_owner": "human|agent",
      "blocking_gate": "<name>|null", "note": "<s>",
      "cleared_gates": ["<name>", ...], "updated_at": "<utc>"
    },
    "followers": {
      "<slug>": {
        "role": "builder-NN", "lanes": ["<posix>", ...],
        "day": "DXX", "plan_path": "<path>", "model": "...",
        "effort": "...", "status": "proposed", "commit": null,
        "propose": "<propose-ref>|null", "updated_at": "<utc>"
      }
    }
  }

The top-level `run` object is the run-level next-action state the
leader advances (`run-advance`) and the operator's gate clears
(`run-clear-gate`). It is OPTIONAL: a registry written by an older
schema has no `run` key, and `msd_next.py` derives the phase from lane
statuses instead — so absence is backward-compatible, not an error.
`run.cleared_gates` lists the gates `run-clear-gate` has cleared; a
later `run-advance` keeps it, and one that records a gate again
removes that gate from it.

Gates the registry enforces:
  - `confirm` needs `--propose <propose-ref>`, the PROPOSE reference:
    the envelope id of the builder's PROPOSE (the verify-before-implement
    reply), or in a single session the path of the file holding the
    finding. Any value that is not empty or only whitespace is accepted;
    it is stored, trimmed, as `propose`.
  - `update --status landed` is refused while `run.blocking_gate` is
    set, and until `human-review` is in `run.cleared_gates`.
  Both refusals exit 5, like an illegal transition.

Status transitions:
  proposed -> assigned -> in-progress -> reported -> landed | aborted
(`confirm` makes proposed -> assigned; `update --status` refuses that
step and enforces the rest.)

Usage:
  msd_lane_registry.py --registry handoff/multi-swe-day.json \
      --lock-path .agents/locks/ops-repo.swe-day.lock \
      init --leader swe-day-leader \
      --lock-owner swe-day-leader --session-id <sid>

  msd_lane_registry.py --registry handoff/multi-swe-day.json \
      --lock-path .agents/locks/ops-repo.swe-day.lock \
      register --slug swe-day-follower-01 --role builder-01 \
      --day D42 --plan-path plans/d42.plan.md \
      --model <model-id> --effort <effort> \
      --lane src/auth --lane src/billing/types.ts \
      --lock-owner swe-day-leader --session-id <sid>

  msd_lane_registry.py --registry handoff/multi-swe-day.json \
      --lock-path .agents/locks/ops-repo.swe-day.lock \
      confirm --slug swe-day-follower-01 --propose <propose-ref> \
      --lock-owner swe-day-leader --session-id <sid>

  msd_lane_registry.py --registry handoff/multi-swe-day.json status
  msd_lane_registry.py --registry handoff/multi-swe-day.json \
      status --slug swe-day-follower-01

  msd_lane_registry.py --registry handoff/multi-swe-day.json \
      --lock-path .agents/locks/ops-repo.swe-day.lock \
      update --slug swe-day-follower-01 --status in-progress \
      [--commit <sha>] --lock-owner swe-day-leader --session-id <sid>

  msd_lane_registry.py --registry handoff/multi-swe-day.json \
      --lock-path .agents/locks/ops-repo.swe-day.lock \
      release --slug swe-day-follower-01 \
      --lock-owner swe-day-leader --session-id <sid>

  msd_lane_registry.py --registry handoff/multi-swe-day.json \
      --lock-path .agents/locks/ops-repo.swe-day.lock \
      run-advance --phase reconcile --owner agent \
      --note "all lanes reported; review cleared" \
      --lock-owner swe-day-leader --session-id <sid>

  msd_lane_registry.py --registry handoff/multi-swe-day.json \
      --lock-path .agents/locks/ops-repo.swe-day.lock \
      run-clear-gate human-review \
      --lock-owner swe-day-leader --session-id <sid>

Without --lock-path a mutation is not lock-guarded.

On a mutation it prints the updated registry JSON. On a lane conflict
it prints the conflicting slug + lanes to stderr and exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any


# Schema 1 had no top-level `run` object; schema 2 adds the optional
# `run` next-action state. A schema-1 registry still loads unchanged —
# the `run` key is simply absent and `msd_next.py` derives the phase
# from lane statuses — so the bump is backward-compatible.
SCHEMA_VERSION = 2
METADATA_NAME = "metadata.json"
LOCK_SCHEMA_VERSION = 1  # checked only when the lock metadata records one

# The ordered run-level phases the leader advances through. `run-advance`
# accepts any of these; the `next_owner` it records (validated against
# RUN_OWNERS) is stored as given. The banner does not read it: it takes
# the owner from its phase model and the blocking gate. This list
# is the registry's view; the authoritative phase model with owners
# lives in msd_next.py.
RUN_PHASES = [
    "plan",
    "dispatch+verify",
    "build",
    "report",
    "human-review",
    "reconcile",
    "land-approval",
    "push",
    "record",
    "done",
]
RUN_OWNERS = {"human", "agent"}

# The valid lifecycle of a builder lane. `register` seeds `proposed`;
# every other state is reachable only through `confirm` (proposed ->
# assigned) and `update --status` along
# this ordered chain (with the two terminal exits off `reported`).
STATUS_ORDER = [
    "proposed",
    "assigned",
    "in-progress",
    "reported",
]
TERMINAL_STATES = {"landed", "aborted"}

# The human gate that must be cleared (by `run-clear-gate`) before any
# lane may be marked `landed`: the operator's review of the held diffs.
REVIEW_GATE = "human-review"
ALL_STATES = set(STATUS_ORDER) | TERMINAL_STATES

# Allowed status transitions: each linear step forward, plus the two
# terminal exits off `reported`. `confirm` uses proposed->assigned.
ALLOWED_TRANSITIONS = {
    "proposed": {"assigned"},
    "assigned": {"in-progress"},
    "in-progress": {"reported"},
    "reported": {"landed", "aborted"},
    "landed": set(),
    "aborted": set(),
}

# Transitions allowed by `update --status`. Identical to ALLOWED_TRANSITIONS
# except proposed -> assigned is blocked here: only `confirm` may do that
# transition (it is the signal to send the build-go prompt).
_UPDATE_TRANSITIONS = {
    "proposed": set(),
    "assigned": {"in-progress"},
    "in-progress": {"reported"},
    "reported": {"landed", "aborted"},
    "landed": set(),
    "aborted": set(),
}


def utc_now() -> str:
    """Current UTC time as an ISO-8601 string with a trailing Z."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_lane(lane: str) -> str:
    """Validate + normalize one repo-relative posix lane path.

    Rejects absolute paths and any `..` traversal component, then
    collapses `.`/redundant separators so overlap comparison is exact.
    Raises ValueError on a rejected lane.
    """
    if not lane or not lane.strip():
        raise ValueError("empty lane path")

    pure = PurePosixPath(lane)
    if pure.is_absolute():
        raise ValueError(f"absolute lane path not allowed: {lane}")

    parts = []
    for part in pure.parts:
        if part == ".":
            continue
        if part == "..":
            raise ValueError(f"'..' not allowed in lane path: {lane}")
        parts.append(part)

    if not parts:
        raise ValueError(f"lane path normalizes to empty: {lane}")

    return str(PurePosixPath(*parts))


def lanes_overlap(a: str, b: str) -> bool:
    """True when two normalized lanes conflict.

    Overlap is exact, ancestor, or descendant: `src` conflicts with
    `src`, with `src/auth`, and with any deeper path under `src`. A
    shared path prefix that is not a full path component (for example
    `src/a` vs `src/ab`) does NOT conflict.
    """
    if a == b:
        return True

    a_parts = PurePosixPath(a).parts
    b_parts = PurePosixPath(b).parts
    shorter, longer = sorted((a_parts, b_parts), key=len)
    # An ancestor relationship requires every component of the shorter
    # path to match the corresponding component of the longer path.
    return longer[: len(shorter)] == shorter


def read_registry(path: str) -> dict[str, Any] | None:
    """Load the registry JSON object, or None when absent.

    Any prior `schema_version` (for example a schema-1 registry with no
    `run` object) loads unchanged; missing keys are treated as absent,
    not as an error. A subsequent `write_registry` upgrades the recorded
    `schema_version` to the current one.
    """
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle)

    if isinstance(value, dict):
        return value

    raise ValueError(f"{path} does not contain a JSON object")


def write_registry(path: str, registry: dict[str, Any]) -> None:
    """Write the registry via one fixed temp file + os.replace.

    A single writer never leaves a torn file. Two writers at once
    share the temp file and are not protected.

    Every write stamps the current `schema_version`, so an older
    registry is upgraded in place the first time the leader mutates it.
    """
    registry["schema_version"] = SCHEMA_VERSION
    registry["updated_at"] = utc_now()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = os.path.join(directory, f".{os.path.basename(path)}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def empty_registry(leader: str) -> dict[str, Any]:
    """A fresh registry skeleton owned by `leader`."""
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": utc_now(),
        "leader": leader,
        "followers": {},
    }


def read_lock_metadata(lock_path: str) -> dict[str, Any] | None:
    """Read the swe-day lock's metadata.json, or None when absent."""
    metadata_path = os.path.join(lock_path, METADATA_NAME)
    if not os.path.exists(metadata_path):
        return None

    with open(metadata_path, "r", encoding="utf-8") as handle:
        value = json.load(handle)

    if isinstance(value, dict):
        lock_ver = value.get("schema_version")
        if lock_ver is not None and lock_ver != LOCK_SCHEMA_VERSION:
            raise ValueError(
                f"lock schema version mismatch: expected {LOCK_SCHEMA_VERSION}, "
                f"got {lock_ver}; lock may be from a different "
                "swe_day_lock.py version"
            )
        return value

    raise ValueError(f"{metadata_path} does not contain a JSON object")


def verify_lock(args: argparse.Namespace) -> tuple[bool, str]:
    """Prove the caller holds the swe-day lock for a mutation.

    Returns (ok, reason). A mutation must pass `--lock-owner` matching
    the lock's `owner`; when the lock records a `session_id`, the
    caller's `--session-id` must match it too. A registry with no
    `--lock-path` configured is treated as lock-exempt for local
    tooling/tests; the returned reason says so, and nothing is
    printed.
    """
    lock_path = getattr(args, "lock_path", None)
    if not lock_path:
        return True, "no lock-path configured; mutation not lock-guarded"

    metadata = read_lock_metadata(lock_path)
    if metadata is None:
        return False, f"no lock held at {lock_path}; refusing mutation"

    lock_owner = getattr(args, "lock_owner", None)
    if not lock_owner:
        return False, "mutation requires --lock-owner to prove lock ownership"

    if metadata.get("owner") != lock_owner:
        return (
            False,
            f"lock owner mismatch: held by {metadata.get('owner')!r}, "
            f"caller passed {lock_owner!r}",
        )

    lock_session = metadata.get("session_id")
    if lock_session:
        if getattr(args, "session_id", None) != lock_session:
            return (
                False,
                "lock session mismatch: caller --session-id does not "
                "match the held lock",
            )

    return True, "lock ownership verified"


def require_lock(args: argparse.Namespace) -> int | None:
    """Enforce lock ownership; return an exit code on failure else None."""
    ok, reason = verify_lock(args)
    if not ok:
        print(reason, file=sys.stderr)
        return 3
    return None


def find_conflict(
    registry: dict[str, Any],
    slug: str,
    lanes: list[str],
) -> tuple[str, str, str] | None:
    """Find the first lane that overlaps another builder's lane.

    Conflicts are checked against every OTHER slug — `proposed` lanes
    conflict too — except those whose status is `aborted`. An aborted
    lane is abandoned and never landed, so it must not block a fresh
    `register` of the same lane without an explicit `release`. `landed`
    lanes still block: those files are in main. Returns
    (other_slug, new_lane, existing_lane) on a conflict, else None.
    """
    followers = registry.get("followers", {})
    for other_slug, record in followers.items():
        if other_slug == slug:
            continue
        if record.get("status") == "aborted":
            continue
        existing = record.get("lanes", [])
        for new_lane in lanes:
            for existing_lane in existing:
                if lanes_overlap(new_lane, existing_lane):
                    return other_slug, new_lane, existing_lane
    return None


def command_init(args: argparse.Namespace) -> int:
    """Create the registry skeleton if it does not already exist."""
    existing = read_registry(args.registry)
    if existing is not None:
        print(json.dumps(existing, indent=2, sort_keys=True))
        return 0

    failure = require_lock(args)
    if failure is not None:
        return failure

    registry = empty_registry(args.leader)
    write_registry(args.registry, registry)
    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


def command_register(args: argparse.Namespace) -> int:
    """Register a builder's proposed lanes, refusing any overlap."""
    failure = require_lock(args)
    if failure is not None:
        return failure

    try:
        lanes = [normalize_lane(lane) for lane in args.lane]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not lanes:
        print("register requires at least one --lane", file=sys.stderr)
        return 2

    registry = read_registry(args.registry)
    if registry is None:
        print(
            f"registry not initialized at {args.registry!r} — "
            "run `init --leader <slug>` first",
            file=sys.stderr,
        )
        return 1

    conflict = find_conflict(registry, args.slug, lanes)
    if conflict is not None:
        other_slug, new_lane, existing_lane = conflict
        print(
            f"lane conflict: {new_lane!r} overlaps {existing_lane!r} "
            f"held by {other_slug!r}",
            file=sys.stderr,
        )
        return 4

    registry.setdefault("followers", {})[args.slug] = {
        "role": args.role,
        "lanes": lanes,
        "day": args.day,
        "plan_path": args.plan_path,
        "model": args.model,
        "effort": args.effort,
        "status": "proposed",
        "commit": None,
        "propose": None,
        "updated_at": utc_now(),
    }
    write_registry(args.registry, registry)
    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


def command_confirm(args: argparse.Namespace) -> int:
    """Promote a builder's lanes from proposed to assigned.

    Refused (exit 5) without `--propose`: the builder's PROPOSE reply is
    the verify-before-implement step, and it is recorded on the row.
    """
    failure = require_lock(args)
    if failure is not None:
        return failure

    registry = read_registry(args.registry)
    if registry is None:
        print(f"no registry at {args.registry}", file=sys.stderr)
        return 1

    record = registry.get("followers", {}).get(args.slug)
    if record is None:
        print(f"no such builder: {args.slug}", file=sys.stderr)
        return 1

    current = record.get("status")
    if "assigned" not in ALLOWED_TRANSITIONS.get(current, set()):
        print(
            f"cannot confirm from status {current!r} "
            "(only proposed -> assigned)",
            file=sys.stderr,
        )
        return 5

    propose = (args.propose or "").strip()
    if not propose:
        print(
            f"cannot confirm {args.slug!r}: no PROPOSE recorded; run the "
            "verify-before-implement gate and pass --propose <propose-ref> "
            "(the PROPOSE reference)",
            file=sys.stderr,
        )
        return 5

    record["status"] = "assigned"
    record["propose"] = propose
    record["updated_at"] = utc_now()
    write_registry(args.registry, registry)
    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


def landing_refusal(registry: dict[str, Any]) -> str | None:
    """Why no lane may be marked `landed` now, or None when it may.

    A lane lands only after the operator cleared the human-review gate
    (`run-clear-gate human-review`) and while no human gate is pending.
    """
    run = registry.get("run")
    if not isinstance(run, dict):
        run = {}
    pending = run.get("blocking_gate")
    if pending:
        return (
            f"human gate {pending!r} is pending; the operator clears it "
            f"with `run-clear-gate {pending}`"
        )
    if REVIEW_GATE not in (run.get("cleared_gates") or []):
        return (
            f"the {REVIEW_GATE!r} gate has not been cleared; record it with "
            f"`run-advance --phase {REVIEW_GATE} --owner human --gate "
            f"{REVIEW_GATE}` and have the operator run "
            f"`run-clear-gate {REVIEW_GATE}`"
        )
    return None


def command_update(args: argparse.Namespace) -> int:
    """Advance a builder's status along the allowed transition chain."""
    failure = require_lock(args)
    if failure is not None:
        return failure

    if args.status not in ALL_STATES:
        print(
            f"unknown status {args.status!r}; valid: "
            f"{sorted(ALL_STATES)}",
            file=sys.stderr,
        )
        return 2

    registry = read_registry(args.registry)
    if registry is None:
        print(f"no registry at {args.registry}", file=sys.stderr)
        return 1

    record = registry.get("followers", {}).get(args.slug)
    if record is None:
        print(f"no such builder: {args.slug}", file=sys.stderr)
        return 1

    current = record.get("status")
    if args.status not in _UPDATE_TRANSITIONS.get(current, set()):
        print(
            f"illegal transition {current!r} -> {args.status!r}; "
            f"allowed from {current!r}: "
            f"{sorted(_UPDATE_TRANSITIONS.get(current, set()))}"
            " (use `confirm` for proposed -> assigned)",
            file=sys.stderr,
        )
        return 5

    if args.status == "landed":
        refusal = landing_refusal(registry)
        if refusal is not None:
            print(
                f"cannot mark {args.slug!r} landed: {refusal}",
                file=sys.stderr,
            )
            return 5

    record["status"] = args.status
    if args.commit is not None:
        record["commit"] = args.commit
    record["updated_at"] = utc_now()
    write_registry(args.registry, registry)
    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


def command_release(args: argparse.Namespace) -> int:
    """Remove a builder from the registry, freeing its lanes."""
    failure = require_lock(args)
    if failure is not None:
        return failure

    registry = read_registry(args.registry)
    if registry is None:
        print(f"no registry at {args.registry}", file=sys.stderr)
        return 1

    followers = registry.get("followers", {})
    if args.slug not in followers:
        print(f"no such builder: {args.slug}", file=sys.stderr)
        return 1

    del followers[args.slug]
    write_registry(args.registry, registry)
    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


def command_status(args: argparse.Namespace) -> int:
    """Print the whole registry, or one builder's record (read-only)."""
    registry = read_registry(args.registry)
    if registry is None:
        print(
            json.dumps(
                {"exists": False, "registry": args.registry},
                indent=2,
                sort_keys=True,
            ),
        )
        return 0

    if args.slug:
        record = registry.get("followers", {}).get(args.slug)
        if record is None:
            print(f"no such builder: {args.slug}", file=sys.stderr)
            return 1
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0

    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


def command_run_advance(args: argparse.Namespace) -> int:
    """Set the top-level `run` next-action object (lock-guarded).

    The leader calls this to record the run's current phase, who owns
    the next action, the human gate blocking it (when any), and a short
    note. It is a leader-only mutation, so it verifies the held lock's
    owner/session exactly like the lane commands.
    """
    failure = require_lock(args)
    if failure is not None:
        return failure

    if args.phase not in RUN_PHASES:
        print(
            f"unknown phase {args.phase!r}; valid: {RUN_PHASES}",
            file=sys.stderr,
        )
        return 2

    if args.owner not in RUN_OWNERS:
        print(
            f"unknown owner {args.owner!r}; valid: {sorted(RUN_OWNERS)}",
            file=sys.stderr,
        )
        return 2

    # Seed the skeleton when absent so the very first run-state write
    # does not require a separate `init` (`register` does require one).
    registry = read_registry(args.registry)
    if registry is None:
        registry = empty_registry(args.lock_owner or "leader")

    # Cleared gates survive a run-advance; recording a gate again makes
    # it pending again, so it leaves the cleared list.
    previous = registry.get("run")
    cleared = []
    if isinstance(previous, dict):
        cleared = list(previous.get("cleared_gates") or [])
    if args.gate in cleared:
        cleared.remove(args.gate)

    registry["run"] = {
        "phase": args.phase,
        "next_owner": args.owner,
        "blocking_gate": args.gate,
        "note": args.note,
        "cleared_gates": cleared,
        "updated_at": utc_now(),
    }
    write_registry(args.registry, registry)
    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


def command_run_clear_gate(args: argparse.Namespace) -> int:
    """Clear `run.blocking_gate` when it matches (operator gate-clear).

    This is the operator's act of clearing a human gate. It is still a
    lock-guarded leader-side mutation (the operator clears the gate
    through the leader, which holds the lock). It clears the gate only
    when the named gate is the one currently blocking; a mismatch is
    refused so a stale clear cannot silently unblock a different gate.
    """
    failure = require_lock(args)
    if failure is not None:
        return failure

    registry = read_registry(args.registry)
    if registry is None:
        print(f"no registry at {args.registry}", file=sys.stderr)
        return 1

    run = registry.get("run")
    if not isinstance(run, dict):
        print("no run object to clear a gate on", file=sys.stderr)
        return 1

    current = run.get("blocking_gate")
    if current != args.gate:
        print(
            f"blocking gate mismatch: registry holds {current!r}, "
            f"caller passed {args.gate!r}",
            file=sys.stderr,
        )
        return 5

    run["blocking_gate"] = None
    cleared = list(run.get("cleared_gates") or [])
    if current not in cleared:
        cleared.append(current)
    run["cleared_gates"] = cleared
    run["updated_at"] = utc_now()
    write_registry(args.registry, registry)
    print(json.dumps(registry, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for every subcommand."""
    parser = argparse.ArgumentParser(
        description="Manage the multi-swe-day disjoint-lane registry.",
    )
    parser.add_argument(
        "--registry",
        default="handoff/multi-swe-day.json",
        help="Path to the registry JSON file.",
    )
    parser.add_argument(
        "--lock-path",
        default=None,
        help="Path to the held swe-day lock directory (for "
        "lock-owner verification on mutations).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init / adopt — create the skeleton.
    init = subparsers.add_parser("init", aliases=["adopt"])
    init.add_argument("--leader", required=True)
    init.add_argument("--lock-owner")
    init.add_argument("--session-id")
    init.set_defaults(handler=command_init)

    # register — propose a builder's lanes.
    register = subparsers.add_parser("register")
    register.add_argument("--slug", required=True)
    register.add_argument("--role", required=True)
    register.add_argument("--day", required=True)
    register.add_argument("--plan-path", required=True)
    register.add_argument("--model", default=None)
    register.add_argument("--effort", default=None)
    register.add_argument("--leader", default=None)
    register.add_argument(
        "--lane",
        action="append",
        default=[],
        help="Repo-relative posix lane path (repeatable).",
    )
    register.add_argument("--lock-owner")
    register.add_argument("--session-id")
    register.set_defaults(handler=command_register)

    # confirm — proposed -> assigned.
    confirm = subparsers.add_parser("confirm")
    confirm.add_argument("--slug", required=True)
    confirm.add_argument(
        "--propose",
        default=None,
        help="The PROPOSE reference: the envelope id of the builder's "
        "PROPOSE response (the verify step), or the path of the file "
        "holding the finding; required.",
    )
    confirm.add_argument("--lock-owner")
    confirm.add_argument("--session-id")
    confirm.set_defaults(handler=command_confirm)

    # update — advance status along the chain.
    update = subparsers.add_parser("update")
    update.add_argument("--slug", required=True)
    update.add_argument("--status", required=True)
    update.add_argument("--commit", default=None)
    update.add_argument("--lock-owner")
    update.add_argument("--session-id")
    update.set_defaults(handler=command_update)

    # release — drop a builder, freeing its lanes.
    release = subparsers.add_parser("release")
    release.add_argument("--slug", required=True)
    release.add_argument("--lock-owner")
    release.add_argument("--session-id")
    release.set_defaults(handler=command_release)

    # status — read-only inspection.
    status = subparsers.add_parser("status")
    status.add_argument("--slug", default=None)
    status.set_defaults(handler=command_status)

    # run-advance — set the run-level next-action object.
    run_advance = subparsers.add_parser("run-advance")
    run_advance.add_argument("--phase", required=True)
    run_advance.add_argument("--owner", required=True)
    run_advance.add_argument("--gate", default=None)
    run_advance.add_argument("--note", default=None)
    run_advance.add_argument("--lock-owner")
    run_advance.add_argument("--session-id")
    run_advance.set_defaults(handler=command_run_advance)

    # run-clear-gate — the operator clears a blocking human gate.
    run_clear = subparsers.add_parser("run-clear-gate")
    run_clear.add_argument("gate")
    run_clear.add_argument("--lock-owner")
    run_clear.add_argument("--session-id")
    run_clear.set_defaults(handler=command_run_clear_gate)

    return parser


def main(argv: list[str]) -> int:
    """Parse arguments and dispatch to the selected subcommand."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
