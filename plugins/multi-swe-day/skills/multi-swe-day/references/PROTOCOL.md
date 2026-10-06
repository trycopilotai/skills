# multi-swe-day — protocol

The canonical, numbered procedure for one
`multi-swe-day(...)` run. The host-neutral surface and role
contract live in `SKILL.md`; this file is the
operational sequence each role executes. Repo bindings (the
exact lock `--repo`/`--lock-path`, the registry path, the
role↔slug map, the l8 wrapper location) belong in the
consuming repo's thin wrapper, not here.

Three stdlib scripts back the registry, the leader inbox,
and the run's next-action banner (a fourth,
`msd_review_open.py`, builds the review surface and is
described under Active Run mode):

- `scripts/msd_lane_registry.py` — the
  disjointness invariant (analog of `swe_day_lock.py`), plus
  the run-level `run-advance` / `run-clear-gate` mutations.
- `scripts/msd_listen.py` — the leader's deduped
  terminal-response collector.
- `scripts/msd_next.py` — the Active-Run
  next-action driver: it reads the lock, the registry (lane
  statuses + the `run` object), and the embedded phase
  model, then renders the banner.

Everything else (dispatch, reconcile, fan-out) is prose that
composes existing gitchat and lock helpers. The command
sequences below are written out so a verifier can follow
them; `<...>` stands for a host binding.

Scripts are named through the placeholders `SKILL.md`
defines under "Finding the scripts":
`<multi-swe-day-skill-dir>`, `<gitchat-skill-dir>` and
`<swe-day-skill-dir>`, each the absolute path of the
directory holding that skill's `SKILL.md`. Resolve them as
`SKILL.md` says before running anything.

A short form in prose, such as
`msd_lane_registry confirm --slug <builder-slug>`, means the
full command:

```sh
python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
  --registry <path> --lock-path <the held lock path> \
  <subcommand> <its options> \
  --lock-owner swe-day-leader --session-id <sid>
```

`--registry` and `--lock-path` belong to the program and go
**before** the subcommand; after it they are rejected with
exit 2. `--lock-owner` and `--session-id` belong to every
mutating subcommand and go after it. Read-only `status`
takes neither. `adopt` is an alias of `init`.
Likewise `swe_day_lock.py ... status` means
`python3 <swe-day-skill-dir>/scripts/swe_day_lock.py --repo <ops-repo> --lock-path <the held lock path> status`.

## 0. Vocabulary

- **Role** is the protocol identity: `leader`, `builder-NN`,
  `auditor`. It is a prompt/registry label only.
- **Slug** is the live gitchat endpoint. The slug is
  **separate from the role** and is NOT changed when a
  builder adopts this protocol: the running slugs stay
  `swe-day-follower-0N`. Renaming a slug would reprocess old
  prompts and orphan the outbox and seen-state, so a builder
  is `role=builder-NN` with `slug=swe-day-follower-0N`.
- **Lane** is a repo-relative POSIX path a builder owns for
  one day. Lanes are the unit of disjointness.
- **Orchestration off** means the gitchat server processes
  the plain text of an inbound prompt and does not evaluate
  embedded protocol invocations (such as swe-day(DXX) or
  multi-swe-day(leader)). Describe every action in prose in
  message bodies addressed to a server; do not paste
  standalone protocol invocations.

## 1. Leader bring-up

Exactly one leader per run.

1. Acquire the single-writer lock with the **exact form** —
   bind `--repo` and `--lock-path` explicitly, never the
   bare defaults:

   ```sh
   python3 <swe-day-skill-dir>/scripts/swe_day_lock.py \
     --repo <ops-repo> \
     --lock-path <the exact path the running lock uses> \
     acquire --owner swe-day-leader --work-item <run-id> \
     --plan-path <path> --session-id <sid>
   ```

   The script default `--lock-path` is
   `.agents/locks/swe-day.lock`, which may differ from the
   path a consuming repo's wrapper binds. Use
   whichever path the live lock actually holds — confirm it
   with `swe_day_lock.py ... status` before acquiring, and
   adopt the existing lock rather than creating a second
   one.

