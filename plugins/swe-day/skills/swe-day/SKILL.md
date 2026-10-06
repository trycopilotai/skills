---
name: swe-day
description: >-
  Run one self-contained "SWE day" of work end to end:
  doSwe(work_item, ops_repo, operator, impl_worktree). Gate
  on the prior work item's state, plan and interview to
  crystal-clear requirements, implement in an isolated
  worktree of the shared repo, validate (unit, e2e, 100%
  incremental coverage proof, overall coverage improvement,
  mutation), render a local result UI, run a multi-persona
  code review plus operator-directed comment ingest, then
  record handoff, timeline, and a private timesheet. Human
  gates punctuate every judgment call, and the agent never
  pushes to the shared repo. Canonical, agent-neutral and
  product-neutral spec; a per-repo wrapper binds the inputs.
  Use when the operator invokes swe-day(<work_item>),
  invokes doSwe(...), or asks to run a sweDay / one unit of
  timeline work.
---

# sweDay

Orchestrate one bounded unit of software work end to end.
This skill is the conductor: it sequences other skills and
protocols (the nine that step 0 of `references/steps.md`
names, such as a bounded fix loop, a result visualizer, a
multi-persona code review and a handoff recorder) and inserts
an explicit human gate at every point where judgment, not
mechanism, decides the next move.

The spec is product-neutral. A per-repo wrapper binds the
inputs below to concrete repos, docs, and commands; this
file never hardcodes a specific product.

## Signature

Primary operator invocation:

`swe-day(<work_item>)`

Expanded signature:

`doSwe(work_item, ops_repo, operator, impl_worktree)`

`swe-day(<work_item>)` is the normal human-facing
entrypoint. It is a stateful controller, not a special
planning syntax. It resolves the work item and current
implementation state, decides the next required phase,
confirms that next action with the operator, then works
autonomously until the next human gate. When human input is
needed, ask the smallest useful interview question,
preferably a 1/2-key choice with a recommended default and
one-line rationale.

Do not treat `swe-day(<work_item>)` as permission to skip
gates. If the next phase would implement, mutate tracked
state, commit, land into a shared repo, or push without
recorded authorization, stop and ask the operator first.

## Inputs

Bound by a per-repo wrapper or passed at call time. With no
wrapper and nothing passed, the run still follows this
protocol: step 0 preflight, the lock, the banner and every
human gate apply exactly as written.

- `work_item` - id of the unit of work in the operator's
  timeline (for example a dated milestone or `D0X`-style
  id).
- `ops_repo` - the operator's private operational context
  repo. Handoff, timeline, progress, plans, and the
  timesheet live here. It may be single-branch; respect its
  branch policy.
- `operator` - the human running the day.
- `impl_worktree` - a worktree of the shared implementation
  repo where code is written, governed by that repo's branch
  policy. Never implement in a worktree of a single-branch
  `ops_repo`.
- `timeline_doc` - path (in `ops_repo`) to the timeline doc
  whose rows carry per-item done/in-progress markers and a
  dependency note.
- `cuj_doc`, `compliance_doc` - optional doc paths passed to
  the code review's opt-in journey and compliance personas.
- `plan_doc` - the day's saved plan, also passed to code
  review's opt-in plan persona.
- `test_cmd`, `e2e_cmd`, `coverage_cmd` - the project's
  validation commands.
- `incremental_coverage_cmd` - optional command that reports
  changed-line, changed-file, or changed-symbol coverage.
  When absent, derive the closest reliable proof from the
  repo's coverage artifact and the implementation diff.
- `overall_coverage_target` - optional desired repo-wide
  target. Default target is 100%, treated as a best-effort
  improvement goal unless the wrapper or repo already makes
  it a hard gate.
- `timesheet` - path (in `ops_repo`) to the append-only
  timesheet.
- `validation_sequence` - optional ordered list of all
  required checks when the repo needs more than the basic
  test, e2e, and coverage commands.
- `local_server` - optional start, health-check, and detach
  instructions for browser, capture, or e2e work.
- `diff_test` - optional command and semantics for comparing
  a reference surface to the changed implementation.
- `result_evidence` - optional policy for where temporary
  result UIs and durable private summaries are recorded.
- `ops_repo_lock` - optional repository and lock path for
  the swe-day lock. The lock itself is not optional: every
  run that goes past the step 0 preflight acquires it at
  the end of step 0, before any other write, and releases
  it when the protocol is done (or keeps it while
  deliberately paused). A run that stops at the preflight
  writes nothing and takes no lock. When no lock path is
  bound, the lock is taken at the lock script's default
  path inside `ops_repo`; `status` with `--repo <ops_repo>`
  prints it as `lock_path` and writes nothing.

## Stateful invocation contract

When invoked through `swe-day(<work_item>)`, run the
state-resolver before choosing an action:

