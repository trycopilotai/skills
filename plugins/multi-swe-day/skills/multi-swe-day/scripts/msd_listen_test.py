#!/usr/bin/env python3
"""Test for msd_listen.py — no network, local fixture git repo.

Builds a throwaway git repo, commits gitchat envelope fixtures onto
`gitchat/<slug>-outbox` branches, then publishes those branches under
`refs/remotes/origin/gitchat/*-outbox` so the collector reads them
exactly as it would after a real fetch — but with `--no-fetch`, so the
test never touches a network. Drives msd_listen.py as a subprocess
(end-to-end) and asserts on its JSON-line output and seen-file.

Covers:
  - terminal response/error addressed to the leader are surfaced
  - prompt / progress / ack and terminals addressed elsewhere are NOT
  - dedup: a second run does not re-surface an already-seen terminal
  - a new terminal arriving after the first run is surfaced once
  - --all ignores seen-state; --mark-seen records an id
  - oldest-first ordering by (created_at, id)
  - the leader seen-file is independent of the gitchat_poll seen-file

Run: python3 msd_listen_test.py   (exit 0 = pass)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "msd_listen.py")
MSG_DIR = ".agents/gitchat/messages/"
LEADER = "swe-day-leader"


def git(repo, *args, check=True):
    out = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    )
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr}")
    return out


def envelope(eid, frm, to, kind, created_at, **extra):
    """A minimal but schema-shaped gitchat envelope fixture."""
    env = {
        "id": eid,
        "conversation_id": extra.get("conversation_id", eid),
        "from": frm,
        "to": to,
        "kind": kind,
        "created_at": created_at,
        "reply_to": extra.get("reply_to"),
        "hops_remaining": 0,
        "max_responses": 0,
        "allow_orchestration": False,
        "msg": extra.get("msg", f"{kind} from {frm}"),
    }
    if "seq" in extra:
        env["seq"] = extra["seq"]
    return env


def commit_envelopes(repo, slug, envelopes):
    """Commit envelope fixtures onto gitchat/<slug>-outbox, then mirror
    that branch to refs/remotes/origin/<branch> so the collector finds
    it with --no-fetch (no real remote involved)."""
    branch = f"gitchat/{slug}-outbox"
    git(repo, "checkout", "-q", "--orphan", branch)
    git(repo, "rm", "-rf", "-q", "--cached", ".", check=False)
    msg_dir = os.path.join(repo, MSG_DIR)
    os.makedirs(msg_dir, exist_ok=True)
    # clear any stray files from a previous orphan checkout
    for name in os.listdir(msg_dir):
        os.remove(os.path.join(msg_dir, name))
    for env in envelopes:
        path = os.path.join(msg_dir, f"{env['id']}.gpt.json")
        with open(path, "w") as fh:
            json.dump(env, fh, indent=2)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"fixtures for {slug}")
    # Mirror local branch -> remote-tracking ref the collector reads.
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-ref", f"refs/remotes/origin/{branch}", sha)


def run(repo, *extra):
    out = subprocess.run(
        [sys.executable, SCRIPT, "--slug", LEADER, "--repo", repo, "--no-fetch", *extra],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise AssertionError(
            f"msd_listen exited {out.returncode} for args {list(extra)}\n"
            f"stderr: {out.stderr.strip()}\n"
            f"stdout: {out.stdout.strip()}"
        )
    ids = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        ids.append(json.loads(line))
    return ids


def setup_repo():
    repo = tempfile.mkdtemp(prefix="msd-listen-test-")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    # one empty base commit so orphan checkouts are clean
    open(os.path.join(repo, ".keep"), "w").close()
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")

    # Builder 01 outbox: a terminal response TO the leader (surface),
    # a progress (skip), and an ack (skip).
    commit_envelopes(
        repo,
        "swe-day-follower-01",
        [
            envelope(
                "g-001", "swe-day-follower-01", LEADER, "response",
                "20260623T100000Z", msg="lane A reported", reply_to="p-001",
            ),
            envelope(
                "g-002", "swe-day-follower-01", LEADER, "progress",
                "20260623T100100Z", seq=1, reply_to="p-001",
            ),
            envelope(
                "g-003", "swe-day-follower-01", LEADER, "ack",
                "20260623T100200Z",
            ),
        ],
    )
    # Builder 02 outbox: a terminal ERROR to the leader (surface), and
    # a response addressed to ANOTHER slug (skip).
    commit_envelopes(
        repo,
        "swe-day-follower-02",
        [
            envelope(
                "g-010", "swe-day-follower-02", LEADER, "error",
                "20260623T095900Z", msg="lane B failed verify gate",
            ),
            envelope(
                "g-011", "swe-day-follower-02", "swe-day-follower-03",
                "response", "20260623T100300Z", msg="not for the leader",
            ),
        ],
    )
    # Leader's own outbox: a prompt the leader SENT (skip — prompts are
    # gitchat_poll's job, never collected here).
    commit_envelopes(
        repo,
        LEADER,
        [
            envelope(
                "g-020", LEADER, "swe-day-follower-01", "prompt",
                "20260623T094500Z", msg="dispatch lane A",
            ),
        ],
    )
    return repo


def add_late_response(repo):
    """Append a second response on builder 01's outbox after run 1."""
    branch = "gitchat/swe-day-follower-01-outbox"
    git(repo, "checkout", "-q", branch)
    env = envelope(
        "g-099", "swe-day-follower-01", LEADER, "response",
        "20260623T110000Z", msg="lane A follow-up",
    )
    path = os.path.join(repo, MSG_DIR, "g-099.gpt.json")
    with open(path, "w") as fh:
        json.dump(env, fh, indent=2)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "late response")
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-ref", f"refs/remotes/origin/{branch}", sha)