2. Inspect the registry, then, if the registry file is
   absent, initialize it (recording the leader owner). Pass
   `--lock-path` before `init`, so creating the registry is
   checked against the lock you just acquired:

   ```sh
   python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
     --registry <path> status
   python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
     --registry <path> --lock-path <the held lock path> \
     init --leader swe-day-leader \
     --lock-owner swe-day-leader --session-id <sid>
   ```

   `init` on an existing registry prints it and changes
   nothing. Never reset existing builder rows on bring-up.

3. Arm the two listeners, which read different things and
   must both run:
   - `msd_listen` for terminal `response`/`error` envelopes
     addressed to the leader (builder reports, payloads,
     auditor errors), deduped by id.
   - a `gitchat_poll` loop for NEW `prompt` envelopes
     addressed to the leader (unsolicited auditor proposals,
     operator prompts). `gitchat_poll` is for prompts ONLY;
     it ignores `response`/`error`, so it can never be the
     report listener — that is `msd_listen`.

4. Announce online to each builder slug, then enter the
   coordinate loop.

## 2. Builder bring-up

One per builder.

1. Read, in order, this `PROTOCOL.md`, the gitchat skill,
   and the swe-day skill.
2. Announce online to the leader over gitchat, naming
   `role=builder-NN` and the unchanged `slug`.
3. Run `gitchat(server:<slug>)` (the existing bounded
   server: one prompt → one terminal response).
4. Act only on a leader dispatch. Do not start work before a
   dispatch arrives.

## 3. Dispatch (leader)

For each day handed out:

1. Confirm the lock is still held by this leader
   (`swe_day_lock.py ... status`).
2. Resolve the day's lanes from its plan to repo-relative
   POSIX paths.
3. Reserve the lanes:

   ```sh
   python3 <multi-swe-day-skill-dir>/scripts/msd_lane_registry.py \
     --registry <path> --lock-path <the held lock path> \
     register --slug <builder-slug> --role builder-NN \
     --day <DXX> --plan-path <path> --model <model> \
     --effort <effort> --lane <path> [--lane <path> ...] \
     --lock-owner swe-day-leader --session-id <sid>
   ```

   `register` **refuses overlap** — exact path, ancestor, or
   descendant — against any lane another builder already
   holds, `proposed` or `assigned` included, exits non-zero,
   and names the conflict. A builder whose status is
   `aborted` does not block, and registering a slug again
   replaces that slug's own row. On
   success it writes `status: proposed`. Absolute paths and
   `..` segments are rejected.

4. Dispatch the work over gitchat:

   ```sh
   python3 <gitchat-skill-dir>/scripts/gitchat_send.py \
     --from swe-day-leader --to <builder-slug> \
     --tier <cheap|max> --want-model <model> --effort <effort> \
     --msg "<deliverable + the reserved lanes + plan path + \
            the standing rules>"
   ```

   The `tier`/`want-model`/`effort` hints are
   **prompt-only** — they change how hard the responder
   works, never the transport, guards, or the
   single-terminal-response rule. The standing rules
   restated in every dispatch: route all ops-repo
   writes through the leader; do not push app main; work in
   a detached worktree off `origin/main`; verify before
   implementing; validate typecheck/lint/test/build.

## 4. Verify-before-implement gate (mandatory)

The builder does **not** build first.

1. On receiving a dispatch, the builder checks the day's
   lanes against `origin/main` and its sibling builders:
   - Is the deliverable already landed on `origin/main`?
   - Are the assigned lanes truly disjoint from what exists?
   - Is there an un-landed cross-lane dependency the day
     needs?
2. The builder replies with its finding as a **terminal
   `response`** to the dispatch — setting `--reply-to` to
   the dispatch id and `--conversation-id` to the dispatch
   conversation id. An unsolicited finding is not a valid
   response; this one is solicited by the dispatch, so it is
   a `response`.
3. The leader reads the finding through `msd_listen`, then
   either `confirm`s the lanes
   (`msd_lane_registry confirm --slug <builder-slug> --propose <propose-ref>`,
   `proposed → assigned`), re-routes (release + re-register
   a new lane set, which re-runs this gate), or aborts the
   day (a `release` at this stage: `update --status aborted`
   is accepted only from `reported`). `confirm` without
   `--propose` is refused (exit 5): the registry records which
   PROPOSE each confirmed lane set rests on, so a `register`
   followed straight by `confirm` does not pass.
