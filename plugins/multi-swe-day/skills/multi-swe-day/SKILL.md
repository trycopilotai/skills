---
name: multi-swe-day
description: >-
  Run a multi-agent swe-day delegation network: one leader
  holds the single-writer lock and gates every land, N
  builders each take one leader-confirmed day and fan out
  local sub-agents to build it, and an auditor runs l8 over
  the skill/protocol files and proposes improvements.
  Composes gitchat (transport), swe_day_lock (single-writer
  lock), and swe-day (milestone discipline) into a reusable
  way to delegate swe work across chats or
  machines. Verify-before-implement, disjoint lanes, and
  operator-gated non-push reconciliation are the rules the
  text asks each role to keep.
---

# multi-swe-day

Promote the ad-hoc swe-day leader/builder/auditor network to
a first-class delegation protocol. One **leader** chat holds
the single-writer lock and gates every land; N **builder**
chats each take one leader-confirmed day and **fan out local
sub-agents** to build it (hybrid parallelism — one day per
builder, multiple sub-tasks inside each); one **auditor**
chat runs the **l8** persona over the skill and protocol
files and proposes — never implements — improvements.

This file is the canonical, host-neutral surface. Host
bindings — which slugs map to which role, the lock's exact
`--repo`/`--lock-path`, the registry path, where the gitchat
runtime lives, which l8 wrapper to read — belong in the
consuming repo's thin wrapper, not here.

This skill is composition, not new transport. It wires three
existing primitives together; read each before using this
skill:

- **gitchat** (`github.com/trycopilotai/gitchat`) — message
  transport (send / server / inbox / tail) over git
  branches. Its scripts, such as `gitchat_send.py` and
  `gitchat_poll.py`, are in `<gitchat-skill-dir>/scripts/`.
  Needed for a run across chats, not in a single session
  (below).
- **swe_day_lock.py** (`github.com/trycopilotai/swe-day`) — the
  single-writer mutation lock for the operational repo, at
  `<swe-day-skill-dir>/scripts/swe_day_lock.py`.
- **swe-day** (`github.com/trycopilotai/swe-day`) — the DXX
  milestone discipline and plan / validate / land gates.

**Finding the scripts.** Commands here and in
`references/PROTOCOL.md` name scripts through three
placeholders. Each stands for the directory that holds that
skill's `SKILL.md`:

- `<multi-swe-day-skill-dir>` — this skill; its own scripts
  are `<multi-swe-day-skill-dir>/scripts/msd_*.py`.
- `<gitchat-skill-dir>` — the installed gitchat skill.
- `<swe-day-skill-dir>` — the installed swe-day skill.

Resolve each to an absolute path before running a command;
commands run from the operational repo, not from a skill
directory, so a bare `scripts/...` path does not resolve.

- **Claude Code:** loading a skill with the Skill tool prints
  its base directory ("Base directory for this skill: ...").
  Otherwise look for `<name>/SKILL.md` in
  `~/.claude/skills/`, in the project's `.claude/skills/`,
  or in the `skills/` directory of an installed plugin.
- **Codex:** the session's skill list gives the path of each
  skill's `SKILL.md`; its directory is the skill directory.
  Otherwise look in `~/.agents/skills/<name>/` or the
  repo's `.agents/skills/<name>/`.

`<name>` is `multi-swe-day`, `gitchat` or `swe-day`. If
swe-day, or gitchat for a run across chats, is in none of
those places, stop and ask the operator where it is
installed; do not search the filesystem outside the
operational repo for it.

**Single session.** With no separate builder chats (one
session doing the leader's work, perhaps with in-process
sub-agents as builders), gitchat is not used (no
`gitchat_send`, server, `msd_listen` or `gitchat_poll`), but
the swe-day lock and the registry are. Every registry
command below takes `--registry <path> --lock-path <lock>`
before the subcommand and `--lock-owner <owner> --session-id
<id>` after it, as in "Lane registry" below. In order:

1. The operator approves the plan. No command records that;
   the approval is the instruction to go on.
2. Acquire the lock with the full `swe_day_lock.py acquire`
   form in `references/PROTOCOL.md` section 1, then
   `init --leader <slug>`.