1. Read the per-repo wrapper, this canonical skill, the
   timeline document, any linked prior plans, handoff state,
   target implementation repo guidance, journey docs,
   compliance docs, and validation bindings.
2. Resolve the requested `work_item` and current state:
   timeline status, prerequisites, existing plan, worktree,
   dirty repos, validation evidence, review/comment state,
   record artifacts, and any operational lock.
3. If the requested `work_item` cannot be found, stop with a
   clear blocker and list the closest timeline candidates
   rather than inventing scope.
4. Decide the next phase from evidence, not from syntax:
   prerequisite check, planning/interview, plan review,
   implementation, fix loop, validation, coverage, mutation,
   result review, comment handling, landing, records, or
   final report.
5. Print a compact next-action proposal: current state,
   proposed next phase, why that phase is next, what will be
   touched, what will not be touched, and the next human
   gate.
6. If human judgment or authorization is needed, ask for it
   with the smallest useful prompt. Prefer a 1/2-key
   interview question when choices are concrete; otherwise
   ask for targeted feedback.
7. After the operator confirms the next action, work
   autonomously until the next human gate. At that gate,
   report evidence and ask the next smallest useful
   question.

Required day-plan fields use stable `snake_case` names so
humans and agents can scan plans consistently:

- `work_item` - requested timeline item and resolved title.
- `ops_repo` - private operational repo and mutation rules.
- `impl_worktree` - implementation repo and worktree policy.
- `timeline_doc` - source row, dependency note, and status.
- `plan_doc` - saved plan path or planned saved path.
- `operator_gates` - every required human decision point.
- `validation_sequence` - exact checks and required order.
- `coverage_proof` - absolute command plus incremental proof
  method and acceptance rule.
- `review_flow` - comment ingest, code review, mutation, and
  result review expectations.
- `record_artifacts` - result UI, handoff, timeline,
  progress, review log, and timesheet records.
- `ops_repo_lock` - lock path, owner policy, stale-lock
  behavior, and release rule.

## Model and agent phase roles

This spec stays model-neutral. Select concrete models,
vendors, effort levels, and context windows from the
consuming repo's dispatch policy and current capacity
signal. Use these roles when planning or running a day:

- Planning role - timeline analysis, interviews, tradeoff
  resolution, and final plan synthesis.
- Implementation role - architecture-sensitive edits,
  debugging, and integration work that requires judgment.
- Mechanical role - known-recipe edits, formatting, codegen,
  validation commands, and approved commit execution.
- Review role - independent code, plan, journey, compliance,
  coverage, and risk review, preferably from a different
  provider or perspective than the implementation role.
- Records role - routine private record updates may be
  mechanical; synthesis-heavy progress, handoff, or
  timesheet entries should use a reasoning role.

## Operating discipline

These bind every step.

- **Literal execution.** Do exactly what the step and the
  operator ask. Do not infer extra scope. If a request is
  ambiguous, conflicting, or missing context, ask one
  concise clarifying question before acting.
- **Planning is not execution.** Interviewing the operator
  and getting plan answers decides _what_ and _how_, not
  _go_. Implement only on an explicit, separate instruction.
- **Stay inside the plan.** Before editing a file, confirm
  it is a target named in the day's plan and is not in an
  off-limits area the operator has fenced off. If a needed
  edit falls outside the plan, stop and ask.
- **No new knobs.** Do not add build, config, or environment
  variables without explicit operator approval; inline
  provided values instead.
- **Commits read top to bottom.** Separate mechanical edits
  (codegen, formatting, renames, moves) from semantic edits;
  one concern per commit; order intent, then tests, then
  implementation, then evidence.
- **Validation gates commits.** Never commit while a
  required check is failing; stop and report first.
- **Coverage is evidence, not theater.** Prove 100%
  incremental coverage for changed production behavior
  before calling implementation validation complete. Do not
  lower thresholds, broaden excludes, skip changed files,
  delete meaningful branches, or add tests that only execute
  code without asserting behavior in order to manufacture a
  number.
- **Commit checkpoints are blocking.** At each checkpoint in
  `references/steps.md`, run the bound commit-planning
  protocol before continuing. Print status, changed groups,
  validation state, auto-eligible groups, approval-required
  groups, and the next actor. Stop for operator approval
  unless the wrapper explicitly allows that exact group to
  be auto-committed.
- **Every run past preflight holds the lock.** Every run
  that goes past the step 0 preflight acquires the swe-day
  lock at the end of step 0, before any other write,
  whether or not a wrapper binds `ops_repo_lock`; without a
  bound path it goes at the lock script's default path
  inside `ops_repo`, and the lock directory is never
  committed. A run that stops at the preflight writes
  nothing and takes no lock. A held lock means other agents
  may read and may work in independent implementation worktrees, but
  must not mutate tracked `ops_repo` state. Stale locks are
  reported to the operator; do not clear them
  automatically.
