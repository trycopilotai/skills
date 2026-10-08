# swe-day summary

Use `swe-day` for one bounded implementation unit. The agent
plans, implements, validates, reviews, records, and reports,
but the operator owns judgment calls and shared repo handoff
decisions.

## Invocation

`swe-day(<work_item>)` is the single operator-facing
invocation. It reads the repo wrapper, canonical skill,
timeline, prior plans, handoff state, implementation repo
guidance, journey docs, compliance docs, validation
bindings, dirty state, and existing evidence before deciding
what should happen next.

The agent prints the proposed next phase and asks the
smallest useful human gate before acting. Prefer a 1/2-key
interview question with a recommended default when concrete
choices exist; otherwise ask for targeted feedback. After
the operator confirms, the agent works autonomously until
the next human gate.

When the next phase is planning, the resulting plan should
use stable `snake_case` fields such as `work_item`,
`ops_repo`, `impl_worktree`, `operator_gates`,
`validation_sequence`, `coverage_proof`, `review_flow`,
`record_artifacts`, and `ops_repo_lock`.

## Turns

- Agent gathers evidence, drafts the plan, implements inside
  the implementation worktree, runs validation, prepares
  commit plans, and records explicit evidence.
- Operator approves prerequisites, reviews the plan, gives
  the explicit implementation go, reviews code/results, and
  approves semantic or shared/public commits.
- Planning/interview answers are not permission to edit.
  Implementation starts only after the relevant operator
  gate is confirmed in the current or recorded state.

## Required Human Gates

- Prerequisite go/no-go.
- Plan review and final implementation buyoff.
- Result/code review after validation evidence is rendered.
- Operator acceptance for any changed production behavior
  that cannot prove 100% incremental test coverage.
- Review/comment-fix approval.
- Any semantic commit, shared/public repo commit, protocol
  change, submodule pointer update, generated artifact,
  raw/source evidence import, provenance update, or mixed
  commit.
- Any stale operational repo lock.

## Commit Checkpoints

Run `planCommits()` as a blocking checkpoint:

- after implementation validation;
- after review/comment fixes;
- after private record updates.

Each checkpoint separates implementation work, generated
artifacts, private records, submodule pointers, and protocol
changes. The agent stops for operator approval unless the
repo wrapper explicitly marks the exact group as
auto-committable.

## Coverage Gate

Implementation validation includes both absolute and
incremental coverage:

- Prove 100% incremental coverage for changed production
  behavior before the first commit checkpoint.
- Prefer a repo-bound changed-code coverage command. If none
  exists, derive a proof table from the diff and coverage
  artifact: file, changed behavior, test, assertion, and
  covered failure mode.
- If coverage config accidentally excludes the
  implementation checkout path, rerun with a scoped override
  and record both commands.
- Try to improve overall repo coverage toward 100% when the
  needed tests stay inside the day's plan. Do not game the
  number by weakening exclusions, deleting branches, or
  writing assertion-free execution tests.
- If incremental 100% is not achieved, stop for operator
  acceptance and record the uncovered behavior and needed
  test.

## Phase Roles

The canonical skill stays model-neutral. Use the consuming
repo's model-selection policy and live capacity signal to
map planning, implementation, mechanical validation, review,
and records work to concrete agents or models. Keep review
as an independent perspective when possible.

## Result Review

When presenting a completed implementation for human review,
open the implementation worktree in the editor, reopen the
live app when the work has UI-visible behavior, and open the
`htmlify` evidence artifact when one was produced. Then
print a `New UX To Test` block with the review location,
role/persona, visible changes, manual test interactions,
expected result, unchanged compatibility surfaces, and any
`NOT-RUN` or partial-validation caveats. For non-UI work,
say `No user-facing UX change expected` and point to the
evidence artifact instead.

## Auto-Commit Boundary

The agent may auto-commit only wrapper-authorized private
tracker artifacts after checks pass. Examples can include
private plans, handoff, timeline/progress, review log, and
timesheet records.

Everything else needs operator approval before commit,
especially semantic code, shared/public repos, protocol
edits, app repos, submodule pointers, and mixed diffs.

## Missing Delegated Skills

Step 0 lists the nine delegated skills the day needs, each
by one canonical name. If any is missing, the agent
acquires nothing, edits nothing, reports the missing ones
and stops. It goes on only when the operator explicitly
says to proceed without them; that consent is recorded with
the lock under the canonical names, and every step that
needed a missing skill is reported `NOT-RUN`.

## Operational Repo Lock

Every run that goes past the step 0 preflight acquires the
swe-day lock at the end of step 0, before any other write,
whether or not a repo wrapper binds one. A run that stops
at the preflight writes nothing and takes no lock. Without
a bound path the lock is taken at the lock script's default
path inside `ops_repo`, and the Active Run banner and gates
apply from then until the run ends. Other agents may read and may work
in independent implementation worktrees, but must not mutate that
operational repo while the lock is held.

Stale locks are never cleared automatically. Report the
owner, age, work item, and plan path, then ask the operator.