3. `register` each builder's lanes.
4. Each builder sub-agent checks its lanes and writes its
   finding to a file; `confirm --slug <slug> --propose
   <propose-ref>` with that file's path.
5. `run-advance --phase build --owner agent`; then
   `update --status in-progress` and, when its work is
   done, `update --status reported` for each builder.
6. `run-advance --phase human-review --owner human --gate
   human-review`, and stop. The operator clears it:
   `run-clear-gate human-review`, with the leader's
   `--lock-owner` and `--session-id`.
7. `run-advance --phase reconcile --owner agent`; merge
   locally, re-validate, then `update --status landed` for
   each builder.
8. `run-advance --phase land-approval --owner human --gate
   land-approval`, and stop. The push waits for a separate
   operator instruction.

`run-clear-gate` accepts only the gate the last
`run-advance --gate` recorded, so there is no
`run-clear-gate plan`: before any `run-advance` there is no
`run` object and it exits 1; on any other gate it exits 5.
These are the only `run-advance` calls.

The numbered, decision-complete procedure lives in
`references/PROTOCOL.md`; read it before acting. This file defines the
roles, the invocation API, and the four bundled scripts.

## Roles + API

- **`multi-swe-day(leader)`** — exactly one. Holds the lock
  and is the sole writer of the operational repo's tracked
  state. Owns the lane registry, runs the deduped
  terminal-response collector plus a new-prompt poller,
  enforces dispatch disjointness and the
  verify-before-implement gate, applies builder payloads
  under the lock, and runs the operator-gated **non-push**
  reconciliation that lands the day.
- **`multi-swe-day(builder-NN)`** — N builders. Each takes
  one leader-confirmed day and **fans out sub-agents**
  across that day's sub-tasks, adversarially verifies,
  integrates, validates, and reports. `role=builder-NN` is a
  role label that is **separate from the gitchat slug** — a
  live network keeps its existing slugs (for example
  `swe-day-follower-0N`) so old prompts are not reprocessed
  and seen-state / outbox branches are not orphaned. A
  builder never writes the operational repo and never pushes
  app main.
- **`multi-swe-day(auditor)`** — one quality/meta role. Runs
  **l8** over the named skill and protocol files,
  **proposes** P0–P3 improvements with file:line and the
  mandatory L9/L10 addendum, and never implements. Because
  its report is unsolicited, it sends it to the leader as a
  `kind:prompt` envelope (a `response` requires a prompt to
  reply to).

Reject mixed forms and an unknown role/slug yourself (no
program checks them), and do not send a dispatch
whose lanes intersect an already-registered lane (including
a `proposed` one).

## Lane registry — the disjointness invariant

The leader maintains a registry file (the consuming repo
binds the path) mapping each builder slug to its assigned
lanes (repo-relative paths), role, day, plan path,
model/effort hint, and status. A dispatch is **refused** if
its lanes intersect another builder's lanes — by an exact
match **or** an ancestor/descendant path relationship — and
the check runs against `proposed` lanes too, not only
`assigned` ones. A builder whose status is `aborted` does
not block, and a slug that registers again replaces its
own row. This is what is meant to keep N builders file-disjoint
and the eventual reconciliation conflict-free. The registry
should be mutated only by the leader and only under the held
lock.

`scripts/msd_lane_registry.py` is the bundled
helper (the analog of `swe_day_lock.py`). `--registry` and
`--lock-path` are options of the program, not of a
subcommand: they go **before** the subcommand, and
`--lock-owner` / `--session-id` go after it. A
`--lock-path` placed after the subcommand is rejected
(exit 2, "unrecognized arguments").