4. `confirm` is a **local registry mutation on the leader**;
   the builder cannot see it. The builder's PROPOSE was a
   terminal `response`, which closed that conversation and
   left the builder's server idle, so the `confirm` cannot
   re-trigger it. After `confirm`, the leader therefore
   sends a **second gitchat prompt** — a **build-go
   dispatch** in a NEW conversation — to the builder slug:

   ```sh
   python3 <gitchat-skill-dir>/scripts/gitchat_send.py \
     --from swe-day-leader --to <builder-slug> \
     --tier <cheap|max> --want-model <model> --effort <effort> \
     --msg "build-go: lanes <reserved lanes> confirmed; build \
            the day per plan <path> and report your worktree \
            commit as a terminal response to THIS prompt"
   ```

   After sending build-go, the leader records a deadline: if
   no terminal response arrives within T (recommended
   default: 30 minutes), treat the builder as crashed and
   apply §9 builder-crash recovery — release its lanes and
   re-dispatch to a healthy builder. Include the expected
   response deadline in the build-go message body so the
   builder can surface it in its progress updates.

   This build-go prompt re-triggers the builder's server and
   is the signal the builder builds on. So per lane there
   are exactly **two leader→builder prompts**: the initial
   dispatch (verify) and the post-confirm build-go.

5. Only after the build-go prompt arrives does the builder
   build. No worktree commit may exist before the build-go
   prompt. The builder reports via a terminal `response` to
   the build-go prompt (§5).

## 5. Builder fan-out + build

Fan-out is **LOCAL / task-internal only**: the builder
spawns parallel sub-agents inside its own task. It is
**never a gitchat relay, never recursive, and bounded to N
workers**. gitchat server mode answers exactly one prompt
with one terminal response; the fan-out happens beneath that
single response, not over the wire.

The builder builds when the **build-go prompt** (§4) arrives
on its server — not on any invisible registry transition. In
its detached worktree off `origin/main`:

1. On the build-go prompt, set
   `msd_lane_registry update --slug <builder-slug> --status in-progress`-equivalent
   state via the leader (the builder routes the status
   request; the leader writes it under the lock).
2. Decompose the day into disjoint sub-tasks.
3. Spawn parallel sub-agents bounded to N workers. **Each
   sub-agent runs in its own throwaway worktree or produces
   a patch/artifact; the builder is the sole integrator.**
   Sub-agents never reach gitchat and never spawn their own
   sub-agents.
4. Adversarially verify each sub-agent's output.
5. Integrate into the builder's worktree and validate the
   whole: typecheck, lint, test, build.
6. Report to the leader as a **terminal `response` to the
   build-go prompt**: the worktree commit sha plus any
   ops-repo write payload (REVIEW.log entries,
   plan/progress text). The builder **never pushes** and
   **never writes ops-repo**.

## 6. Ops-repo writes (leader)

The leader is the **single ops-repo writer**.

1. On a builder report carrying an ops-repo payload,
   the leader writes those tracked files under the held
   lock.
2. The leader then advances the lane:
   `msd_lane_registry update --slug <builder-slug> --status reported`.

No other role writes ops-repo tracked state.

## 7. Reconcile — non-push (leader, operator-gated)

Reconciliation merges builder worktree commits into one main
**locally** and never pushes on its own authority.

1. **Operator gate 1 (`human-review`).** When every lane is
   `reported`, record the gate
   (`run-advance --phase human-review --owner human --gate human-review`)
   and stop. Wait for the operator to clear it
   (`run-clear-gate human-review`), then
   `run-advance --phase reconcile --owner agent`.
2. Merge every builder's reported worktree commit plus the
   leader's own operational commits into one local `main`,
   resolving any lane overlap (rare, since lanes are
   disjoint).
3. Re-validate the merged tree: typecheck, lint, test,
   build.
4. Advance each landed lane:
   `msd_lane_registry update --slug <builder-slug> --status landed`.
   The registry refuses this (exit 5) while any human gate
   is pending, and until `human-review` has been cleared
   with `run-clear-gate`.
5. **Operator gate 2.** Record it
   (`run-advance --phase land-approval --owner human --gate land-approval`)
   and stop. Only on a second, separate operator
   instruction does the leader push the deploy. The
   reconcile step itself authorizes no push.

