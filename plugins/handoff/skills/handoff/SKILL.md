---
name: handoff
description: >-
  Maintain resumable implementation state across context
  compaction, agent handoff, branch-off work, parallel patch
  attempts, review-comment passes, blockers, validation,
  commits, multi-agent ownership lanes, and long-running
  coding sessions. Use when explicitly asked to create,
  update, resume from, or append to handoff documents such as
  HANDOFF.md, HANDOFF.log.md, or tracked handoff/ state
  files.
---

# Handoff

Use this skill to keep a repository's current implementation
state recoverable by a future agent after an explicit
handoff/checkpoint/resume invocation. A handoff is not a
transcript and is not routine end-of-turn bookkeeping. It is
the compact, technically precise state an engineer needs to
resume work without relying on chat memory.

Routine turn history and lightweight operational metadata
belong in the repository's transcript or memory system when
one exists. Use handoff files for deliberate checkpoints.

## Paths

Every path below is relative to the repository root the
operator chooses: the repository the handoff describes. The
collector takes it as `--repo` and uses the top level of the
git repository that contains that path. When the
repository's own instructions name other files, use those.
Otherwise the defaults are:

| Default              | Holds                                          |
| -------------------- | ---------------------------------------------- |
| `HANDOFF.md`         | the current snapshot                           |
| `HANDOFF.log.md`     | the log, appended to at each state transition  |
| `handoff/state.json` | the multi-agent registry, when lanes are used  |
| `handoff/agents/`    | optional per-agent detail files                |

Of these files, the collector reads only the registry, at
`--state-file` (default `handoff/state.json`). It refuses an
absolute path, one that resolves outside the repository
root, and one it cannot resolve.
`references/update-protocol.md` lists the registry fields it
reads.

`<skill-dir>` below is the directory that holds this file
once installed, for example `~/.claude/skills/handoff` or
`~/.agents/skills/handoff`.

## Workflow

When handoff is explicitly invoked:

1. Read the target repository's standing instructions first
   (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`, or local
   equivalents). Local rules override this generic skill.
2. Read the current snapshot file, usually `HANDOFF.md`, and
   the latest relevant entries in the log, usually
   `HANDOFF.log.md`.
3. Inspect live state with the collector:

   ```sh
   python3 <skill-dir>/scripts/collect_handoff_state.py --repo .
   ```

   Use `--json` when a structured summary is easier to
   transform. Add `--state-file <path>` when the registry is
   not at `handoff/state.json`.

4. Update the snapshot so it names the active objective,
   exact resume point, dirty state, validation state, next
   actions, blockers, important commands, and do-not-do rules.
5. If the repo uses multi-agent lanes, update the ownership
   index in the snapshot and the compact `handoff/state.json`
   registry. Read per-agent detail files only when assigned,
   linked from the relevant row, or needed for a conflict.
6. Append a log entry only for a state transition: saved plan,
   material edits, validation result, commit/push, blocker,
   parallel patch attempt, review-comment pass, deploy, or
   explicit handoff. Do not append a log entry solely because an
   ordinary implementation turn ended.
7. Run the repository's normal formatting / validation for the
   files changed. If local provenance or memory systems exist,
   update them according to local instructions.

## Safety Rules

- Preserve user work. Do not stash, reset, clean, or revert
  dirty files unless the user explicitly asks.
- Do not include secrets, token values, `.env` contents,
  private keys, credentials, or raw proprietary payloads.
- Treat handoff files as operational state. If the repository
  marks them private, never copy their contents into shareable
  docs.
- Keep the snapshot current rather than historical. Keep
  history in the log.
- Keep per-agent detail files optional. Do not bulk-read
  `handoff/agents/*`; summarize ownership from
  `handoff/state.json`.
- Record validation failures honestly, including expected
  pre-existing failures.
- Do not claim a commit, push, migration, deploy, or test
  passed unless it actually ran.

## References

Read these only as needed:

- `references/update-protocol.md` - detailed update sequence
  and state-transition rules.
- `references/snapshot-template.md` - generic `HANDOFF.md`
  template.
- `references/log-entry-template.md` - generic
  `HANDOFF.log.md` entry template.

## Script

The collector writes no file. It runs `git rev-parse`,
`git rev-list`, `git status`, `git log` and
`git submodule status` in the repository, `git rev-parse`
in each submodule directory on disk and `git status` in
each one that is its own checkout, and reads the registry.
Like any `git status`, those calls may refresh git's own
index file. It needs Python 3.9 or later and `git` on
`PATH`; it was tested with git 2.50.1.

```sh
python3 <skill-dir>/scripts/collect_handoff_state.py --repo .
python3 <skill-dir>/scripts/collect_handoff_state.py --repo . --json
```

It exits 0 after printing the report, 1 when `--repo` is
not inside a git working tree, and 2 on a usage error,
including a refused `--state-file`. `--repo` is checked
first. Status 1 also covers any directory git will not
treat as a working tree, such as a bare repository or one
git refuses as unsafe. A registry file that is missing,
cannot be read, cannot be parsed by Python's `json` module,
or is not the expected shape is reported in the output, not
as an exit status. That module also accepts `NaN` and
`Infinity`, which the collector passes through.
Without `git` on `PATH` it stops with a Python traceback and
status 1.