```
# initialize an empty registry (idempotent: an existing registry
# is printed unchanged; creating a new one is lock-checked)
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> --lock-path <lock> \
  init --leader <slug> --lock-owner <owner> --session-id <id>

# propose a disjoint lane set for one builder (status: proposed).
# repeatable --lane; rejects absolute paths and any ".." component;
# exits non-zero and names the conflict on overlap, incl. proposed.
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> --lock-path <lock> \
  register --slug <slug> --role builder-NN --day DXX \
  --plan-path <path> --model <model> --effort <effort> \
  --lane <repo-relative-posix-path> [--lane ...] \
  --lock-owner <owner> --session-id <id>

# confirm a proposed lane set (proposed -> assigned) once the
# builder's PROPOSE has arrived; --propose records the PROPOSE
# reference and is required: without it confirm is refused (exit 5)
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> --lock-path <lock> \
  confirm --slug <slug> --propose <propose-ref> \
  --lock-owner <owner> --session-id <id>

# advance / record state; release a builder's lanes
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> --lock-path <lock> \
  update --slug <slug> --status <status> [--commit <sha>] \
  --lock-owner <owner> --session-id <id>
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> --lock-path <lock> \
  release --slug <slug> --lock-owner <owner> --session-id <id>

# record the run phase / park at a human gate (leader), and
# clear a recorded human gate (operator)
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> --lock-path <lock> \
  run-advance --phase <phase> --owner agent|human \
  [--gate <gate>] [--note <text>] \
  --lock-owner <owner> --session-id <id>
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> --lock-path <lock> \
  run-clear-gate <gate> --lock-owner <owner> --session-id <id>

# read the registry (no lock needed)
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> status [--slug <slug>]
```

- **Subcommands:** `init` (also accepted as `adopt`, an
  alias of `init` with the same options and behaviour),
  `register`, `confirm`, `update`, `release`, `status`,
  `run-advance`, `run-clear-gate`.
- **Schema:**
  `{schema_version, updated_at, leader, run:{phase, next_owner, blocking_gate, note, cleared_gates[], updated_at}, followers:{<slug>:{role, lanes[], day, plan_path, model, effort, status, commit, propose, updated_at}}}`;
  `run` is optional.
- **Status transitions:**
  `proposed → assigned → in-progress → reported → landed | aborted`.
- **Gates the registry enforces** (each refusal exits 5, like
  an illegal transition, and changes nothing):
  - `confirm` without `--propose` is refused. The value,
    `<propose-ref>`, is the PROPOSE reference: the gitchat
    envelope id of the builder's PROPOSE response (the
    verify-before-implement step), or in a single session
    the path of the file holding the finding. It is stored
    as `propose` with surrounding whitespace trimmed; any
    value that is not empty or only whitespace is accepted.
  - `update --status landed` is refused while
    `run.blocking_gate` is set, and until the operator's
    `run-clear-gate human-review` has put `human-review` in
    `run.cleared_gates`. A registry with no `run` object has
    not cleared it. A later `run-advance` keeps
    `cleared_gates`; one that records `--gate human-review`
    again takes it out.
  The program cannot tell who runs a command: it checks that
  the steps were recorded, not that the operator took them.
- Writes go through a temp file + rename, so one writer's
  write is not torn; two concurrent writers share the temp
  file name and are not protected. Rename does not stop the **wrong**
  writer, so every mutating command (`init` on a new
  registry, `register`, `confirm`, `update`, `release`,
  `run-advance`, `run-clear-gate`) also **verifies the held lock's
  owner/session** — it takes `--lock-owner` and
  `--session-id` and refuses the write when they do not
  match the lock metadata (the session id is compared only
  when the metadata records a non-empty one). The check runs only when
  `--lock-path` names the lock directory; without it the
  write is not lock-guarded. Read-only `status` needs no
  lock.

## Terminal-response listener

`scripts/msd_listen.py` is the leader's deduped
inbox for **terminal** envelopes. It reads `response` and
`error` envelopes addressed to the leader across all
`gitchat/*-outbox` branches and surfaces each one once,
deduped by id against the leader's own seen-state (the
repository's `SECURITY.md` lists known cases where that does
not hold). This
formalizes the hand-rolled bash listener the ad-hoc network
used.

This is a distinct listener from `gitchat_poll` **on
purpose**: `gitchat_poll.py` returns only executable
`prompt` envelopes (it ignores `response`/`error`), so it
**cannot** be the report/proposal listener. The leader runs
both: `msd_listen` for builder reports and errors (it does
not collect `ack` envelopes), and a `gitchat_poll` loop for **new
prompts** (auditor proposals, operator messages). Mark a
prompt seen with
`python3 <gitchat-skill-dir>/scripts/gitchat_poll.py --slug <leader> --mark-seen <id>` only after
the leader has pushed its own terminal response to it.