- **Missing delegated skills stop the run.** Step 0 lists
  the nine delegated skills the day needs, each by one
  canonical name, and how to check that it resolves. If any
  is missing, acquire nothing, edit nothing, report the
  missing ones and stop, unless the operator explicitly says
  to proceed without them; that consent is recorded with
  `acquire --proceed-without <skill>`, passing the
  canonical name from step 0, and each step that
  needed a missing skill is reported `NOT-RUN`.
- **Inclusive, neutral language** in every authored surface;
  private labels never cross into the shared repo.
- **Shared repo landing rewrites history.** When applying,
  moving, bringing over, copying, or cherry-picking worktree
  commits into a shared implementation repo, preserve the
  product diff but not the private worktree history. Apply
  patches without committing first, then create fresh
  neutral commits whose subjects, bodies, grouping, and
  metadata do not reveal private work items, same-day
  chronology, review metrics, model labels, private repo
  paths, or source commit mappings.
- **Handoff is deliberate.** Touch handoff and timesheet
  records only at the explicit step in
  `references/steps.md`, not as running bookkeeping.
- **Evidence is explicit.** Every required step is recorded
  as completed, failed, skipped by operator decision, timed
  out, or `NOT-RUN` with the reason. Do not imply a review,
  mutation audit, visualization, or guard completed when it
  only partially ran.
- **Execution contract first.** Before implementation,
  produce a compact contract that names the worktree, plan,
  target surfaces, off-limits surfaces, acceptance criteria,
  validation sequence, review scope, mutation budget, result
  UI behavior, coverage proof method, fingerprint guard, and
  record artifacts.

## Active Run mode

While a swe-day run is live — the swe-day lock is held,
which is true from the end of step 0 for every run that
goes past the preflight — the run is in
**Active Run mode**. The next required action,
who owns it, and the current blocking gate are derived from
state, not improvised. Bind this rule:

- **Begin every turn** by running
  `python3 <skill-dir>/scripts/swe_day_next.py --repo <repo> --lock-path <path> render`
  (`<skill-dir>` is under Helper scripts; `--repo` and
  `--lock-path` are the ones step 0 acquired with, and
  `--lock-path` may be omitted when the default was used)
  and emit its banner
  at the top of your reply. Its first line is
  `▶ swe-day ACTIVE · phase <P> · NEXT: <item> · OWNER: human|agent · BLOCKED-ON: <whom>`;
  up to two indented detail lines can follow.
- **Never act downstream of an unmet human gate.** When the
  banner's OWNER is `human`, state the exact human action
  required and stop. Do not propose, preview, or take the
  next agent phase until the gate clears. A one-shot
  next-action proposal is not a license to keep moving after
  the gate is reached.
- **A human gate clears only by an explicit operator
  action.** The operator (or the agent on the operator's
  explicit instruction) runs
  `python3 <skill-dir>/scripts/swe_day_lock.py --repo <repo> --lock-path <path> clear-gate <name> --owner <owner> --session-id <session>`.
  Within a held lock nothing else removes a pending gate.
  Releasing with `--abandon`, and acquiring again with
  `--phase`, start over without it; both are the operator's
  to ask for, never the agent's to choose. The lock program
  derives the pending gate from the recorded phase and the
  gates cleared so far; the agent does not declare it. The
  agent records the phase it is in with
  `set-phase --phase <p>`, which never moves backward,
  refuses to advance while a gate is pending, and refuses to
  enter the operator's phase.
- **A gated phase reads as the operator's from the moment
  it is recorded.** The agent finishes that phase's own
  work; nothing after it is the agent's until the gate
  clears.
- **The banner fails closed.** OWNER is `human` whenever a
  gate is pending or the lock's metadata is missing or
  unusable. The banner and `set-phase` read the same derived
  state. A second banner line that starts `note:` is free
  text from `set-phase --note` and decides nothing.
- **Ending a run early.** `release` refuses while a gate is
  pending. On the operator's explicit instruction to abandon
  the run, pass `--abandon`.
- If no lock directory exists, `render` prints
  `no active swe-day` and Active Run mode is inactive. That
  is true only before step 0 has acquired the lock or after
  `release`; it is never a way to work without the banner
  or the gates.
- **Showing a diff for a human gate.** When the operator
  asks to see or review a diff (held changes, a worktree
  commit), write ONE `.diff` per changed file into a fresh
  temporary directory —
  `git diff <base>..<head> -- <file> > <dir>/<flat>.diff`
  per file — and open each as its own tab in the operator's
  editor with the wrapper-bound open command (plus the
  worktree; skip huge generated files unless asked). The
  editor is the operator's review surface — never just
  print the diff inline.

