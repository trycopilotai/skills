#!/usr/bin/env python3
"""The swe-day run lock, and the one state machine behind it.

The lock is one directory inside the repository holding one metadata
file. This program owns the phase model and is the only thing that
decides which human gate is pending; ``swe_day_next.py`` only renders
what it reports.

State is three facts: the phase last recorded, the gates cleared so
far, and who holds the lock. Everything else is derived:

- the recorded phase's own gate is pending until ``clear-gate`` clears
  it;
- otherwise, when the next phase is human-owned, that phase's gate is
  pending, and clearing it moves the run into the phase;
- otherwise the next phase is the agent's.

``set-phase`` never moves backward, never advances past a pending gate,
and never enters a human-owned phase. ``release`` refuses while a gate
is pending unless the operator passes ``--abandon``.

These rules hold within one held lock. ``acquire --phase`` starts a new
run at any phase with no gates cleared, so releasing and acquiring again
is a way around a gate that this program does not police.

The lock is advisory. It coordinates callers that use this program; it
is not a security boundary against a caller that edits the directory
directly. Changes are serialized with ``flock`` on the lock's parent,
so the program needs ``fcntl`` and does not run where that is missing.

Exit codes: 0 done (``status`` for any valid path, and ``release`` when
there is no lock), 2 a usage error or, from ``acquire``, ``set-phase`` and
``clear-gate``, a lock that already exists or is not held, 3 the caller
does not own the lock, 4 a phase or gate refusal, 5 the lock path leaves
the repository, is a symbolic link, cannot be resolved, has a parent
that cannot be created, or sits inside another readable lock, or
``--repo`` is not a directory, 6 the lock's contents are
missing, unusable or unexpected, or the filesystem refused an operation.
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import socket
import stat
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_LOCK_PATH = ".agents/locks/swe-day.lock"
METADATA_NAME = "metadata.json"
SESSION_VARIABLES = ("CODEX_SESSION_ID", "CODEX_THREAD_ID", "SESSION_ID")

EXIT_HELD = 2
EXIT_NOT_OWNER = 3
EXIT_REFUSED = 4
EXIT_PATH = 5
EXIT_UNREADABLE = 6

# One ordered entry per swe-day phase. ``owner`` is the actor that
# performs the phase. ``gate`` is the human action that must clear before
# the NEXT phase may begin; ``None`` means the agent flows straight on.
# The gate names match the operator gates called out in references/steps.md.
PHASE_MODEL: list[dict[str, Any]] = [
    {
        "key": "preflight",
        "step": 0,
        "title": "preflight: confirm the day can run",
        "owner": "agent",
        "gate": None,
    },
    {
        "key": "prerequisite-gate",
        "step": 1,
        "title": "prerequisite gate: resolve dependency markers",
        "owner": "agent",
        "gate": "prerequisite-go",
    },
    {
        "key": "learn-scope",
        "step": 2,
        "title": "learn the work item's scope",
        "owner": "agent",
        "gate": None,
    },
    {
        "key": "plan-interview",
        "step": 3,
        "title": "plan and interview the operator",
        "owner": "agent",
        "gate": "interview-complete",
    },
    {
        "key": "consolidated-plan",
        "step": 5,
        "title": "write the consolidated, decision-complete plan",
        "owner": "agent",
        "gate": "plan-review",
    },
    {
        "key": "final-buyoff",
        "step": 6,
        "title": "operator gives the final go on the plan",
        "owner": "human",
        "gate": "final-buyoff",
    },
    {
        "key": "implement",
        "step": 7,
        "title": "implement the plan in the impl worktree",
        "owner": "agent",
        "gate": None,
    },
    {
        "key": "fix-loop",
        "step": 8,
        "title": "run the bounded fix loop to green",
        "owner": "agent",
        "gate": None,
    },
    {
        "key": "unit-e2e",
        "step": 9,
        "title": "run unit and e2e tests",
        "owner": "agent",
        "gate": None,
    },
    {
        "key": "coverage",
        "step": 10,
        "title": "coverage proof and commit checkpoint 1",
        "owner": "agent",
        "gate": "commit-checkpoint-1",
    },
    {
        "key": "mutation",
        "step": 11,
        "title": "run the mutation-testing audit",
        "owner": "agent",
        "gate": None,
    },
    {
        "key": "present-open",
        "step": 12,
        "title": "present results and open the editor for review",
        "owner": "agent",
        "gate": "code-result-review",
    },
    {
        "key": "address-comments",
        "step": 13,
        "title": "address comments, code review, commit checkpoint 2",
        "owner": "agent",
        "gate": "commit-checkpoint-2",
    },
    {
        "key": "iterate-to-done",
        "step": 14,
        "title": "iterate with the operator until code is done",
        "owner": "agent",
        "gate": None,
    },
    {
        "key": "landing",
        "step": 15,
        "title": "pre-handoff scrub, landing, and fingerprint guard",
        "owner": "agent",
        "gate": "landing-approval",
    },
    {
        "key": "record",
        "step": 16,
        "title": "record handoff, timeline, progress, timesheet",
        "owner": "agent",
        "gate": "commit-checkpoint-3",
    },
    {
        "key": "report",
        "step": 17,
        "title": "report completion and release the lock",
        "owner": "agent",
        "gate": None,
    },
    {
        "key": "done",
        "step": 18,
        "title": "swe-day complete",
        "owner": "agent",
        "gate": None,
    },
]

PHASE_KEYS = [entry["key"] for entry in PHASE_MODEL]
GATE_NAMES = {entry["gate"] for entry in PHASE_MODEL if entry["gate"]}


class Unreadable(Exception):
    """The lock exists but its metadata cannot be used."""


class LockPathError(ValueError):
    """The lock path does not stay inside the repository."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_session() -> str | None:
    for name in SESSION_VARIABLES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def resolve_lock_path(repo_argument: str, lock_argument: str) -> Path:
    """The lock directory, which must sit strictly inside the repository."""
    relative = Path(lock_argument)
    if relative.is_absolute() or ".." in relative.parts:
        raise LockPathError(
            f"lock path must be relative to the repository: {lock_argument}"
        )
    if not relative.name:
        raise LockPathError(f"lock path names no directory: {lock_argument}")
    # Resolve the parent only. The last component is the lock itself and
    # is never followed, so a symbolic link there is refused, dangling
    # or not, instead of being mistaken for its target or for nothing.
    # A path that cannot be resolved at all (a symlink loop, a component
    # that is too long) is refused the same way, not raised.
    try:
        repo = Path(repo_argument).resolve()
        if not repo.is_dir():
            raise LockPathError(
                f"--repo is not an existing directory: {repo_argument}"
            )
        parent = (repo / relative).parent.resolve()
    except (OSError, RuntimeError) as error:
        raise LockPathError(f"the lock path cannot be resolved: {error}")
    if parent != repo and repo not in parent.parents:
        raise LockPathError(
            f"lock path resolves outside the repository: {lock_argument}"
        )
    lock_path = parent / relative.name
    try:
        is_link = stat.S_ISLNK(os.lstat(lock_path).st_mode)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENAMETOOLONG):
            raise LockPathError(f"the lock path cannot be resolved: {error}")
        # Absent, or not examinable; lock_exists decides which.
        is_link = False
    if is_link:
        raise LockPathError(f"lock path is a symbolic link: {lock_argument}")
    return lock_path