```
# surface unseen terminal responses/errors addressed to the leader
# (a stream loop; add --once to print what is new and exit)
python3 <multi-swe-day-skill-dir>/scripts/msd_listen.py \
  --slug <leader> [--repo .] [--remote origin]

# record an envelope id as seen without printing it (a printed
# envelope is already recorded unless --no-mark is passed)
python3 <multi-swe-day-skill-dir>/scripts/msd_listen.py \
  --slug <leader> --mark-seen <envelope-id>
```

Dispatch and reconciliation are **prose, not new scripts**:
they compose the existing gitchat scripts and the lock, as a
documented runnable command sequence in `references/PROTOCOL.md`.

## Active Run mode

While a run is live (the lock is held / the registry is
present), the leader BEGINS EVERY TURN by running the
next-action driver and emitting its banner as the **first
lines** of the reply:

```
▶ multi-swe-day ACTIVE · phase <P> · NEXT: <item> · OWNER: human|agent · BLOCKED-ON: <whom>
  next: <the concrete next item>
```

`scripts/msd_next.py render` computes this from
the lock, the registry (lane `status`es + the `run` object),
and an embedded phase model — it improvises nothing. When
`run.phase` is unset the phase is DERIVED (all lanes
`reported` ⇒ `human-review`, etc.); an explicit `run.phase`
overrides the derivation, and a set `run.blocking_gate`
forces OWNER `human` whatever the phase is. A mix
of `reported` and `landed` lanes derives `reconcile`, an
agent phase, so record the review gate with `run-advance`
as the protocol says rather than relying on the derivation.
When OWNER is `human` the banner adds a line naming the
unmet gate, and a `note:` line when a note is recorded.

The registry refuses to mark a lane `landed` until the
`human-review` gate has been recorded and cleared (see
"Gates the registry enforces" above).

**Never act downstream of an unmet HUMAN gate.** When OWNER
renders `human` (`plan`, `human-review`, `land-approval`,
`push`, or
any set `blocking_gate`), the leader names the exact human
action and stops — it does NOT offer any agent action behind
the gate (for example, never suggest `reconcile` while
`human-review` is unmet). A human gate the leader recorded
with `run-advance --gate` clears only via the
operator's `run-clear-gate <name>` (full form under "Lane
registry" above);
the leader then `run-advance`s to the next phase. The
ordered phase model and exactly where the leader advances it
live in `references/PROTOCOL.md` → "Run phase model" / "Active Run
mode".

