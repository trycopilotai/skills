# Snapshot Template

Use this as a generic shape for `HANDOFF.md`. Apply local
privacy, provenance, and formatting rules.

```markdown
---
name: Repository Handoff
last_updated: YYYY-MM-DDTHH:MM:SSZ
status: active
active_objective: Brief current objective
resume_here: Exact next action
handoff_log: HANDOFF.log.md
---

# Repository Handoff

## Purpose And Rules

- This file is the current implementation snapshot for an
  explicit handoff/checkpoint/resume invocation.
- Do not update it as automatic end-of-turn bookkeeping for
  ordinary implementation work.
- Keep history in `HANDOFF.log.md`.
- Do not include secrets.

## Resume Here

State the exact command, file, plan, or review step the next
agent should start with.

## Current Repo Graph

Describe the repository, current branch, important SHAs,
upstream status, and, if the repository has submodules, the
important ones and their dirty state.

## Current Working State

List tracked and untracked changes that matter. Say which are
owned by the current agent, which pre-existed, and which must
not be touched.

## Agent Ownership Index

Use this section only when the repo has multi-agent lanes.
Keep it short. Link to per-agent files; do not inline them.

| Scope         | Owner | Model / Surface | Session | Status | Detail                            | Updated    |
| ------------- | ----- | --------------- | ------- | ------ | --------------------------------- | ---------- |
| Example scope | Codex | GPT-5 / Codex   | unknown | active | handoff/agents/example.md         | YYYY-MM-DD |

Agents should read per-agent detail files only when assigned,
linked from a relevant row, or needed for conflict resolution.

## Active Objective

Name the current user request and success criteria.

## Recent Completed Work

Summarize durable completed work with commits or file paths.

## Next Work Queue

Order the next actions. Each item should be decision-complete
or point to the plan that is.

## Known Dirty State

Record dirty files and why they are dirty.

## Validation State

Record commands run, pass/fail results, and expected
pre-existing failures.

## Command Surface

List the commands a resumed agent is likely to need.

## Protocols

Summarize the local review-comment, memory, provenance,
deploy, release, or other protocols a resumed agent must
follow.

## Private / Shareable Boundary

State what must never leave this repo.

## Do-Not-Do List

List destructive or scope-expanding actions to avoid.

## Last Update Checklist

- [ ] Snapshot reflects current dirty state.
- [ ] Log has a state-transition entry if needed.
- [ ] Validation state is current.
- [ ] Provenance / memory systems handled if local rules
      require them.
```
