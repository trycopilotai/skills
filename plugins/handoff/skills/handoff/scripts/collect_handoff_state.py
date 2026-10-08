#!/usr/bin/env python3
"""Collect repository state for handoff documents; writes no file."""

# Exit status: 0 with a report on stdout; 1 when --repo is not
# inside a git working tree (checked first); 2 for a usage error,
# including a --state-file that is absolute, resolves outside
# the repository root, or cannot be resolved.

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_git(repo: Path, args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Keep leading whitespace: in `git status --porcelain` it is the
    # first column of a line, and the first line is part of the output.
    return proc.returncode, proc.stdout.rstrip(), proc.stderr.strip()


def git_value(repo: Path, args: list[str], default: str = "") -> str:
    code, stdout, _ = run_git(repo, args)
    if code != 0:
        return default
    return stdout


def repo_root(path: Path) -> Path:
    code, stdout, stderr = run_git(path, ["rev-parse", "--show-toplevel"])
    if code != 0:
        raise SystemExit(f"not a git repository: {path}\n{stderr}")
    return Path(stdout).resolve()


def ahead_behind(repo: Path) -> dict[str, Any]:
    upstream = git_value(
        repo,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
    )
    if not upstream:
        return {"upstream": "", "ahead": None, "behind": None}

    counts = git_value(repo, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
    if not counts:
        return {"upstream": upstream, "ahead": None, "behind": None}

    ahead_s, behind_s = counts.split()[:2]
    return {"upstream": upstream, "ahead": int(ahead_s), "behind": int(behind_s)}


def parse_submodule_paths(lines: list[str]) -> list[str]:
    """Paths from `git submodule status` lines.

    A line is a status character, the commit, a space, the path,
    and for a checked-out submodule ` (<describe>)`. The path may
    hold spaces.
    """
    paths: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        parts = line[1:].split(" ", 1)
        if len(parts) < 2 or not parts[1]:
            continue
        path = parts[1]
        if path.endswith(")") and " (" in path:
            path = path[: path.rindex(" (")]
        paths.append(path)
    return paths


def is_own_checkout(path: Path) -> bool:
    """True when git sees `path` as the top of its own worktree."""
    code, stdout, _ = run_git(path, ["rev-parse", "--show-toplevel"])
    if code != 0:
        return False
    return Path(stdout).resolve() == path.resolve()


def submodule_details(repo: Path, submodule_lines: list[str]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for rel_path in parse_submodule_paths(submodule_lines):
        path = repo / rel_path
        if not os.path.isdir(path):
            details.append({"path": rel_path, "exists": False, "status": []})
            continue
        if not is_own_checkout(path):
            # An uninitialized submodule's directory belongs to the
            # parent; `git status` there would describe the parent.
            details.append(
                {"path": rel_path, "exists": True, "checked_out": False, "status": []}
            )
            continue
        code, stdout, stderr = run_git(path, ["status", "--short", "--branch"])
        details.append(
            {
                "path": rel_path,
                "exists": True,
                "checked_out": True,
                "status": stdout.splitlines() if code == 0 and stdout else [],
                "error": stderr if code != 0 else "",
            }
        )
    return details


DEFAULT_STATE_FILE = "handoff/state.json"


def state_path(repo: Path, relative: str) -> Path | None:
    """The state file under the root, or None if it is refused.

    Refused: an absolute path, one that resolves outside the root,
    and one that cannot be resolved.
    """
    if Path(relative).is_absolute():
        return None
    try:
        path = (repo / relative).resolve()
        path.relative_to(repo)
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        # A missing file inside the root is reported, not refused,
        # including when a parent component is a regular file.
        return path
    except (OSError, RuntimeError, ValueError):
        # Outside the root, or not resolvable (a symlink loop, or a
        # path component that cannot be searched).
        return None
    return path


def shape_error(raw: Any) -> str:
    """Why a parsed state file cannot be summarized, or ""."""
    if not isinstance(raw, dict):
        return "the top level is not a JSON object"
    agents = raw.get("agents", [])
    if not isinstance(agents, list):
        return "agents is not a list"
    for index, item in enumerate(agents):
        if not isinstance(item, dict):
            return f"agents[{index}] is not an object"
        if not isinstance(item.get("owned_scopes", []), list):
            return f"agents[{index}].owned_scopes is not a list"
    return ""


def handoff_state(repo: Path, relative: str = DEFAULT_STATE_FILE) -> dict[str, Any]:
    path = repo / relative
    try:
        present = path.exists()
    except OSError as exc:
        return {"present": True, "path": relative, "error": str(exc), "agents": []}
    if not present:
        return {"present": False, "path": relative, "agents": []}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface parse/read failures.
        return {
            "present": True,
            "path": relative,
            "error": str(exc),
            "agents": [],
        }

    problem = shape_error(raw)
    if problem:
        return {
            "present": True,
            "path": relative,
            "error": problem,
            "agents": [],
        }

    agents: list[dict[str, Any]] = []
    for item in raw.get("agents", []):
        scopes = item.get("owned_scopes", [])
        agents.append(
            {
                "agent_id": item.get("agent_id", ""),
                "owner": item.get("owner", ""),
                "model": item.get("model", ""),
                "surface": item.get("surface", ""),
                "chat_uuid": item.get("chat_uuid", ""),
                "status": item.get("status", ""),
                "detail_path": item.get("detail_path", ""),
                "owned_scopes": [
                    {
                        "name": scope.get("name", ""),
                        "paths": scope.get("paths", []),
                    }
                    for scope in scopes
                    if isinstance(scope, dict)
                ],
                "updated_at": item.get("updated_at", ""),
            }
        )

    return {
        "present": True,
        "path": relative,
        "schema_version": raw.get("schema_version"),
        "updated_at": raw.get("updated_at", ""),
        "agents": agents,
    }


def collect(
    repo_arg: str, recent: int, state_file: str = DEFAULT_STATE_FILE
) -> dict[str, Any]:
    root = repo_root(Path(repo_arg).resolve())
    if state_path(root, state_file) is None:
        print(
            f"--state-file must be a relative path that resolves inside {root}: {state_file}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    branch = git_value(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    head = git_value(root, ["rev-parse", "--short", "HEAD"])
    full_head = git_value(root, ["rev-parse", "HEAD"])
    status = git_value(root, ["status", "--short", "--branch"])
    porcelain = git_value(root, ["status", "--porcelain=v1"])
    log = git_value(root, ["log", "--oneline", "--decorate", f"-n{recent}"])
    submodules = git_value(root, ["submodule", "status", "--recursive"])

    submodule_lines = submodules.splitlines() if submodules else []
    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "repo": str(root),
        "branch": branch,
        "head": head,
        "full_head": full_head,
        **ahead_behind(root),
        "status": status.splitlines() if status else [],
        "dirty_files": porcelain.splitlines() if porcelain else [],
        "recent_commits": log.splitlines() if log else [],
        "submodules": submodule_lines,
        "submodule_details": submodule_details(root, submodule_lines),
        "handoff_state": handoff_state(root, state_file),
        "collector": os.path.relpath(__file__, root)
        if Path(__file__).resolve().is_relative_to(root)
        else str(Path(__file__).resolve()),
    }


def text(value: Any) -> str:
    """A registry value as one line of text; JSON null is empty."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return json.dumps(value)
    # A lone surrogate from JSON cannot be printed; show it as "?".
    printable = str(value).encode("utf-8", "replace").decode("utf-8")
    return " ".join(printable.split())


def cell(value: Any) -> str:
    """One Markdown table cell: one line, `\\` and `|` escaped."""
    return text(value).replace("\\", "\\\\").replace("|", "\\|")


def owner_or_agent_id(agent: dict[str, Any]) -> Any:
    """The owner, or the agent_id when the owner is missing, null or ""."""
    owner = agent.get("owner")
    if owner is None or owner == "":
        return agent.get("agent_id", "")
    return owner


def fenced(lines: list[str]) -> str:
    if not lines:
        return "_None._"
    return "```text\n" + "\n".join(lines) + "\n```"


def render_markdown(data: dict[str, Any]) -> str:
    upstream = data["upstream"] or "(none)"
    ahead = data["ahead"] if data["ahead"] is not None else "unknown"
    behind = data["behind"] if data["behind"] is not None else "unknown"

    parts = [
        "# Handoff State Collection",
        "",
        f"- Generated UTC: `{data['generated_at_utc']}`",
        f"- Repo: `{data['repo']}`",
        f"- Branch: `{data['branch']}`",
        f"- HEAD: `{data['head']}` (`{data['full_head']}`)",
        f"- Upstream: `{upstream}`",
        f"- Ahead / behind: `{ahead}` / `{behind}`",
        "",
        "## Status",
        "",
        fenced(data["status"]),
        "",
        "## Dirty Files",
        "",
        fenced(data["dirty_files"]),
        "",
        "## Recent Commits",
        "",
        fenced(data["recent_commits"]),
        "",
        "## Submodules",
        "",
        fenced(data["submodules"]),
        "",
        "## Nested Submodule Status",
        "",
    ]

    nested: list[str] = []
    for detail in data["submodule_details"]:
        nested.append(f"### {detail['path']}")
        if not detail["exists"]:
            nested.append("missing on disk")
        elif not detail.get("checked_out", True):
            nested.append("not checked out")
        elif detail.get("error"):
            nested.append(detail["error"])
        elif detail["status"]:
            nested.extend(detail["status"])
        else:
            nested.append("clean")
        nested.append("")

    parts.append("\n".join(nested).strip() or "_No submodules._")
    parts.extend(
        [
            "",
            "## Agent Ownership Summary",
            "",
        ]
    )

    state = data["handoff_state"]
    if not state.get("present"):
        parts.append(f"_No {state['path']} present._")
    elif state.get("error"):
        parts.append(f"`{state['path']}` could not be parsed: {state['error']}")
    elif not state.get("agents"):
        parts.append(f"`{state['path']}` is present but has no agents.")
    else:
        parts.append(
            "| Agent | Model / Surface | Session | Status | Detail | Scopes | Updated |"
        )
        parts.append("| --- | --- | --- | --- | --- | --- | --- |")
        for agent in state["agents"]:
            model_surface = f"{text(agent.get('model'))} / {text(agent.get('surface'))}".strip()
            scopes = ", ".join(
                text(scope.get("name")) for scope in agent.get("owned_scopes", [])
            )
            parts.append(
                "| "
                + " | ".join(
                    cell(value)
                    for value in [
                        owner_or_agent_id(agent),
                        model_surface,
                        agent.get("chat_uuid", ""),
                        agent.get("status", ""),
                        agent.get("detail_path", ""),
                        scopes,
                        agent.get("updated_at", ""),
                    ]
                )
                + " |"
            )
    parts.append("")
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository path to inspect")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    parser.add_argument("--recent", type=int, default=8, help="recent commit count")
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help="agent registry, relative to the repository root "
        f"(default: {DEFAULT_STATE_FILE})",
    )
    args = parser.parse_args(argv)

    data = collect(args.repo, args.recent, args.state_file)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(render_markdown(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