**Showing a diff for the human gate — use the review-surface
helper.** When the operator asks to see or review a held
diff (a worktree commit, a lane's changes) at the
`human-review` gate, build the review surface with
`scripts/msd_review_open.py`, not a hand-rolled
`git diff` + `open`:

```sh
python3 <multi-swe-day-skill-dir>/scripts/msd_review_open.py \
  --repo <worktree-or-repo> \
  --range <base>..<head> [--skip-glob 'drizzle/meta/*' ...]
```

The helper writes ONE `.diff` per path that
`git diff --name-only` lists (paths matched by
`--skip-glob` excepted) into a fresh
temp review dir (one tab per file — it expands the `.diff`
glob into separate `open` arguments, never a newline-joined
variable, fixing the historical path-join bug), generates a
`CHECKLIST.md` (one review item per written `.diff`, a list
of skipped paths, plus a verdict section), and opens VS Code with the **checklist on
the LEFT half and the per-file diffs on the RIGHT half** via
`osascript` window bounds, best effort: it moves the first
two VS Code windows it finds (graceful fallback to just opening
both if accessibility automation is blocked). It always
launches with `open -a "Visual Studio Code"`, never the
`code` CLI shim. Pass `--skip-glob` for huge generated files
(`drizzle/meta` snapshots) and `--no-open` to build without
launching. The repository's `SECURITY.md` lists known cases
where a listed file gets an empty, partial or wrong diff,
or shares one `.diff` with another file.

**Cmd+Opt+A scoping.** The temp review dir is not a
workspace the companion extension activates in on its own, so the helper opens the diffs
as a FOLDER and drops a sentinel pair (`publish.manifest` +
`PROVENANCE.schema.json`) plus a `.vscode/settings.json`
(`files.exclude` hides the sentinels and `.vscode`) into it.
That is what makes the
companion VS Code review extension (not included)
activate and fire Cmd+Opt+A on the diff
tabs, which feeds the address-comments `.diff` mode. VS Code
renders `.diff` with syntax highlighting; that surface is
the operator's review — never just print the diff inline.

## Invariants (what the text asks each role to keep)

1. **Single operational-repo writer = the leader.** Builders
   never write the operational repo's tracked files; they
   send the content to the leader, which writes it under the
   lock.
2. **Leader- and operator-gated lands.** No builder pushes
   app main. Builders report worktree commits; the leader
   reconciles and lands only on an explicit operator gate.
3. **Disjoint lanes.** No two builders hold the same lanes,
   enforced by the registry with path normalization and
   ancestor/descendant detection, against `proposed` lanes
   too (an `aborted` builder's lanes excepted).
4. **Deduped terminal-response listener** = `msd_listen`,
   not `gitchat_poll` — each builder report and error is
   surfaced once, deduped by id.
5. **Verify-before-implement.** A builder checks its lanes
   against `origin/main` and its siblings and replies with a
   PROPOSE (a terminal `response`) before building; the
   leader confirms, re-routes, or aborts. Because the
   PROPOSE closes that conversation and `confirm` is only a
   local registry mutation the builder cannot see, the
   leader sends a **second build-go prompt** (a new
   conversation) after `confirm`; the builder builds on that
   build-go prompt and reports a terminal `response` to it.
   Two leader→builder prompts per lane: dispatch (verify)
   then build-go. `confirm` requires `--propose <propose-ref>`, the
   PROPOSE it rests on.
6. **Builders fan out locally** (task-internal sub-agents,
   never a gitchat relay, never recursive, bounded to N
   workers (default N=4)), each sub-agent in its own throwaway
   worktree or producing a patch, with the builder as sole
   integrator, and adversarially verify before reporting.
7. **Non-push reconcile → operator-gated deploy.** The
   leader merges all worktree commits into one main
   **locally**, re-validates, marks `landed` (the registry
   refuses this until the operator has cleared
   `human-review`); a **second** operator gate authorizes the
   deploy push.
8. **Auditor proposes only** — never implements.
9. **Registry writes only under the held lock**, verified by
   owner/session when `--lock-path` is passed, not just
   atomic rename.

## Bundled scripts

- `scripts/msd_lane_registry.py` — the
  disjointness invariant (above). Pure stdlib, executable,
  with `test_msd_lane_registry.py` beside it.
- `scripts/msd_listen.py` — the deduped
  terminal-response collector (above). Pure stdlib,
  executable, with `msd_listen_test.py` beside it.
- `scripts/msd_next.py` — the Active-Run
  next-action driver (above). Pure stdlib, executable, with
  `test_msd_next.py` beside it.
- `scripts/msd_review_open.py` — the human-review-gate
  review-surface builder (above): per-file `.diff` tabs + a
  generated `CHECKLIST.md`, opened in VS Code checklist-left
  / diffs-right, with the Cmd+Opt+A sentinel scoping. Pure
  stdlib, executable, with a self-test (`--self-test`).

These mirror the conventions of the gitchat transport
scripts and `swe_day_lock.py`: stdlib only, temp-file-and-rename
writes for the registry and the seen-state, a
clear JSON contract, and a runnable test. Prefer them over
hand-rolled git or JSON plumbing.

## Promotion / consuming this skill

A consuming repo wires this in with a **thin wrapper** that
reads this file first and binds the host specifics:

- the registry path (for example
  `handoff/multi-swe-day.json`),
- the role↔slug map (for example `builder-01` ↔
  `swe-day-follower-01`),
- the lock's exact `--repo` and `--lock-path` (bind them
  explicitly — the `swe_day_lock.py` default
  `.agents/locks/swe-day.lock` may differ from a host
  wrapper's path; confirm via
  `python3 <swe-day-skill-dir>/scripts/swe_day_lock.py
  --repo <repo> --lock-path <lock> status`),
- the gitchat scripts and remote,
- which l8 wrapper the auditor reads.

Do not copy this protocol text into a wrapper; update the
installed copy to receive upstream changes. The wrapper is the
canonical entry point for invoking the skill in that repo;
this file stays slug- and host-neutral.
