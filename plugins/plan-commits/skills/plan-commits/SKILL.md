---
name: plan-commits
description: >-
  Plan granular commits for the uncommitted changes in a git
  repository: logical groups labelled mechanical or semantic,
  a summary per file, and added/updated/deleted line counts
  taken from git diff --numstat or wc -l, for line-level
  staging and easy reverts. Use when
  asked to plan commits, or when a caller runs
  planCommits(). Ends with an approval section for the
  operator and does not stage or commit anything itself.
---

# plan-commits

Produce a commit plan for the uncommitted changes in one git
repository. The plan groups the changes into small,
revert-friendly commits, labels each one `mechanical` or
`semantic`, and gives every file a plain-language summary and
line counts taken from `git diff --numstat` or `wc -l`, so the
operator can stage each commit line by line and revert any
one of them alone.

Callers may name this skill `planCommits()`. The steps are
the same however it is invoked.

This skill plans. It does not stage, commit or push. The plan
ends with an approval section. The run ends once the plan is
shown, and saved if the operator asked for that (step 6).

## 1. Read context

- Read the repository's agent instructions, for example
  `AGENTS.md`, and follow the commit rules they give.
- Run `git status --porcelain=v1 --untracked-files=all` to
  see every modified file and every untracked file that is
  not ignored.
- Note the operator's formatting and commit-style
  preferences, for example no subject prefixes, exact line
  counts, or where the summary goes.

## 2. Collect diffs and counts

- Run `git diff --numstat` to get the added and deleted line
  counts for each changed file.
- For new files, get the line count from:
  - `git diff --cached --numstat -- <file>` for a new file
    that is already staged (`A` in the first column of
    `git status`);
  - `wc -l <file>` for a new, untracked file.
- For a gitlink (a submodule pointer), record 0 lines added
  and say that it is a gitlink.
- Do not write approximate counts such as `~40`; prefer
  exact numbers.
- Read the diff of each file before you summarise it.

## 3. Group logical commits

- Find the logical groups in the changes, for example a
  submodule addition, configuration changes, build file
  changes, documentation, or a lint- or format-only change.
- Avoid mixing unrelated changes. Aim for small commits that
  can each be reverted on their own.
- Label each group `mechanical` or `semantic`:
  - mechanical: generated output, format-only changes, a
    bulk rename, file moves, or regeneration;
  - semantic: behaviour, interface, or test logic.
- Never put a mechanical change and a semantic change in the
  same commit.
- Order the commits for reading: intent and interface first,
  then tests, then implementation, then evidence or
  regeneration, with mechanical commits last.

## 4. Detail each file

For each file in a group, give:

- **Summary**: what changed, in plain language.
- **SLOCS added/updated/deleted**: the exact counts from
  step 2. `git diff --numstat` reports only added and
  deleted lines, so `updated` is `0` when that is the
  source.

SLOCS stands for source lines of code. Here it means the
lines that the step 2 commands count.

Put format-only changes in a group of their own.

Give each group a `Label: mechanical` or `Label: semantic`
line. A mechanical group also gets a `Regen: <command>` line
naming the command that re-derives it, so a reviewer can
re-run the command instead of reading the diff.

## 5. Render the plan

- Write a numbered list with one entry per proposed commit.
- Prefix each entry with its label, for example
  `1. [semantic] ...` or `4. [mechanical] ...`, followed by
  the proposed commit subject.
- Under each entry, write one sub-bullet per file. Under
  each file, write two sub-bullets: `Summary` and
  `SLOCS added/updated/deleted`.
- Keep the text ASCII and concise, and follow the operator's
  layout preferences where they differ from this one.
- End with the approval section below.

The shape, with placeholders in angle brackets:

```text
Commit plan: <N> commits, <M> files

1. [semantic] <commit subject>
   - Label: semantic
   - <path>
     - Summary: <what changed>
     - SLOCS added/updated/deleted: <a>/0/<d>
2. [mechanical] <commit subject>
   - Label: mechanical
   - Regen: <command>
   - <path>
     - Summary: <what changed>
     - SLOCS added/updated/deleted: <a>/0/<d>

Approval
- Status: awaiting operator approval. This skill has not
  staged or committed anything.
- To approve: reply with the entry numbers to commit as
  planned, for example "approve 1-<N>" or "approve 1".
- To change: reply with an entry number and the change; the
  plan is re-rendered and approval is asked again.
- Entries that are not approved are left uncommitted.
- This skill does not commit. Approved entries are committed
  after this reply, by the operator or by a caller acting on
  the approval.
```

## 6. Save the plan if asked

- If the operator asks for the plan to be saved, write it to
  the path the operator names, keeping the structure above.
- Do not alter unrelated files.

## 7. Stop for approval

Show the plan and stop. Do not run `git add`, `git commit`,
`git push` or any other command that changes the index, the
history or a remote, even when a group looks safe to commit.
This stop applies even when the repository's instructions
say to commit after planning; the operator decides.

Committing from an approved plan is the operator's job, or
the job of a caller acting on the operator's approval of
this plan. Whoever commits should:

- stage one approved entry at a time, using `git add -p`
  where a file's lines belong to more than one entry;
- use the entry's subject as the commit subject, in the
  style the operator approved;
- put a mechanical entry's `Regen` command in its commit
  body;
- verify with `git status` after the last commit that the
  working tree is clean, or that only the changes of entries
  that were not approved remain, and report what was
  committed.

If the changes move after the plan was shown, run this skill
again rather than committing from a stale plan.