def enclosing_lock(lock_path: Path) -> Path | None:
    """A readable lock that the given lock path would sit inside.

    Only a directory whose metadata parses and carries this program's
    fields is recognised. A damaged lock cannot be told apart from an
    ordinary directory, so it is not detected here. The check is best
    effort: it runs before the flock on the inner path's parent, so it
    does not exclude a concurrent acquire of the outer path.
    """
    # Every ancestor is examined, the repository root and above included,
    # so naming a held lock as --repo does not get around the check.
    for ancestor in lock_path.parents:
        try:
            if not stat.S_ISREG(os.lstat(ancestor / METADATA_NAME).st_mode):
                continue
            with (ancestor / METADATA_NAME).open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, ValueError, RecursionError):
            continue
        # An unrelated metadata.json does not make a directory a lock;
        # the fields this program always writes do.
        if isinstance(value, dict) and {"session_id", "work_item"} <= set(value):
            return ancestor
    return None


@contextmanager
def serialized(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on the lock directory's parent."""
    descriptor = os.open(lock_path.parent, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def lock_exists(lock_path: Path) -> bool:
    """Whether anything is at the lock path. An entry that cannot be
    examined counts as present, so a run is never reported idle because
    a directory could not be searched."""
    try:
        os.lstat(lock_path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return True


def load_state(lock_path: Path) -> dict[str, Any]:
    """The lock's metadata, checked, or Unreadable with the reason."""
    metadata_path = lock_path / METADATA_NAME
    try:
        if not stat.S_ISDIR(os.lstat(lock_path).st_mode):
            raise Unreadable(f"{lock_path} is not a lock directory")
        # Only a regular file is opened: a link is not followed and a
        # FIFO or device is not waited on.
        if not stat.S_ISREG(os.lstat(metadata_path).st_mode):
            raise Unreadable(f"{metadata_path} is not a regular file")
    except FileNotFoundError:
        raise Unreadable(f"{metadata_path} is missing")
    except OSError as error:
        raise Unreadable(f"{lock_path} cannot be examined: {error}")
    try:
        with metadata_path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        raise Unreadable(f"{metadata_path} is missing")
    except (OSError, ValueError, RecursionError) as error:
        raise Unreadable(f"{metadata_path} is unreadable: {error}")
    if not isinstance(value, dict):
        raise Unreadable(f"{metadata_path} does not contain a JSON object")
    phase = value.get("phase")
    if not isinstance(phase, str) or phase not in PHASE_KEYS:
        raise Unreadable(f"{metadata_path} records no known phase")
    cleared = value.get("cleared_gates", [])
    if not isinstance(cleared, list) or any(
        not isinstance(gate, str) or gate not in GATE_NAMES for gate in cleared
    ):
        raise Unreadable(f"{metadata_path} records unknown cleared gates")
    if len(set(cleared)) != len(cleared):
        raise Unreadable(f"{metadata_path} records a gate cleared twice")
    # A gate can only have been cleared for a phase the run has reached.
    # Anything else is not a history this program writes, and reading it
    # as valid would let the banner and set-phase disagree.
    reached = {
        entry["gate"] for entry in PHASE_MODEL[: PHASE_KEYS.index(phase) + 1]
    }
    for gate in cleared:
        if gate not in reached:
            raise Unreadable(
                f"{metadata_path} records gate '{gate}' as cleared before "
                "its phase was reached"
            )
    value["cleared_gates"] = cleared
    for field in ("owner", "session_id"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise Unreadable(f"{metadata_path} records no {field}")
    return value


def write_metadata(lock_path: Path, metadata: dict[str, Any]) -> None:
    """Replace the metadata file without following a planted link."""
    metadata_path = lock_path / METADATA_NAME
    tmp_path = lock_path / f".{METADATA_NAME}.tmp"
    if os.path.lexists(tmp_path):
        os.unlink(tmp_path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(tmp_path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, metadata_path)


def phase_entry(key: str) -> dict[str, Any]:
    return PHASE_MODEL[PHASE_KEYS.index(key)]


def following_phase(key: str) -> dict[str, Any] | None:
    index = PHASE_KEYS.index(key)
    if index + 1 >= len(PHASE_MODEL):
        return None
    return PHASE_MODEL[index + 1]


def pending_gate(state: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """The gate the operator must clear now, and the phase it opens.

    The second value is the human-owned phase the run enters when the
    gate clears, or None when clearing leaves the phase unchanged.
    """
    cleared = state["cleared_gates"]
    current = phase_entry(state["phase"])
    if current["gate"] and current["gate"] not in cleared:
        return current["gate"], None
    following = following_phase(state["phase"])
    if following is not None and following["owner"] == "human":
        if following["gate"] not in cleared:
            return following["gate"], following
    return None, None


def describe(state: dict[str, Any]) -> dict[str, Any]:
    """What happens next: the item, its owner, and the pending gate."""
    current = phase_entry(state["phase"])
    gate, opens = pending_gate(state)
    if gate is not None:
        if opens is not None:
            item = opens["title"]
        elif current["owner"] == "human":
            item = current["title"]
        else:
            item = "operator clears gate '%s' (after phase %s)" % (
                gate,
                current["key"],
            )
        return {"owner": "human", "next": item, "gate": gate}
    following = following_phase(state["phase"])
    if following is None:
        return {
            "owner": "agent",
            "next": "release the lock; swe-day complete",
            "gate": None,
        }
    return {"owner": "agent", "next": following["title"], "gate": None}


def lock_age_seconds(metadata: dict[str, Any]) -> int | None:
    acquired_at = metadata.get("acquired_at")
    if not isinstance(acquired_at, str):
        return None
    try:
        acquired = datetime.fromisoformat(acquired_at.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - acquired
    except (ValueError, TypeError):
        return None
    return int(age.total_seconds())


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def report(state: dict[str, Any], lock_path: Path) -> dict[str, Any]:
    """The metadata plus what is derived from it."""
    shown = dict(state)
    summary = describe(state)
    shown["locked"] = True
    shown["lock_path"] = str(lock_path)
    shown["next_owner"] = summary["owner"]
    shown["pending_gate"] = summary["gate"]
    age = lock_age_seconds(state)
    if age is not None:
        shown["age_seconds"] = age
    return shown


def print_status(lock_path: Path) -> int:
    if not lock_exists(lock_path):
        emit({"locked": False, "lock_path": str(lock_path)})
        return 0
    try:
        state = load_state(lock_path)
    except Unreadable as problem:
        emit(
            {
                "locked": True,
                "lock_path": str(lock_path),
                "metadata": "unreadable",
                "reason": str(problem),
            }
        )
        return 0
    emit(report(state, lock_path))
    return 0


def caller_owns_lock(state: dict[str, Any], owner: str, session_id: Any) -> bool:
    return state["owner"] == owner and state["session_id"] == session_id


def unreadable(lock_path: Path, problem: Unreadable) -> int:
    print(
        f"the swe-day lock's metadata cannot be used: {problem}. "
        "This needs human review; nothing was changed.",
        file=sys.stderr,
    )
    print_status(lock_path)
    return EXIT_UNREADABLE


def refuse(lock_path: Path, message: str, code: int) -> int:
    print(message, file=sys.stderr)
    print_status(lock_path)
    return code


def command_acquire(args: argparse.Namespace, lock_path: Path) -> int:
    if not args.session_id:
        print(
            "acquire needs --session-id (or one of %s). The session is half "
            "of the ownership check." % ", ".join(SESSION_VARIABLES),
            file=sys.stderr,
        )
        return 2
    if not args.owner.strip() or not args.session_id.strip():
        print("acquire needs a non-empty --owner and session id.", file=sys.stderr)
        return 2
    if args.proceed_without is not None and any(
        not name.strip() for name in args.proceed_without
    ):
        print("--proceed-without needs a non-empty skill name.", file=sys.stderr)
        return 2
    if args.phase not in PHASE_KEYS:
        print(
            "unknown phase %r. Known phases: %s" % (args.phase, ", ".join(PHASE_KEYS)),
            file=sys.stderr,
        )
        return EXIT_REFUSED

    repo = Path(args.repo).resolve()
    outer = enclosing_lock(lock_path)
    if outer is not None:
        print(
            f"{outer} is itself a lock; a lock cannot be acquired inside "
            "another lock.",
            file=sys.stderr,
        )
        return EXIT_PATH
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"cannot create the lock's parent directory: {error}", file=sys.stderr)
        return EXIT_PATH
    state = {
        "acquired_at": utc_now(),
        "acquired_phase": args.phase,
        "cleared_gates": [],
        "hostname": socket.gethostname(),
        "owner": args.owner,
        "phase": args.phase,
        "pid": os.getpid(),
        "plan_path": args.plan_path,
        "repo": str(repo),
        "scope": args.scope,
        "session_id": args.session_id,
        "work_item": args.work_item,
    }
    if args.proceed_without is not None:
        state["proceed_without"] = list(args.proceed_without)
    with serialized(lock_path):
        try:
            lock_path.mkdir(mode=0o700)
        except FileExistsError:
            return refuse(
                lock_path,
                "swe-day lock already exists; stale locks require human review.",
                EXIT_HELD,
            )
        write_metadata(lock_path, state)
    emit(report(state, lock_path))
    return 0


def command_release(args: argparse.Namespace, lock_path: Path) -> int:
    not_locked = {"released": False, "reason": "not_locked", "lock_path": str(lock_path)}
    if not lock_exists(lock_path):
        emit(not_locked)
        return 0
    with serialized(lock_path):
        if not lock_exists(lock_path):
            emit(not_locked)
            return 0
        try:
            state = load_state(lock_path)
        except Unreadable as problem:
            return unreadable(lock_path, problem)
        if not caller_owns_lock(state, args.owner, args.session_id):
            return refuse(
                lock_path,
                "refusing to release a lock owned by another caller",
                EXIT_NOT_OWNER,
            )
        gate, _ = pending_gate(state)
        if gate is not None and not args.abandon:
            return refuse(
                lock_path,
                f"gate '{gate}' is pending. Releasing would drop it; pass "
                "--abandon on the operator's instruction to end the run anyway.",
                EXIT_REFUSED,
            )
        # Remove only what this program wrote. Anything else inside the
        # directory, such as another lock, is not this caller's to delete.
        # Everything is checked before anything is deleted.
        leftover = f".{METADATA_NAME}.tmp"
        extra = sorted(set(os.listdir(lock_path)) - {METADATA_NAME, leftover})
        if os.path.isdir(lock_path / leftover) and not os.path.islink(
            lock_path / leftover
        ):
            extra.append(leftover)
        if extra:
            return refuse(
                lock_path,
                "the lock directory holds entries this program did not "
                f"write ({', '.join(extra[:5])}); it was left in place for "
                "human review.",
                EXIT_UNREADABLE,
            )
        for name in (leftover, METADATA_NAME):
            if os.path.lexists(lock_path / name):
                os.unlink(lock_path / name)
        os.rmdir(lock_path)
    emit({"released": True, "lock_path": str(lock_path), "released_at": utc_now()})
    return 0


def command_status(args: argparse.Namespace, lock_path: Path) -> int:
    return print_status(lock_path)


def command_set_phase(args: argparse.Namespace, lock_path: Path) -> int:
    if args.phase not in PHASE_KEYS:
        print(
            "unknown phase %r. Known phases: %s" % (args.phase, ", ".join(PHASE_KEYS)),
            file=sys.stderr,
        )
        return EXIT_REFUSED
    if not lock_exists(lock_path):
        return refuse(
            lock_path,
            "no swe-day lock is held; acquire one before setting a phase.",
            EXIT_HELD,
        )
    with serialized(lock_path):
        if not lock_exists(lock_path):
            return refuse(lock_path, "no swe-day lock is held.", EXIT_HELD)
        try:
            state = load_state(lock_path)
        except Unreadable as problem:
            return unreadable(lock_path, problem)
        if not caller_owns_lock(state, args.owner, args.session_id):
            return refuse(
                lock_path,
                "refusing to set the phase on a lock owned by another caller",
                EXIT_NOT_OWNER,
            )
        current = PHASE_KEYS.index(state["phase"])
        target = PHASE_KEYS.index(args.phase)
        if target < current:
            return refuse(
                lock_path,
                f"the run is at phase {state['phase']}; set-phase does not move "
                "backward.",
                EXIT_REFUSED,
            )
        if target > current:
            gate, _ = pending_gate(state)
            if gate is not None:
                return refuse(
                    lock_path,
                    f"gate '{gate}' is pending; only clear-gate removes it. "
                    "The phase was not changed.",
                    EXIT_REFUSED,
                )
            for entry in PHASE_MODEL[current + 1 : target + 1]:
                if entry["owner"] == "human":
                    return refuse(
                        lock_path,
                        f"phase {entry['key']} is the operator's; the run "
                        f"enters it when clear-gate clears '{entry['gate']}'.",
                        EXIT_REFUSED,
                    )
            for entry in PHASE_MODEL[current + 1 : target]:
                if entry["gate"] and entry["gate"] not in state["cleared_gates"]:
                    return refuse(
                        lock_path,
                        f"gate '{entry['gate']}' of phase {entry['key']} was "
                        f"never cleared; the run cannot skip to {args.phase}.",
                        EXIT_REFUSED,
                    )
        state["phase"] = args.phase
        if args.note is not None:
            state["phase_note"] = args.note
        else:
            state.pop("phase_note", None)
        state["phase_updated_at"] = utc_now()
        write_metadata(lock_path, state)
    emit(report(state, lock_path))
    return 0


def command_clear_gate(args: argparse.Namespace, lock_path: Path) -> int:
    if not lock_exists(lock_path):
        return refuse(
            lock_path, "no swe-day lock is held; nothing to clear.", EXIT_HELD
        )
    with serialized(lock_path):
        if not lock_exists(lock_path):
            return refuse(lock_path, "no swe-day lock is held.", EXIT_HELD)
        try:
            state = load_state(lock_path)
        except Unreadable as problem:
            return unreadable(lock_path, problem)
        if not caller_owns_lock(state, args.owner, args.session_id):
            return refuse(
                lock_path,
                "refusing to clear a gate on a lock owned by another caller",
                EXIT_NOT_OWNER,
            )
        gate, opens = pending_gate(state)
        if gate is None or gate != args.gate:
            emit(
                {
                    "cleared": False,
                    "reason": "gate_mismatch",
                    "pending_gate": gate,
                    "requested_gate": args.gate,
                    "lock_path": str(lock_path),
                }
            )
            return EXIT_REFUSED
        state["cleared_gates"] = state["cleared_gates"] + [gate]
        if opens is not None:
            state["phase"] = opens["key"]
        state["phase_updated_at"] = utc_now()
        write_metadata(lock_path, state)
    emit(report(state, lock_path))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage a swe-day operational repo mutation lock.",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root containing the lock path.",
    )
    parser.add_argument(
        "--lock-path",
        default=DEFAULT_LOCK_PATH,
        help="Repo-relative lock directory path. It must stay inside --repo.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    acquire = subparsers.add_parser("acquire")
    acquire.add_argument("--owner", required=True)
    acquire.add_argument("--work-item", required=True)
    acquire.add_argument("--plan-path", required=True)
    acquire.add_argument("--scope", default="tracked operational repo mutation")
    acquire.add_argument(
        "--phase",
        default="preflight",
        help="The phase the run starts from; one of the modelled phases.",
    )
    acquire.add_argument("--session-id", default=default_session())
    acquire.add_argument(
        "--proceed-without",
        action="append",
        default=None,
        metavar="SKILL",
        help="A delegated skill that is missing and that the operator "
        "explicitly agreed to run without. Repeat for each one.",
    )
    acquire.set_defaults(handler=command_acquire)

    status = subparsers.add_parser("status")
    status.set_defaults(handler=command_status)

    set_phase = subparsers.add_parser("set-phase")
    set_phase.add_argument("--owner", required=True)
    set_phase.add_argument("--phase", required=True)
    set_phase.add_argument("--note", default=None)
    set_phase.add_argument("--session-id", default=default_session())
    set_phase.set_defaults(handler=command_set_phase)

    clear_gate = subparsers.add_parser("clear-gate")
    clear_gate.add_argument("gate")
    clear_gate.add_argument("--owner", required=True)
    clear_gate.add_argument("--session-id", default=default_session())
    clear_gate.set_defaults(handler=command_clear_gate)

    release = subparsers.add_parser("release")
    release.add_argument("--owner", required=True)
    release.add_argument("--session-id", default=default_session())
    release.add_argument(
        "--abandon",
        action="store_true",
        help="End the run even though a human gate is pending.",
    )
    release.set_defaults(handler=command_release)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        lock_path = resolve_lock_path(args.repo, args.lock_path)
    except LockPathError as error:
        print(str(error), file=sys.stderr)
        return EXIT_PATH
    # Notes are free text and a terminal may not be UTF-8; output must
    # not be what stops a status from being printed.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    try:
        return args.handler(args, lock_path)
    except OSError as error:
        print(
            f"the filesystem refused an operation on the lock: {error}. "
            "This needs human review.",
            file=sys.stderr,
        )
        return EXIT_UNREADABLE


if __name__ == "__main__":
    raise SystemExit(main())
