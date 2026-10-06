#!/usr/bin/env python3
"""msd_next — the multi-swe-day Active-Run next-action driver.

The persistent next-action mode for a live multi-swe-day run. Each turn
the leader runs `msd_next.py render` and emits its banner as the first
lines of the reply, so the run's phase, the concrete next item, WHO
owns it (human vs agent), and the current blocking human gate never
drift out of view.

It reads three inputs and improvises nothing:
  - the swe-day lock metadata (is a run live),
  - the registry (`run` object + per-lane `status`es), and
  - the EMBEDDED phase model below (owner + gate per phase).

Phase resolution:
  - An explicit `run.phase` (or a set `run.blocking_gate`) WINS — the
    leader advanced it deliberately and the driver renders that.
  - Otherwise the phase is DERIVED from lane statuses:
      any `proposed`                 -> dispatch+verify (agent)
      any `assigned`/`in-progress`   -> build           (agent)
      all `reported` (none landed)   -> human-review     (HUMAN gate)
      all `landed`                   -> done
      a `reported` + `landed` mix    -> reconcile       (agent)
    (no live lanes, none at all or all aborted -> plan, the opening
    HUMAN gate.)

CRITICAL — the human-gate guard. When the resolved phase is a HUMAN
gate (`plan`, `human-review`, `land-approval`, `push`) OR
`run.blocking_gate`
is set, OWNER renders `human`, the banner names the exact human action,
and the driver presents NO downstream agent action. It must never, for
example, suggest `reconcile` while `human-review` is unmet. The whole
point of the mode is that an unmet human gate is never skipped.

One input is free text. A `run.note` recorded with `run-advance
--note` replaces the action text only in an agent-owned phase with
no blocking gate. In a human-owned phase, or while a gate blocks,
the action stays the operator's and the note is printed on its own
`note:` line. It is printed as one line, control characters removed,
but the driver does not interpret the note: it prints what was
recorded.

One derivation is a guess. With no explicit `run.phase`, a mix of
`reported` and `landed` lanes derives `reconcile`, an agent phase, on
the reading that the leader is part-way through landing. The driver
cannot tell that from landed rows left over beside newly reported
ones, and a status it does not know lands there too. Record the review
gate with `run-advance --phase human-review --owner human --gate
human-review` instead of relying on the derivation. `run.next_owner`
is not read: the owner comes from the phase model and the gate.

Usage:
  msd_next.py --registry handoff/multi-swe-day.json \
      --lock-path .agents/locks/ops-repo.swe-day.lock render

`render` is the only subcommand: advancing the phase and clearing a
gate are lock-guarded registry mutations, owned by
`msd_lane_registry.py` (`run-advance` / `run-clear-gate`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


METADATA_NAME = "metadata.json"

# The ordered run-level phase model: each phase tags its owner and the
# gate (if any) that must clear before the run can leave it. This is the
# authoritative spec the banner renders from; the registry only stores
# the current `run.phase`. `human` owners are the gates that BLOCK the
# next agent action — the human-gate guard keys off `owner == "human"`.
PHASE_MODEL: list[dict[str, str | None]] = [
    {
        "phase": "plan",
        "owner": "human",
        "gate": "plan-approval",
        "action": "operator approves the run plan",
    },
    {
        "phase": "dispatch+verify",
        "owner": "agent",
        "gate": None,
        "action": "leader dispatches lanes; builders verify before build",
    },
    {
        "phase": "build",
        "owner": "agent",
        "gate": None,
        "action": "builders fan out locally and build their lanes",
    },
    {
        "phase": "report",
        "owner": "agent",
        "gate": None,
        "action": "builders report worktree commits to the leader",
    },
    {
        "phase": "human-review",
        "owner": "human",
        "gate": "human-review",
        "action": "operator reviews the held builder diffs",
    },
    {
        "phase": "reconcile",
        "owner": "agent",
        "gate": None,
        "action": "leader merges reported commits into one local main "
        "and re-validates (no push)",
    },
    {
        "phase": "land-approval",
        "owner": "human",
        "gate": "land-approval",
        "action": "operator approves the reconciled landing",
    },
    {
        "phase": "push",
        "owner": "human",
        "gate": "push",
        "action": "operator authorizes the deploy push",
    },
    {
        "phase": "record",
        "owner": "agent",
        "gate": None,
        "action": "leader records the landed run in private state",
    },
    {
        "phase": "done",
        "owner": "agent",
        "gate": None,
        "action": "run complete; nothing pending",
    },
]

# Index the model by phase name for O(1) lookup.
PHASE_BY_NAME = {entry["phase"]: entry for entry in PHASE_MODEL}

# The HUMAN gates, derived from the model. When the resolved phase is
# one of these (or `run.blocking_gate` is set), the driver renders OWNER
# human and presents no downstream agent action.
HUMAN_GATE_PHASES = {
    entry["phase"] for entry in PHASE_MODEL if entry["owner"] == "human"
}


def one_line(value: object) -> str:
    """Free text as one line with no control characters."""
    printable = "".join(ch if ch.isprintable() else " " for ch in str(value))
    return " ".join(printable.split())


def read_lock_metadata(lock_path: str | None) -> dict[str, Any] | None:
    """Read the swe-day lock's metadata.json, or None when absent."""
    if not lock_path:
        return None

    metadata_path = os.path.join(lock_path, METADATA_NAME)
    if not os.path.exists(metadata_path):
        return None

    with open(metadata_path, "r", encoding="utf-8") as handle:
        value = json.load(handle)

    if isinstance(value, dict):
        return value

    raise ValueError(f"{metadata_path} does not contain a JSON object")