## Steps

The steps, numbered 0 to 17 (3 and 4 share a heading), each
tagged with its owner and, where it has one, its blocking
gate, are in
[`references/steps.md`](references/steps.md). Read that file
in full before step 0, and return to it at every step.

## Helper scripts

Run both with `python3`; neither is installed executable.
The scripts live in this skill's directory, not in any
repository you work in, so always call them by `<skill-dir>`, the
absolute path of the directory that holds this `SKILL.md`.
Claude Code prints it as the skill's base directory when the
skill loads; a personal install is `~/.claude/skills/swe-day`,
a project install `.claude/skills/swe-day`, and a plugin
install `skills/swe-day` under the plugin's root. A Codex
install is `~/.agents/skills/swe-day` (or
`.agents/skills/swe-day` in a repository). If unsure, find
the directory that holds `scripts/swe_day_lock.py` next to
this file. A bare `scripts/...` path fails when the shell is
in another directory.
Both take `--repo`, the repository that holds the lock
(the one `ops_repo_lock` binds, or `ops_repo` when none is
bound; never the implementation repository), and a
`--lock-path` that must stay inside it,
and exit 5 otherwise, including for a path that cannot be
resolved. Both options go before the subcommand:
`python3 <skill-dir>/scripts/swe_day_next.py --repo <repo> --lock-path <path> render`.
Both programs need Python 3.9 or later and `fcntl`.

- `scripts/swe_day_lock.py` manages the swe-day lock that
  every run past preflight holds: `acquire`, `status`, `set-phase`,
  `clear-gate` and `release`. Without `--lock-path` it uses
  its default path inside `--repo`; `status` prints the
  resolved `lock_path`, whether or not a lock exists, and
  writes nothing.
  - `acquire` needs `--owner`, `--work-item`, `--plan-path`
    and a session id (`--session-id`, or `CODEX_SESSION_ID`,
    `CODEX_THREAD_ID` or `SESSION_ID` in the environment).
    Owner and session must not be empty. It refuses a lock
    that already exists, never clears a stale one, and
    refuses a path that is a symbolic link or sits inside
    a directory whose `metadata.json` carries this program's
    `session_id` and `work_item` fields. That check is
    best effort: it cannot recognise a damaged lock as an
    enclosing one, and it is not serialized against a
    concurrent `acquire` of the outer path.
  - `set-phase`, `clear-gate` and `release` need `--owner`
    and the same session id. Both must equal what the lock
    recorded, and each check and change runs under one
    advisory file lock.
  - The metadata carries the Active Run state: `phase` and
    the `cleared_gates` so far. `status` adds what is
    derived from them: `pending_gate` and `next_owner`.
  - `acquire --phase <p>` starts a run at a phase other than
    `preflight`. Gates of earlier phases are not asked for.
  - `acquire --proceed-without <skill>`, repeated once per
    skill, records in the metadata (`proceed_without`) the
    missing delegated skills the operator explicitly agreed
    to run without. Pass it only on that consent, with the
    skill's canonical name from step 0. The program records
    any non-empty value; it does not check the name.
  - `set-phase --phase <p> [--note <s>]` records the phase
    the agent is in. The phase must be one of the model's
    and not an earlier one. Advancing needs no gate pending,
    and may not enter or pass a human-owned phase or skip a
    gated phase. Recording the current phase again
    changes only the note (replaced, or removed when
    `--note` is omitted) and the update time.
  - `clear-gate <name>` clears the pending gate and nothing
    else. When the pending gate belongs to the human-owned
    phase that comes next, clearing it moves the run into
    that phase.
  - `release` refuses while a gate is pending unless
    `--abandon` is passed. It removes only the files this
    program wrote and leaves a directory that holds anything
    else.
  - A lock whose metadata is missing or unusable is left
    alone: `set-phase`, `clear-gate` and `release` exit 6,
    `acquire` exits 2 (or 6 when the lock's directory cannot
    be opened), and `status` reports it and exits 0. An
    unknown phase name is refused with exit 4 before the
    lock is read.
    A phase or gate refusal exits 4.
  - The lock is advisory: it coordinates callers that use
    this program and is not a security boundary.
- `scripts/swe_day_next.py` renders the Active Run banner.
  It decides nothing: the phase model (the steps in
  `references/steps.md`, each tagged `owner` and any
  blocking `gate`, plus a closing `done` phase) and the pending-gate rule live in
  `swe_day_lock.py`. `render` names the phase, the next
  required item, the owner, and what it is blocked on. It
  prints `no active swe-day` only when nothing exists at the
  lock path.

## Installing

Copy or vendor this skill directory where your coding agent
loads skills. Keep a thin per-repo wrapper that binds the
inputs (repos, docs, and commands) and delegates here; do
not fork the spec per repo.
