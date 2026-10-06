# Steps

Human gates are marked. Stop at a gate until the operator
acts.

Each step is tagged `owner: agent|human` and, where one
exists, the human `gate:` that must clear before the next
phase may begin. These tags are the canonical source for the
machine-readable phase model in `scripts/swe_day_lock.py`;
a test keeps the two in sync. The gate names below are the exact
values passed to `swe_day_lock.py clear-gate`, together with
`--owner` and the session id the lock was acquired with.

### 0. Preflight — `owner: agent`

Step 0 runs before any edit, with or without a wrapper.
Confirm the day can run, and fail loudly listing anything
missing. A run that stops in step 0 writes nothing and takes
no lock; every run that goes past step 0 holds the lock.

- Check that each delegated skill below resolves. The name
  is the canonical one: use it in reports and pass exactly
  it to `acquire --proceed-without`. A name resolves when a
  skill of that name is listed among the session's
  available skills, or when the wrapper binds that name to
  a skill or protocol that is listed there; then check the
  bound one. Nothing in this package installs any of them.

  | Skill | Serves | Role |
  | --- | --- | --- |
  | `fix-loop` | step 8 | bounded fix loop |
  | `improve-coverage` | step 10 | coverage improver |
  | `plan-commits` | steps 10, 13, 16 | commit planner, called as `planCommits()` |
  | `mutation-testing` | step 11 | mutation-testing audit |
  | `result-visualizer` | step 12 | result visualizer |
  | `review-watch` | step 12 | review watcher |
  | `address-comments` | steps 10, 12, 13 | operator-comment ingest |
  | `code-review` | steps 10, 13 | multi-persona code review |
  | `handoff` | step 16 | handoff recorder |

- If any of them is missing, this is a hard stop: acquire
  nothing, edit nothing, report the missing ones by name
  and the steps that need them, and stop. Go on only when
  the operator explicitly says to proceed without them.
  Then record that consent with the lock by passing
  `--proceed-without <skill>` to `acquire` once per missing
  skill, with the name from the table, and report every
  step that needed a missing skill as `NOT-RUN` with the
  missing skill as the reason. Never substitute an
  improvised version of a missing skill.
- `impl_worktree` exists and is a worktree of the shared
  implementation repo, not of a single-branch `ops_repo`.
- `timeline_doc` is readable.
- Read the target repos' agent instructions and note any
  off-limits areas before touching code.
- Once every check above has passed (or the operator has
  agreed to go on without the missing skills), acquire the
  swe-day lock before the first edit of any kind:
  `python3 <skill-dir>/scripts/swe_day_lock.py --repo <repo> --lock-path <path> acquire ...`
  (`<skill-dir>` and the `acquire` arguments are under
  Helper scripts in SKILL.md; `--plan-path` may name a plan
  that is not written yet). When `ops_repo_lock` binds a
  repository and lock path, use them. When no lock path is
  bound, `--repo` is `ops_repo` and `--lock-path` is
  omitted, so the script uses its default path inside
  `ops_repo`. To see that path first, run `status` with the
  same `--repo`: it prints `lock_path` and writes nothing,
  before or after a lock exists. Acquiring is the run's
  first write: it creates the lock directory in that
  repository. Never commit it; its metadata records the
  hostname, process id and absolute repository path.
  Use the same `--repo` and `--lock-path` for every later
  helper call. If another lock exists, report its metadata
  and stop for the operator.

### 1. Prerequisite gate — `owner: agent`, `gate: prerequisite-go` _(evidence; human decides)_

From the `work_item` row's dependency note in
`timeline_doc`, resolve the prerequisite ids. For each,
check its done/in-progress marker, any inline sub-markers,
and the handoff resume point. Print an evidence table
(prerequisite, marker, note). The operator decides go/no-go;
if a prerequisite is not done, stop.

### 2. Learn the work item's scope — `owner: agent`

Read the target row (work items, gates, dependencies), any
linked plan files, and the handoff.

### 3-4. Plan and interview — `owner: agent`, `gate: interview-complete`

Draft the day's plan and rigorously interview the operator,
looping until the requirements are crystal clear. If they
cannot be made crystal clear, stop. _(gate: human is
interviewed.)_

### 5. Consolidated plan — `owner: agent`, `gate: plan-review`

Write a decision-complete, pedantic, low-variance plan that
a range of general-purpose coding agents could execute
identically - not only top-tier models. Use test-driven
patterns: state the happy path, the error cases, and the
edge cases for the new behavior. The code is implemented in
`impl_worktree`. Include an execution contract with the
target worktree, source plan, target files or subsystems,
off-limits areas, acceptance criteria, exact validation
sequence, review requirements, mutation scope and budget,
local result UI expectations, coverage proof method,
fingerprint guard, private record artifacts, and `NOT-RUN`
policy. The coverage proof method must name how 100%
incremental coverage will be measured for changed production
code and how the agent will attempt to move overall coverage
toward 100% without gaming exclusions or assertion quality.
Save the plan into `ops_repo` with date-kebab naming before
any implementation. _(gate: human reviews the plan.)_