The whole sequence is exact so a verifier can dry-run it:
review gate cleared → merge locally → validate → mark
`landed` → park at `land-approval` → stop, with no push.

## 8. Auditor loop

The auditor improves the skills and never implements.

1. The auditor reads the l8 protocol directly, from the l8
   wrapper the consuming repo's wrapper binds.
2. The auditor prompt **explicitly expands l8 scope** to the
   named files: this `multi-swe-day` skill/protocol/scripts
   and the `swe-day` skill/protocol. (l8 reviews only
   pasted/named scope unless the user expands it, so the
   expansion must be explicit.)
3. The auditor runs l8 over those files, labels every
   finding with `file:line`, orders findings P0–P3, and
   appends the mandatory L9/L10 persona escalation addendum
   as the final section.
4. The auditor sends its proposed edits to the leader as an
   **unsolicited `kind:prompt`** (an unsolicited report
   cannot be a `response`, which must reply to a prompt).
   The leader receives it on the `gitchat_poll` loop, not on
   `msd_listen`.

   ```sh
   python3 <gitchat-skill-dir>/scripts/gitchat_send.py \
     --from <auditor-slug> --to swe-day-leader \
     --kind prompt \
     --msg-file <report-file>
   ```

   `--reply-to` and `--conversation-id` are omitted because
   this is an unsolicited send, not a reply to an existing
   prompt.

5. The auditor **proposes only**. The leader (or a builder
   the leader dispatches) implements any accepted change
   under the normal gates.

## 9. Crash recovery

No automatic force-release exists anywhere in this protocol.

- **Builder crash.** The leader `release`s the dead
  builder's lanes
  (`msd_lane_registry release --slug <builder-slug>`) and
  `register`s the day to a healthy builder, which re-runs
  the verify-before-implement gate (§4) from scratch.
- **Leader crash.** The lock and the registry both live on
  disk. A recovering leader confirms the lock with `status`
  using the exact `--repo`/`--lock-path` form (§1), keeps
  working under the owner and session id it records —
  `acquire` refuses a lock that already exists — and reads
  the registry forward — it never resets builder rows.
- **Stale lock.** There is **no force-release flag**. A
  stale lock is resolved by the **operator reviewing the
  lock metadata** (`swe_day_lock.py ... status`) and
  **manually removing the lock directory**. A separate
  audited force-release command is a possible follow-up, not
  part of this protocol.

## Run phase model

One run advances through an ordered, owner-tagged phase
list. Each phase names whether the **agent** or a **human**
owns the next action, and the gate (when any) that must
clear before the run leaves it. The two HUMAN gates that
matter most are `human-review` — which **BLOCKS reconcile**
— and the deploy `push`.

| Phase             | Owner | Gate / note                         |
| ----------------- | ----- | ----------------------------------- |
| `plan`            | HUMAN | operator approves the run plan      |
| `dispatch+verify` | agent | leader dispatches; builders verify  |
| `build`           | agent | builders fan out locally and build  |
| `report`          | agent | builders report worktree commits    |
| `human-review`    | HUMAN | operator reads the held diffs —     |
|                   |       | **BLOCKS reconcile**                |
| `reconcile`       | agent | leader merges locally, re-validates |
| `land-approval`   | HUMAN | operator approves the landing       |
| `push`            | HUMAN | operator authorizes the deploy push |
| `record`          | agent | leader records the landed run       |
| `done`            | agent | run complete                        |

The model is embedded in `msd_next.py`; the registry
stores the run's current state (the `run` object), not the
model. When `run.phase` is
unset, `msd_next.py` DERIVES it from lane statuses: any
`proposed` → `dispatch+verify`; any `assigned`/`in-progress`
→ `build`; all `reported` (none landed) → `human-review`;
all `landed` → `done`; a mix of `reported` and `landed` →
`reconcile`; no lanes, or only `aborted` ones, → `plan`. An explicit `run.phase` or a set
`run.blocking_gate` overrides the derivation: an explicit
phase replaces the derived one, and a set gate forces OWNER
`human` whatever the phase is.

## Active Run mode

While a run is live (the lock is held / the registry is
present), the leader BEGINS EVERY TURN by running the
next-action driver and emitting its banner as the first
lines of the reply:

```sh
python3 <multi-swe-day-skill-dir>/scripts/msd_next.py --registry <path> \
  --lock-path <the held lock path> render
```

The banner is:

```
▶ multi-swe-day ACTIVE · phase <P> · NEXT: <item> · OWNER: human|agent · BLOCKED-ON: <whom>
  next: <the concrete next item>
```

Rules:

- **Never act downstream of an unmet HUMAN gate.** When the
  resolved OWNER is `human` (any of `plan`, `human-review`,
  `land-approval`, `push`, or any set `blocking_gate`), the
  banner names the exact human action (a recorded `--note`
  is shown on its own `note:` line) and the leader stops —
  it does NOT propose or take any agent action behind that
  gate (for example, never offer `reconcile` while
  `human-review` is unmet).
- A human gate clears **only** via the operator's
  `run-clear-gate <name>`. That clears `run.blocking_gate`
  when it matches; the leader then calls `run-advance` to
  the next phase. `run-clear-gate` works only on a gate the
  leader recorded with `run-advance --gate`; a human phase
  the banner merely derived has none, so record it first, as
  the list below does. The opening `plan` phase has no
  command here: the operator's approval is the instruction to
  dispatch, and the first `register` moves the derived phase
  on.

Where the leader calls `run-advance` (each is a registry
mutation, lock-guarded when `--lock-path` is passed):

- **after dispatch** →
  `run-advance --phase build --owner agent` (lanes confirmed
  and building).
- **when all lanes reach `reported`** →
  `run-advance --phase human-review --owner human --gate human-review`
  (park at the review gate; reconcile is now BLOCKED).
- **when the operator clears review**
  (`run-clear-gate human-review`) →
  `run-advance --phase reconcile --owner agent` (reconcile
  becomes the offered next item). The registry refuses
  `update --status landed` until this clear is recorded.
- **after reconcile** →
  `run-advance --phase land-approval --owner human --gate land-approval`
  (park at the landing gate; no push on the leader's own
  authority).

**Showing the held diffs at `human-review`.** When parked at
`human-review` and the operator asks to see or review the
held diffs (a worktree commit, a lane's changes), build the
review surface with `scripts/msd_review_open.py`, not
a hand-rolled `git diff` + `open`:

```sh
python3 <multi-swe-day-skill-dir>/scripts/msd_review_open.py \
  --repo <worktree-or-repo> \
  --range <base>..<head> [--skip-glob 'drizzle/meta/*' ...]
```

It writes ONE `.diff` per path `git diff --name-only` lists,
skipped paths excepted (one VS Code tab per
file — the `.diff` glob is expanded into separate `open`
arguments, never a newline-joined variable), generates a
`CHECKLIST.md` (a review item per written `.diff`, a list of
skipped paths, plus a verdict section), and opens VS Code with the **checklist on
the LEFT half and the diffs on the RIGHT half** via
`osascript` window bounds (graceful fallback to just opening
both if accessibility automation is blocked), always with
`open -a "Visual Studio Code"` — never the `code` shim. The
temp dir is not a workspace the companion extension
activates in on its own, so the helper
opens the diffs as a FOLDER and drops a sentinel pair
(`publish.manifest` + `PROVENANCE.schema.json`) plus a
`.vscode/settings.json` hiding them, which is what makes the
companion VS Code review extension (not included) fire
Cmd+Opt+A on the diff tabs (feeding the address-comments
`.diff` mode). That surface is the operator's review — never
just print the diff inline. The leader presents this only
because the operator asked to see the diffs; it is not an
agent action behind the gate.

## Invariants

1. Single ops-repo writer = the leader.
2. Leader-gated and operator-gated lands.
3. Disjoint lanes (registry, path-normalized, conflicting on
   `proposed` as well as `assigned`, exact and
   ancestor/descendant).
4. The terminal-response listener is `msd_listen`, deduped
   by id — not `gitchat_poll`, which is prompts-only.
5. Verify before implement.
6. Builders fan out **locally** and adversarially verify,
   each sub-agent in an isolated worktree, the builder the
   sole integrator.
7. Non-push reconcile, then a separate operator-gated
   deploy.
8. The auditor proposes only.
9. Registry writes happen only under the held lock, verified
   against the lock owner/session when `--lock-path` is
   passed.
