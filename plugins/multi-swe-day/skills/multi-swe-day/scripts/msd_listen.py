#!/usr/bin/env python3
"""msd_listen — the leader's deduped terminal-message inbox.

The multi-swe-day leader's listener for terminal `response`/`error`
envelopes addressed to it: builder reports, ops-repo payloads,
verify-gate PROPOSE replies, and crash notices. It reads every
envelope across all `gitchat/*-outbox` branches, keeps only the
terminal `response`/`error` messages whose `to` is the leader slug,
dedupes them by `id` against its own seen-file, and prints each new
one as a JSON line.

CRITICAL — this is NOT a prompt poller. `gitchat_poll` already finds
executable `kind:"prompt"` envelopes; it deliberately ignores
`response`/`error`, so it can never surface a builder's report.
`msd_listen` is the mirror image: it handles ONLY the terminal
`response`/`error` envelopes and ignores `prompt`/`progress`/`ack`.
The two run side by side — `gitchat_poll` for new prompts the leader
must answer, `msd_listen` for terminal reports the leader must
collect. Each keeps its own independent seen-state, so marking a
report collected here never affects prompt handling there.

Modes:
  msd_listen.py --slug <leader>             # stream loop: print
                                                # each new terminal as
                                                # a JSON line forever
  msd_listen.py --slug <leader> --once      # print new terminals
                                                # once, then exit
  msd_listen.py --slug <leader> --all       # print every matching
                                                # terminal (ignore seen);
                                                # prints once and exits,
                                                # not a stream loop
  msd_listen.py --slug <leader> --mark-seen <id>
                                                # record one terminal id
                                                # as collected

By default the ids of a printed batch are recorded as seen once the
batch has been printed, so a later run does not re-surface them (a run
killed between the two prints that batch again). Pass `--no-mark` to print without
recording (useful with `--all`, or to inspect before committing
seen-state). Seen-state lives at
`<state-dir>/<slug>.listen.seen.gpt.json` (default state-dir
`.agents/gitchat/state/`), a JSON object `{"seen": [<id>, ...]}`. It
is deliberately separate from the `gitchat_poll`
`<slug>.seen.gpt.json` prompt seen-file so the two listeners never
clobber one another.

Common flags: --repo (default .), --remote (default origin),
--message-dir (default .agents/gitchat/messages/),
--state-dir (default .agents/gitchat/state/),
--poll-interval (default 5.0, stream loop only),
--no-fetch (skip the network fetch; use already-fetched refs).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

# Terminal kinds msd_listen collects. `prompt`/`progress` are NOT
# terminal (gitchat_poll handles prompts; progress is streaming), and
# `ack` is a transport acknowledgement, not a builder report — so the
# leader's report inbox is exactly `response` plus `error`.
TERMINAL = {"response", "error"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def git(repo, *args):
    """Run a git command; return stdout (str), or '' on failure."""
    out = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    )
    if out.returncode != 0:
        return ""
    return out.stdout


def fetch(repo, remote):
    subprocess.run(
        [
            "git",
            "-C",
            repo,
            "fetch",
            "-q",
            remote,
            f"+refs/heads/gitchat/*-outbox:refs/remotes/{remote}/gitchat/*-outbox",
        ],
        capture_output=True,
        text=True,
    )


def outbox_refs(repo, remote):
    out = subprocess.run(
        [
            "git", "-C", repo, "for-each-ref",
            "--format=%(refname)",
            f"refs/remotes/{remote}/gitchat/",
        ],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        print(
            f"warning: git for-each-ref failed: {out.stderr.strip()}",
            file=sys.stderr,
        )
        return []
    return [r for r in out.stdout.split("\n") if r.endswith("-outbox")]


def all_envelopes(repo, remote, msg_dir):
    """Every envelope across every outbox branch, deduped by id."""
    found = {}
    for ref in outbox_refs(repo, remote):
        listing = git(repo, "ls-tree", "-r", "--name-only", ref, "--", msg_dir)
        for path in listing.split("\n"):
            if not path.endswith(".gpt.json"):
                continue
            show = subprocess.run(
                ["git", "-C", repo, "show", f"{ref}:{path}"],
                capture_output=True,
                text=True,
            )
            if show.returncode != 0:
                print(
                    f"warning: git show {ref}:{path} failed: "
                    f"{show.stderr.strip()}",
                    file=sys.stderr,
                )
                continue
            try:
                env = json.loads(show.stdout)
            except ValueError:
                continue
            eid = env.get("id")
            if eid and eid not in found:
                found[eid] = env
    return list(found.values())


def state_path(args):
    return os.path.join(
        args.repo, args.state_dir.rstrip("/"), f"{args.slug}.listen.seen.gpt.json"
    )


def load_seen(args):
    try:
        with open(state_path(args)) as fh:
            data = json.load(fh)
        return set(data.get("seen", []))
    except (OSError, ValueError):
        return set()


def save_seen(args, seen):
    path = state_path(args)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        json.dump({"seen": sorted(seen)}, fh, indent=2)
    os.replace(tmp, path)


def sort_key(env):
    return (env.get("created_at") or "", env.get("id") or "")


def terminal_messages(args):
    """Terminal response/error envelopes addressed to the leader slug.

    Sorted oldest-first by (created_at, id). Does not consult
    seen-state — callers filter that themselves so `--all` can show
    everything.
    """
    envs = all_envelopes(args.repo, args.remote, args.message_dir)
    out = []
    for env in envs:
        if env.get("kind") not in TERMINAL:
            continue
        if env.get("to") != args.slug:
            continue
        out.append(env)
    out.sort(key=sort_key)
    return out


def collect_once(args, seen):
    """Print new terminal messages once; return the updated seen set.

    When `--all` is set, every matching terminal is printed regardless
    of seen-state. Otherwise only ids absent from `seen` print. Unless
    `--no-mark` is set, every printed id is added to `seen` and the
    seen-file is rewritten so the next run does not repeat it.
    """
    messages = terminal_messages(args)
    printed = []
    for env in messages:
        eid = env.get("id")
        if not args.all and eid in seen:
            continue
        print(json.dumps(env), flush=True)
        printed.append(eid)
    if printed and not args.no_mark:
        seen.update(printed)
        save_seen(args, seen)
    return seen


def main(argv):
    p = argparse.ArgumentParser(prog="msd_listen.py")
    p.add_argument("--slug", required=True, help="the leader slug")
    p.add_argument("--repo", default=".")
    p.add_argument("--remote", default="origin")
    p.add_argument("--message-dir", default=".agents/gitchat/messages/")
    p.add_argument("--state-dir", default=".agents/gitchat/state/")
    p.add_argument(
        "--once",
        action="store_true",
        help="print new terminals once, then exit (no stream loop)",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="print every matching terminal ignoring seen-state, then exit (not a stream loop)",
    )
    p.add_argument(
        "--no-mark",
        action="store_true",
        help="print without recording printed ids as seen",
    )
    p.add_argument("--mark-seen", help="record one terminal id as collected")
    p.add_argument(
        "--no-fetch",
        action="store_true",
        help="skip the network fetch (use already-fetched refs)",
    )
    p.add_argument("--poll-interval", type=float, default=5.0)
    args = p.parse_args(argv)

    if not SLUG_RE.match(args.slug):
        print("invalid slug", file=sys.stderr)
        return 2

    if args.mark_seen:
        seen = load_seen(args)
        seen.add(args.mark_seen)
        save_seen(args, seen)
        print(json.dumps({"marked_seen": args.mark_seen}))
        return 0

    seen = load_seen(args)
    if args.once or args.all:
        if not args.no_fetch:
            fetch(args.repo, args.remote)
        collect_once(args, seen)
        return 0

    # Stream loop: fetch, surface any new terminals, sleep, repeat,
    # until the human interrupts.
    while True:
        if not args.no_fetch:
            fetch(args.repo, args.remote)
        seen = collect_once(args, seen)
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
