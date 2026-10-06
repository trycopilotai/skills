---
name: m2
description: >-
  Reference text for m2, a manager-of-managers protocol for
  coding agents. Use when reading, citing or adapting the m2
  conductor protocol, its artifact schemas, the m1 manager
  lane protocol, or the writeAC acceptance criteria protocol.
  Ships four protocol documents and no runnable code.
---

# m2

In these documents `m2` means manager of managers: one
conductor that coordinates manager lanes, reviewers, workers
and testers from a single plan file. `m1` means manager of
individual contributors, the role of one lane inside an m2
run.

This skill is reference text. It holds four protocol
documents and no program. Loading it starts nothing.

## The documents

- `references/m2.protocol.md` is the conductor protocol: the
  invocation contract, the budget and exit contracts, the
  tick loop, the execution phases, the output schemas, and
  the status and failure rules.
- `references/m2-artifact-schemas.md` lists required fields
  for records the conductor protocol uses. It does not cover
  every record and field that protocol names.
- `references/m1.protocol.md` is the protocol for one
  manager lane.
- `references/writeAC.protocol.md` is the protocol for
  turning a request into acceptance criteria. The conductor
  protocol applies it before it writes an acceptance matrix.

Inside the documents, a path that starts with `references/`
is relative to this skill's directory.

The documents are shipped as written and do not fully agree
with each other. Where two passages differ, say so instead
of choosing one silently.

## What the documents depend on

They were written for one repository and its tooling. They
name things this package does not include:

- Companion protocols: `l8()`, `fanOut()`, `dispatch()`,
  `green()` and `greenTick()`.
- Repository tooling: the repository's own `AGENTS.md`, its
  documented lint, prepare and verify commands, its
  devcontainer command surface, and the `git` and `gh`
  commands. The `x_available` field of the Isolation Record
  refers to a repository command runner named `x`.
- A plan store: a separate git repository of plan files.
  The documents write it as `~/<plan-store>`, with the
  identities `<owner>/<plan-store>` and
  `<owner>/<project-store>`. Those are placeholders, as is
  `<repository>`.
- A model: the documents name `gpt-5.3-codex-spark` as the
  default worker model.

## Using the documents

Read `references/m2.protocol.md` in full before acting on
any part of it. It tells a conductor to keep working without
returning control to the human; to commit, push, and open,
update or merge pull requests; to write outside the
repository it was started in (the plan store and a run
directory beside the repository); and to treat a saved
resume prompt as its prompt. Follow it only where the
operator has asked for an m2 run and the things listed above
exist in the repository you are working in. Where one is
missing, say which one instead of substituting for it.
