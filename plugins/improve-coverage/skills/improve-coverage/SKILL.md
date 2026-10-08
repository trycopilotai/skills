---
name: improve-coverage
description: >-
  Raise automated test coverage on an operator-defined
  scope. Interview the operator about the scope first,
  unless a calling skill passes the scope and the coverage
  command (non-interactive mode); then measure coverage
  honestly, fan out one agent per uncovered file to write
  tests to the target, run a typecheck/lint fix-up pass
  over the new tests, and handle genuinely-unreachable
  defensive guards explicitly.
  Canonical, agent-neutral and product-neutral spec; a host
  repo binds the test runner, commit/privacy rules, and any
  private operational log.
---

# improve-coverage

Use this skill when the operator asks to improve, raise, or
"finish" code coverage, or when another skill calls it with
a scope. It turns a vague "get coverage up" into a
deterministic, interview-scoped, parallel test-writing pass
that reports an honest number.

The engine is a massive fan-out: one subagent per uncovered
file, each writing only that file's tests and verifying its
own scoped coverage, run concurrently. The skill wraps that
engine with a scoping interview (required unless a caller
passes the scope; see Non-interactive mode), honest
measurement, an integration fix-up, and explicit handling of
code that genuinely cannot be covered.

## Core principles

1. **Interview until rock-solid.** Interview the operator
   about the scope of the coverage improvements and keep
   iterating the questions until the scope is rock-solid —
   not one round, but as many as it takes to remove every
   ambiguity. Do not measure or write anything until it is
   locked. In non-interactive mode the caller's inputs lock
   it instead.
2. **Test code only.** Write test code only. Do not edit
   implementation files unless a change is genuinely
   required to make code testable AND the operator
   explicitly signs off on that specific change first. In
   non-interactive mode no one signs off, so no
   implementation file is edited.
3. **Workshop toward 100%.** Workshop the tests until
   absolute coverage is as high as possible — ideally a
   literal 100%. Keep iterating, per file and in aggregate;
   stop only at the target or at code that is genuinely
   unreachable (Step 5), and say which it is.

## Non-interactive mode

A calling skill that already knows the scope can pass it,
and the Step 1 interview is skipped. `swe-day` is one such
caller: at its step 10 it runs this skill on the production
code changed that day.

The mode applies only when the caller passes both of these:

- **`scope`**: either an explicit list of production files,
  or a diff base (a commit, branch or tag). With a diff
  base, the scope is the files `git diff --name-only <base>`
  lists, less test files, generated files and files the
  change deleted.
- **`coverage_cmd`**: the command that measures coverage in
  this repository, exactly as the caller runs it.

It may also pass:

- **`target`**: the coverage to reach. Default: a literal
  100% of every metric `coverage_cmd` reports, for each file
  in the scope.
- **`exclusions`**: globs to leave out of the scope.
- **`commit`**: whether this skill may commit. Default: it
  may not. Steps 7 and 8 are then skipped and the changes
  are left uncommitted for the caller.

If neither input is passed, run the Step 1 interview as
usual. If only one of the two is passed, or the scope
resolves to no file, do not guess, do not widen the scope
and do not start the interview: stop and tell the caller
which input is missing or empty.

The inputs are free text in the caller's request, for
example:

```text
scope: diff base main, less test files
coverage_cmd: make coverage FILES="<files in scope>"
target: 100% of lines and branches
commit: no
```

Here `<files in scope>` stands for the scope's file list,
which the agent fills in. For Step 3's per-file runs, the
agent narrows `coverage_cmd` to one file the same way.

In this mode:

- The passed inputs are the locked Step 1 answers. Do not
  ask the operator about scope, target or runner.
- Write test code only. No one is there to sign off on an
  implementation change, so do not edit production files
  for any reason, comments and coverage-ignore directives
  included. Never change production behaviour for
  coverage's sake. A file that cannot reach the target
  without a production change keeps its gap, and the result
  says what change would be needed.
- In Step 5, report unreachable code in the result only: no
  annotation, ignore directive or refactor.
- If `coverage_cmd` does not count files that no test
  imports (Step 2), say so in the result instead of
  changing the command.
- Do not add files outside the scope to the work queue.
  Step 4 still runs the full suite, the type-checker and the
  linter.
- Do not push.
- Return the Step 9 table to the caller.

## Step 1 — Interview until the scope is rock-solid (REQUIRED, FIRST)

Skip this step in non-interactive mode.

Interview the operator and keep iterating until the scope is
rock-solid — repeat and refine the questions until no
ambiguity remains; one round is rarely enough. Do NOT
measure or write anything before the scope is locked. Use
the host's structured-question / interview mechanism when it
has one. Resolve at least:

- **Scope.** Whole repo, one package, a directory, an
  explicit file set, or changed-files-only? Name the exact
  include globs.
- **Target.** Literal 100%, or a threshold (lines / branches
  / functions)? Which metrics matter?
- **Exclusions.** Vendored or generated code (for example a
  UI submodule), end-to-end tests, type-only declaration
  files, fixtures.
- **Runner and provider.** Which test runner and coverage
  provider, and any environment constraints (see Step 2's
  provider caveat).
- **Output discipline.** May new test files be committed,
  and where (an isolated worktree vs the main checkout)? Is
  a push authorized? (Default: no push.)