def read_registry(path: str) -> dict[str, Any] | None:
    """Load the registry JSON object, or None when absent."""
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle)

    if isinstance(value, dict):
        return value

    raise ValueError(f"{path} does not contain a JSON object")


def active_lane_statuses(registry: dict[str, Any]) -> list[str]:
    """The statuses of every non-aborted lane in the registry.

    Aborted lanes are abandoned, so they do not count toward phase
    derivation — an aborted lane must not, for example, hold the run in
    `build` forever. Returns an empty list when there are no live lanes.
    """
    statuses = []
    for record in registry.get("followers", {}).values():
        status = record.get("status")
        if status == "aborted":
            continue
        statuses.append(status)
    return statuses


def derive_phase(registry: dict[str, Any] | None) -> str:
    """Derive the run phase from lane statuses (no explicit override).

    The derivation, in priority order:
      no live lanes               -> plan (the opening human gate)
      any proposed                -> dispatch+verify
      any assigned/in-progress    -> build
      all reported (none landed)  -> human-review
      all landed                  -> done
      anything else               -> reconcile (a reported/landed mix)
    """
    if registry is None:
        return "plan"

    statuses = active_lane_statuses(registry)
    if not statuses:
        return "plan"

    if any(status == "proposed" for status in statuses):
        return "dispatch+verify"

    if any(status in ("assigned", "in-progress") for status in statuses):
        return "build"

    if all(status == "landed" for status in statuses):
        return "done"

    # Every live lane has been reported (and at least one is not landed):
    # the run is parked at the operator's review gate.
    if all(status == "reported" for status in statuses):
        return "human-review"

    # A mix of reported + landed lanes is mid-reconcile; treat it as the
    # reconcile phase so the agent finishes landing.
    return "reconcile"


