#!/usr/bin/env python3
"""Install this marketplace into both clients and check pickup.

`make validate` reads the marketplace files. It cannot tell
you whether a client agrees with how they were read, and the
two have disagreed: `metadata.pluginRoot` looks like a base
directory for every plugin `source`, validates cleanly, and is
ignored by Claude Code, which resolves `source` against the
marketplace root and then fails at install time. Nothing in
this repository caught that, because nothing in this
repository ran an install.

So this runs one. It copies the checkout somewhere
disposable, points a throwaway client home at it, adds the
marketplace, installs each plugin, and then asks the client
what it actually loaded. Installing is not the assertion:
Claude Code will install a plugin whose skills directory is
empty. The assertion is that the client reports the skill.

No credentials and no model. Every command here is a `plugin`
subcommand, the client homes are temporary directories, and
the API-key variables are cleared before each run so a
configured key cannot make this pass where an unconfigured
one would not.

    python3 tools/install_smoke.gpt.py [--client claude|codex]

Needs npx, and network the first time it fetches a client.
Not part of `make check` for that reason; `make install-smoke`
runs it.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# AGENTS-mandated invocation: both clients are reached through
# npx, never a PATH or Homebrew binary, so the version under
# test is the one named here rather than whatever is installed.
#
# The `--package ... -- <bin>` form is required, not stylistic.
# Given a bare `npx --yes @openai/codex@0.146.0`, npm 11 looks
# for a command named after the whole specifier and reports
# "sh: @openai/codex@0.146.0: No such file or directory". Both
# packages publish a bin whose name is not the package name, so
# naming the package and the binary separately is the only form
# that resolves.
CLAUDE = [
    "npx",
    "--yes",
    "--package",
    "@anthropic-ai/claude-code@2.1.220",
    "--",
    "claude",
]
CODEX = ["npx", "--yes", "--package", "@openai/codex@0.146.0", "--", "codex"]

# Cleared for every client run. A smoke test that passes only
# on a machine with credentials is not testing installation.
CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)


class SmokeFailure(Exception):
    """A client did not do what the marketplace promised."""


def catalogue_entries() -> list:
    """Read the generated catalogue, which records the clients."""
    payload = json.loads((ROOT / "catalogue.json").read_text())
    return payload.get("skills", [])


def run(argv: list, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True)


def client_env(home_var: str, home: Path) -> dict:
    env = os.environ.copy()
    for name in CREDENTIAL_VARS:
        env.pop(name, None)
    env[home_var] = str(home)
    return env


def require(result: subprocess.CompletedProcess, what: str) -> str:
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise SmokeFailure(f"{what} failed:\n{output.strip()}")
    return output


def smoke_lint_runtime(repo: Path) -> None:
    """Run the vendored lint package without repository fallbacks."""
    plugin = repo / "plugins" / "lint"
    runner = plugin / "skills" / "lint" / "run.py"
    if not runner.is_file():
        return

    env = os.environ.copy()
    for name in CREDENTIAL_VARS:
        env.pop(name, None)
    output = require(
        run([sys.executable, str(runner), "--list-languages"], env, repo),
        "lint package runtime",
    )
    try:
        observed = json.loads(output)
        expected = json.loads(
            (runner.parent / "languages.json").read_text(encoding="utf-8")
        )
        matrix = json.loads(
            (runner.parent / "images" / "matrix.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise SmokeFailure(f"lint package data is unreadable: {exc}") from exc
    if observed != expected:
        raise SmokeFailure("lint package loaded a different language manifest")
    if matrix.get("version") != manifest.get("version"):
        raise SmokeFailure(
            "lint package image version disagrees with the plugin version"
        )
    print("  package lint: runtime and data loaded")


def smoke_claude(repo: Path, home: Path, names: list) -> None:
    """Add, install, and confirm the skill is in the inventory."""
    env = client_env("CLAUDE_CONFIG_DIR", home)
    home.mkdir(parents=True, exist_ok=True)
    require(
        run(CLAUDE + ["plugin", "marketplace", "add", str(repo)], env, repo),
        "claude plugin marketplace add",
    )
    for name in names:
        require(
            run(
                CLAUDE + ["plugin", "install", f"{name}@trycopilotai"],
                env,
                repo,
            ),
            f"claude plugin install {name}",
        )
        details = require(
            run(
                CLAUDE + ["plugin", "details", f"{name}@trycopilotai"],
                env,
                repo,
            ),
            f"claude plugin details {name}",
        )
        # The inventory line reads "Skills (1)  <name>". A plugin
        # that installed but shipped nothing loadable reports
        # "Skills (0)", which is the failure worth catching.
        if "Skills (0)" in details or name not in details:
            raise SmokeFailure(
                f"claude installed {name!r} but its inventory has no such "
                f"skill:\n{details.strip()}"
            )
        print(f"  claude  {name}: installed, skill in inventory")


def smoke_codex(repo: Path, home: Path, names: list) -> None:
    """Add, list, and install from the Codex marketplace file."""
    env = client_env("CODEX_HOME", home)
    home.mkdir(parents=True, exist_ok=True)
    require(
        run(CODEX + ["plugin", "marketplace", "add", str(repo)], env, repo),
        "codex plugin marketplace add",
    )
    listed = require(run(CODEX + ["plugin", "list"], env, repo), "codex plugin list")
    for name in names:
        if f"{name}@trycopilotai" not in listed:
            raise SmokeFailure(
                f"codex did not list {name!r} from the marketplace:\n"
                f"{listed.strip()}"
            )
        added = require(
            run(CODEX + ["plugin", "add", f"{name}@trycopilotai"], env, repo),
            f"codex plugin add {name}",
        )
        if "Installed plugin root" not in added:
            raise SmokeFailure(
                f"codex add {name!r} reported no installed root:\n" f"{added.strip()}"
            )
        print(f"  codex   {name}: listed and installed")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--client",
        action="append",
        choices=("claude", "codex"),
        default=[],
        help="run only this client's smoke; repeatable",
    )
    args = ap.parse_args(argv)
    wanted = args.client or ["claude", "codex"]

    entries = catalogue_entries()
    claude_names = [e["name"] for e in entries if "claude-code" in e.get("clients", [])]
    codex_names = [e["name"] for e in entries if "codex" in e.get("clients", [])]

    failures = []
    with tempfile.TemporaryDirectory() as td:
        temporary = Path(td)
        # A copy, not the checkout. Both clients write state next
        # to a local marketplace, and a smoke test must not be
        # able to dirty the tree it is testing.
        repo = temporary / "skills"
        shutil.copytree(
            ROOT,
            repo,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )
        try:
            smoke_lint_runtime(repo)
        except SmokeFailure as exc:
            failures.append(f"package: {exc}")
        arms = {
            "claude": (smoke_claude, temporary / "claude-home", claude_names),
            "codex": (smoke_codex, temporary / "codex-home", codex_names),
        }
        for client in wanted:
            smoke, home, names = arms[client]
            if not names:
                failures.append(f"{client}: no entry declares this client")
                continue
            try:
                smoke(repo, home, names)
            except SmokeFailure as exc:
                failures.append(f"{client}: {exc}")

    if failures:
        print("\nFAIL  install smoke")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"\nOK    install smoke passed for {', '.join(wanted)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