- **Unreachable code.** How to handle genuinely unreachable
  defensive guards — accept and document, annotate with an
  ignore directive, or refactor (see Step 5).

Lock these before proceeding. Interviewing is planning, not
execution: it decides what and how, not go.

## Step 2 — Measure current coverage honestly

- Run the coverage tool over the locked scope with its
  all-files mode ON, so files that no test imports still
  count. Without it, untested files are silently absent and
  the number lies high.
- **Provider caveat.** If the default provider reports 0/0
  or "unknown" (some V8-based providers do not instrument
  under newer runtimes), switch to a source-instrumenting
  provider (istanbul-style). If it is not installed,
  install it transiently without committing a dependency
  change (unless the operator approved one), or run under a
  runtime version the provider supports.
- Produce the exact list of under-target files with their
  uncovered line and branch numbers. That list is the work
  queue.

## Step 3 — Fan out: one agent per uncovered file

Dispatch the work deterministically (a workflow / parallel
fan-out), one subagent per uncovered file. Cap concurrency
to the host's limit; excess queue. Each agent:

- reads its target file and enumerates every branch,
  function, and export;
- studies the repo's existing test idioms FIRST (how the DB,
  network, framework, and components are mocked or rendered)
  and REUSES them — it does NOT invent a parallel harness;
- writes ONLY that file's colocated test, then verifies with
  SCOPED coverage limited to its file and a UNIQUE report
  directory, so concurrent runs do not collide;
- iterates against the "uncovered lines" output until its
  file hits the target, or reports the lines that are
  genuinely unreachable;
- stays tests-only: no source edits, no shared setup/mock
  files (concurrency would race on them), no commits.

Each returns a structured per-file result (final
percentages, test file, residual uncovered lines and why).

## Step 4 — Integrate and verify

Concurrent agents verify coverage at RUNTIME but do not run
the full type-checker or linter, so expect fix-ups:

- Run the FULL suite, the type-checker, and the linter
  together over the whole scope.
- Dispatch a fix-up agent (or fix directly) to make
  type-check and lint clean WITHOUT deleting test cases or
  dropping coverage — fix mock fixtures to satisfy real
  types, remove dead directives, rewrite bare-expression
  assertions, format.
- Re-measure the aggregate over the scope and report the
  real number.

## Step 5 — Genuinely-unreachable code

Some branches cannot be reached by any test because the call
site or render-gating makes the guard's condition impossible
(a defensive early-return whose handler only runs when the
guard is already satisfied). Never silently suppress these.

Per the operator's Step-1 choice:

- **Accept and document** — annotate each with a findable
  comment (for example `COVERAGE-GAP:`) stating exactly why
  it is unreachable, and report the residual percentage as
  the honest result.
- **Ignore directive** — add a documented coverage-ignore
  directive on each, only for guards proven unreachable,
  never to mask a real gap.
- **Refactor** — remove the now-redundant guard (operator
  approval required; it weakens defense in depth).

## Step 6 — Review the changes with fresh agents

Review the test changes with FRESH review agents — a clean
perspective, not the agents that wrote the tests. Bind these
to the host's review skills, for example
`multi-persona-code-review` then `address-comments`.
Neither ships with this skill. If the host has no review
skill, review with a fresh agent anyway and say in the
summary which skill was missing:

- `multi-persona-code-review` reviews the new and changed
  test files and writes its findings back as in-source
  review markers.
- `address-comments` then resolves those markers (and any
  agent-directed comments), fixing or recording each.

Keep it tests-only (Principle 2). The review may surface
weak assertions, flakiness, missed branches, or shared-state
leaks; address them in the tests, never by editing
implementation unless it is required and the operator signs
off.

## Step 7 — Plan the commits

Run the host's commit-planning protocol/skill — for example
`plan-commits`, called as `planCommits()` — over the
dirty/staged changes: split semantic from mechanical, order
commits for review, give per-file SLOC summaries, and
produce a decision-complete plan. Do not hand-roll the
grouping when the host has a planCommits protocol.

## Step 8 — Commit the changes

Commit per the Step 7 plan. Tests-only, neutral messages; if
the host repo forbids private metrics in shared history,
keep coverage percentages OUT of commit subjects and bodies.
Do not push unless the operator authorized it. If the host
keeps a private operational log, record the run there
(scope, target, before/after numbers, unreachable lines),
not in shared docs.

## Step 9 — Summarize the work as a table

Present a Markdown table summarizing the run for the
operator. One row per file (or scope unit) with at least
before % to after %, tests added, and any
residual/unreachable note, plus an aggregate row and the
commits created. The table is the deliverable the operator
reads to verify the outcome at a glance.

## Honesty rules

- Report the real aggregate, including what could not be
  covered and why. A "100%" that hides ignore directives
  over real gaps is a regression in trust, not a win.
- State which gates ran and which were skipped or blocked
  (for example a coverage provider that could not run), and
  why.

## Installing

Install this skill where your agent loads skills (the
README has pinned install commands for Claude Code and
Codex), then keep a thin host wrapper that binds the test
runner and coverage commands, the interview mechanism, the
commit/privacy rules, and any private log. Do not fork the
spec per repo.