def resolve_run(registry: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve the effective run state the banner renders.

    An explicit `run.phase` (or a set `run.blocking_gate`) WINS over the
    derivation; otherwise the phase is derived from lane statuses. The
    resolved phase is then mapped through PHASE_MODEL to its owner, gate,
    and concrete next action. A set `blocking_gate` always forces OWNER
    human regardless of the phase's own owner.

    Returns {phase, owner, gate, action, source, blocked_on, note}; `note`
    is set only when it is shown on its own line.
    """
    run = {}
    if registry is not None and isinstance(registry.get("run"), dict):
        run = registry["run"]

    explicit_phase = run.get("phase")
    blocking_gate = run.get("blocking_gate")

    if explicit_phase in PHASE_BY_NAME:
        phase = explicit_phase
        source = "explicit"
    else:
        phase = derive_phase(registry)
        source = "derived"

    entry = PHASE_BY_NAME[phase]
    owner = entry["owner"]
    gate = entry["gate"]
    action = entry["action"]

    # A blocking_gate set on the run forces a human gate even if the
    # phase's own owner is the agent: the operator must clear it first.
    # When it does, the concrete next action becomes the human clear-gate
    # action — never the agent's own phase action — or the banner would
    # surface downstream agent work while the gate is still unmet.
    if blocking_gate:
        owner = "human"
        gate = blocking_gate
        action = (
            f"operator clears gate {blocking_gate!r} "
            f"(after phase {phase})"
        )

    if owner == "human":
        blocked_on = "operator"
    else:
        blocked_on = "—"

    # A note replaces the action line only in an agent-owned phase. In a
    # human-owned phase, or while a gate blocks, the action stays the
    # operator's and the note is shown on a line of its own.
    note = run.get("note")
    shown_note = None
    if note:
        if owner == "human":
            shown_note = one_line(note)
        else:
            action = one_line(note)

    return {
        "phase": phase,
        "owner": owner,
        "gate": gate,
        "action": action,
        "source": source,
        "blocked_on": blocked_on,
        "note": shown_note,
    }


def render_banner(
    metadata: dict[str, Any] | None,
    registry: dict[str, Any] | None,
) -> str:
    """Render the compact Active-Run banner block (two lines).

    Line 1 is the machine-shaped status; line 2 is the concrete next
    item. When OWNER is human, line 2 names the exact human action, a
    recorded note follows on a `note:` line of its own, and the
    last line states that no downstream agent action is offered until
    the gate clears — the human-gate guard made visible.
    """
    if metadata is None and registry is None:
        return "◦ multi-swe-day INACTIVE · no lock held and no registry"

    resolved = resolve_run(registry)
    phase = resolved["phase"]
    owner = resolved["owner"]
    action = resolved["action"]
    blocked_on = resolved["blocked_on"]

    header = (
        f"▶ multi-swe-day ACTIVE · phase {phase} "
        f"· NEXT: {action} · OWNER: {owner} "
        f"· BLOCKED-ON: {blocked_on}"
    )
    lines = [header, f"  next: {action}"]

    if owner == "human":
        if resolved["note"]:
            lines.append(f"  note: {resolved['note']}")
        gate = resolved["gate"] or phase
        lines.append(
            f"  (gate {gate!r} is unmet — no downstream agent action "
            "is offered until the operator clears it)"
        )

    return "\n".join(lines)


def command_render(args: argparse.Namespace) -> int:
    """Read state and print the banner. Read-only; no lock proof."""
    metadata = read_lock_metadata(args.lock_path)
    registry = read_registry(args.registry)
    print(render_banner(metadata, registry))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the driver."""
    parser = argparse.ArgumentParser(
        description="Render the multi-swe-day Active-Run next-action banner.",
    )
    parser.add_argument(
        "--registry",
        default="handoff/multi-swe-day.json",
        help="Path to the registry JSON file.",
    )
    parser.add_argument(
        "--lock-path",
        default=None,
        help="Path to the held swe-day lock directory.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # render — the only subcommand; phase mutation lives in the registry.
    render = subparsers.add_parser("render")
    render.set_defaults(handler=command_render)

    return parser


def main(argv: list[str]) -> int:
    """Parse arguments and dispatch to the selected subcommand."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