### 6. Final buyoff — `owner: human`, `gate: final-buyoff`

Get an explicit go from the operator. _(human gate.)_

### 7. Implement — `owner: agent`

Implement the plan in `impl_worktree`, staying inside the
plan's target files and the operating discipline in
`SKILL.md`. Before the first code edit, restate the
validation sequence and any local server requirements that
will gate completion.

### 8. Fix loop — `owner: agent`

Run the bounded fix loop to drive the prescribed and added
test cases to green, with an iteration cap of 8 (raise to at
most 16 for a heavy day).
On exhaustion, stop and surface the failing case to the
operator rather than looping further.

### 9. Unit and e2e tests — `owner: agent`

Run the bound `validation_sequence` when supplied; otherwise
run `test_cmd` and `e2e_cmd` and collect results. Never
proceed to commit on a failing required suite. When a
required check cannot run, record it as `NOT-RUN` with the
concrete blocker rather than omitting it.

### 10. Coverage — `owner: agent`, `gate: commit-checkpoint-1`

Run `coverage_cmd` and collect absolute repo-wide results.
Then prove incremental coverage for changed production
behavior:

- Prefer `incremental_coverage_cmd` when bound.
- Otherwise derive a changed-code report from the coverage
  artifact and the implementation diff. At minimum, list
  each changed production file and the changed lines or
  exported behaviors that are covered by tests.
- Watch for path-based false zeros: if the implementation
  worktree path is accidentally excluded by coverage config
  (for example an exclude such as `worktrees/**` matching
  the checkout path), rerun with a scoped override that
  preserves the repo's real source excludes but includes the
  current checkout, and record both commands.
- The required target is 100% incremental coverage for
  changed production code. If a tool cannot produce a
  numeric changed-line percentage, use a traceable proof
  table: file, changed behavior, test name or command,
  assertion, and covered failure mode.
- If 100% incremental coverage is not achieved, stop before
  commit checkpoint 1 unless the operator explicitly accepts
  the gap. Record each uncovered behavior, why it remains
  uncovered, the test needed, and whether the blocker is
  technical, time-budget, or scope.
- Drive absolute repo-wide coverage as close to 100% as
  possible by running the `improve-coverage` skill, scoped
  to the day's touched modules and nearby high-value gaps.
  Apply its workflow: scope-interview the operator until
  rock-solid, measure honestly (mind the path-based false zero
  above), fan out one agent per uncovered file to workshop
  tests toward 100%, then review the new tests with fresh
  code-review and address-comments agents. Stay tests-only —
  never modify production behavior solely for coverage or
  weaken meaningful branches — and keep scope inside the
  day's plan, not a broad expansion. Honestly report any
  genuinely-unreachable code that caps the number below
  100%. The improve-coverage commit/planCommits step is
  satisfied by commit checkpoint 1 below; do not run a
  separate commit.

Run commit checkpoint 1 after implementation validation: run
`planCommits()` or the bound commit-planning protocol
against every dirty repo involved in the day. The checkpoint
must separate implementation changes, generated artifacts,
private operational records, submodule pointers, and
protocol changes. Do not proceed to mutation/review work
until the operator approves all approval-required groups or
the wrapper auto-commits only explicitly auto-eligible
private tracker groups.

### 11. Mutation testing — `owner: agent`

Audit the suite with the mutation-testing skill, run from
`impl_worktree` with `test_cmd` as the fixed test command.
Restore the baseline after every trial and never leave a
mutant in the working tree; collect surviving mutants as
concrete test gaps. If the audit genuinely cannot run,
report `NOT-RUN` with the reason rather than skipping
silently.

### 12. Present and open — `owner: agent`, `gate: code-result-review` _(human reviews implementation)_

Render a scripted, repeatable local web UI of the day's
results - tests, absolute coverage, incremental coverage
proof, uncovered changed-code gaps, mutation score, and an
explicit list of anything `NOT-RUN` - using the result
visualizer. If the repo binds a temporary artifact policy,
keep the UI out of the shared implementation repo and record
the URL or path in the private operational record. Open an
editor in `impl_worktree`.

When the editor opens on `impl_worktree`, start the
`review-watch` loop over that worktree so the agent-directed
markers the operator writes while reading - `agent`-directed
labels and `TODO(code-review:<id>)` markers - are addressed
live through the `address-comments` skill instead of waiting
for a single later batch pass. review-watch only detects and
delegates; it edits the worktree under review through
address-comments, runs until the operator ends the review or
step 14 reaches done, and never commits or lands. This makes
the live watch the default companion to the batch ingest in
step 13, not a replacement for it.