def seen_file(repo):
    return os.path.join(
        repo, ".agents/gitchat/state", f"{LEADER}.listen.seen.gpt.json"
    )


def main():
    repo = setup_repo()

    # Run 1 (--once): exactly the two terminals to the leader, oldest
    # first by created_at. g-010 (09:59) precedes g-001 (10:00).
    got = run(repo, "--once")
    ids = [e["id"] for e in got]
    assert ids == ["g-010", "g-001"], f"run1 ids wrong: {ids}"
    kinds = {e["id"]: e["kind"] for e in got}
    assert kinds == {"g-010": "error", "g-001": "response"}, kinds
    print("PASS surfaces terminal response/error to the leader, oldest-first")
    print("PASS skips prompt/progress/ack and terminals to other slugs")

    # Seen-file now records both ids.
    with open(seen_file(repo)) as fh:
        seen = set(json.load(fh)["seen"])
    assert seen == {"g-010", "g-001"}, seen
    print("PASS records surfaced ids in the leader listen seen-file")

    # Run 2 (--once): nothing new — dedup holds.
    got2 = run(repo, "--once")
    assert got2 == [], f"run2 should be empty, got {[e['id'] for e in got2]}"
    print("PASS dedupes already-seen terminals on a second run")

    # A late response arrives; run 3 surfaces only it.
    add_late_response(repo)
    got3 = run(repo, "--once")
    ids3 = [e["id"] for e in got3]
    assert ids3 == ["g-099"], f"run3 ids wrong: {ids3}"
    print("PASS surfaces a newly-arrived terminal exactly once")

    # --all ignores seen-state: all three leader terminals reappear.
    got_all = run(repo, "--all", "--no-mark")
    ids_all = [e["id"] for e in got_all]
    assert ids_all == ["g-010", "g-001", "g-099"], ids_all
    print("PASS --all ignores seen-state and lists every leader terminal")

    # --mark-seen records an id directly; a fresh listen then skips it.
    repo2 = setup_repo()
    out = subprocess.run(
        [sys.executable, SCRIPT, "--slug", LEADER, "--repo", repo2,
         "--mark-seen", "g-001"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip())["marked_seen"] == "g-001"
    got4 = run(repo2, "--once")
    ids4 = [e["id"] for e in got4]
    assert ids4 == ["g-010"], f"after mark-seen got {ids4}"
    print("PASS --mark-seen records an id so a later listen skips it")

    # The listen seen-file name is distinct from gitchat_poll's, so the
    # two listeners never share state.
    assert seen_file(repo).endswith(f"{LEADER}.listen.seen.gpt.json")
    poll_name = f"{LEADER}.seen.gpt.json"
    assert os.path.basename(seen_file(repo)) != poll_name
    print("PASS leader listen seen-file is independent of the poll seen-file")

    # The stream loop flushes each envelope: a reader on a pipe gets the
    # line while the listener is still running.
    import select

    repo3 = setup_repo()
    stream = subprocess.Popen(
        [sys.executable, SCRIPT, "--slug", LEADER, "--repo", repo3,
         "--no-fetch", "--poll-interval", "0.2"],
        stdout=subprocess.PIPE,
    )
    try:
        ready, _, _ = select.select([stream.stdout], [], [], 30)
        assert ready, "no envelope reached the pipe within 30 seconds"
        first = json.loads(stream.stdout.readline())
        assert first["id"] == "g-010", first
        assert stream.poll() is None, "the stream loop exited"
    finally:
        stream.terminate()
        stream.wait()
        stream.stdout.close()
    print("PASS stream loop delivers an envelope to a pipe while running")

    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