Then reopen the relevant review surfaces for the operator:
the live local app when the day has UI-visible behavior and
`local_server` is bound, and the result evidence UI/artifact
when one was produced. After the editor and browser surfaces
are open, print a `New UX To Test` block for the operator.
The block must name:

- `Where` - editor path, app URL when applicable, and
  evidence artifact URL/path.
- `Role/persona` - the role, tenant, seeded user, or persona
  to use when applicable.
- `What changed` - visible UX changes only, not an
  implementation dump.
- `How to test` - short manual interactions that exercise
  the change.
- `Expected result` - visible state, persistence, audit,
  validation, or workflow outcome.
- `What did not change` - compatibility notes, especially
  preserved surfaces.
- `Caveats` - `NOT-RUN`, partial validation, server issues,
  or non-UI notes.

For non-UI work, still print the block with
`No user-facing UX change expected` and point to the
relevant evidence artifact instead of inventing UX changes.
_(gate: human reviews the code and visible result.)_

### 13. Address comments and review — `owner: agent`, `gate: commit-checkpoint-2`

On the operator's request, ingest operator-directed comments
with the `address-comments` skill (operator-attribution and
`agent`-directed labels for every comment leader). Then run
the multi-persona code review over `impl_worktree`, passing
explicit absolute doc paths so the opt-in personas activate:
`plan_doc` (plan persona), `cuj_doc` (journey persona), and
`compliance_doc` (legal/compliance persona). Write the
consolidated findings back inline as review comments. Follow
each skill's own spec exactly; address each comment as its
own focused, separately committable change. _(gate: human
reviews the changes.)_

Run commit checkpoint 2 after review/comment fixes: rerun
the bound commit-planning protocol, update grouping for
review fixes, and stop for operator approval unless the
wrapper explicitly allows the exact private tracker group to
be auto-committed.

### 14. Iterate to done — `owner: agent`

Continue with the operator until the code is agreed done.
Done = committed in `impl_worktree` after the relevant
checkpoint commit plan has been approved or otherwise
resolved under the wrapper's authority rules.

### 15. Pre-handoff scrub, landing, and fingerprint guard — `owner: agent`, `gate: landing-approval`

Before any worktree changes are applied to the shared repo,
inspect the source commits and diff, then plan the shared
landing as a history rewrite. Use `git cherry-pick -n`, a
diff/apply flow, or an equivalent no-commit patch
application; do not preserve original private/worktree
commit subjects, bodies, operational grouping, or same-day
chronology. Recommit in the shared repo with neutral
product/workflow messages, collapsing, splitting, or
reordering commits when needed to remove private shape while
preserving reviewable product intent.

Run a fingerprint guard over the source commits, staged
shared-repo diff, filenames, branch/worktree names, docs,
and proposed commit messages. Shared repo-visible metadata
must not contain private work item ids, private timeline
labels, review counts, coverage or mutation
percentages, token/time/budget metrics, model-agent labels,
private repo paths, or source-to-landed commit mappings.
Keep all quantitative results and exact commit mappings in
`ops_repo`. Re-run targeted validation from the shared
target checkout after applying the patch. The agent never
pushes to the shared repo. If no automated guard is bound,
run the best available text scan and record the guard as
manual with its exact command. _(gate: the operator approves
the landing.)_

### 16. Record — `owner: agent`, `gate: commit-checkpoint-3`

Update the handoff, the timeline (add status around the
original goal; never replace planned scope), and the
progress log, and append a rich entry to `timesheet` (date,
`work_item` id, elapsed time, steps completed,
test/absolute-coverage/incremental-coverage/mutation summary
with any `NOT-RUN` reasons, evidence links, worktree branch
and commit ids). Use the handoff skill for the handoff
update rather than editing those files ad hoc.

Run commit checkpoint 3 after private record updates: rerun
the bound commit-planning protocol for `ops_repo`, identify
auto-eligible private tracker groups and approval-required
groups, commit only groups the wrapper authorizes, and leave
the lock held until the checkpoint is resolved or the
operator directs a pause.

### 17. Report — `owner: agent`

State what was done and the client-facing implementation
steps in neutral wording. Include a compact
protocol-completion checklist naming every required
validation, absolute coverage, incremental coverage proof,
review, mutation, visualization, fingerprint, and record
step as completed, failed, timed out, or `NOT-RUN`. Report
the incremental coverage percentage or proof status before
the absolute coverage percentage; a green test suite without
100% incremental coverage is not a complete swe-day unless
the operator explicitly accepted the gap. Release the lock
only after all intended mutations are complete and the
final status has been reported. If the run is paused,
report that the lock remains held and why.
