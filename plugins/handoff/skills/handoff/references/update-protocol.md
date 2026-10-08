# Handoff Update Protocol

Use this protocol only after an explicit human request or a
named workflow checkpoint.
Do not run it as automatic start/end bookkeeping for ordinary
implementation turns.

## Read First

1. Read local repository instructions.
2. Read the current snapshot.
3. Read the latest relevant log entries.
4. Inspect live git state, and submodule state if the
   repository has submodules.
5. Read the active plan or issue, if one exists.

## Update Snapshot

Keep `HANDOFF.md` as the current truth. Replace outdated
state. Do not let stale next steps linger after they are done.

Always capture:

- active objective and exact resume point;
- current branch, HEAD, upstream, and submodule state if
  any;
- dirty files and ownership;
- pending plans and next actions;
- commands needed to run, test, build, deploy, or review;
- validation that passed, failed, or was not run;
- known blockers and expected pre-existing failures;
- private/shareable boundaries;
- destructive actions to avoid.

If the repository uses multi-agent lanes, keep only a concise
ownership index in the snapshot. The index should link to
per-agent detail files but not inline those details.

Use `handoff/state.json` as the compact machine-readable
registry when present. It should record each agent/session,
model or surface, status, owned scopes, linked detail file, and
last update. Per-agent detail files are optional context:
agents should read them only when assigned, linked from a
relevant row, or needed to resolve a conflict.

The bundled collector reads these fields and ignores any
others. Each one may be absent. In its `--json` output an
absent field is an empty string or list (`null` for
`schema_version`), and a `null` value stays `null`. `chat_uuid`
is the agent's session or chat identifier; the table shows it
as Session. Its
Markdown table shows the per-agent fields except the scope
paths and `agent_id`, which it shows only in place of an
owner that is missing, `null` or
`""` (not one that is `0` or `false`). It shows each value
as one line of text: `null` as empty, `true` and `false` as
written, runs of whitespace as one space, a character that
cannot be encoded as UTF-8 as `?`, `\` as `\\`, and `|` as
`\|`.

```json
{
  "schema_version": 1,
  "updated_at": "2026-01-01T00:00:00Z",
  "agents": [
    {
      "agent_id": "cli",
      "owner": "agent-a",
      "model": "model-a",
      "surface": "Claude Code",
      "chat_uuid": "session-a",
      "status": "active",
      "detail_path": "handoff/agents/cli.md",
      "owned_scopes": [{ "name": "cli", "paths": ["greeter.py"] }],
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

The top level must be an object, `agents` (when present) a
list of objects, and each `owned_scopes` (when present) a
list; a `null` there is not a list. Otherwise the collector
reports that the file could not be parsed and lists no
agents. A scope that is not an object is skipped.

Do not bulk-read `handoff/agents/*`. Large per-agent Markdown
details are intentionally outside the default context path.

## Append Log

Append to `HANDOFF.log.md` when a state transition happens:

- a plan is saved or materially revised;
- a meaningful edit set lands;
- validation passes or fails in a way future agents need;
- a commit, push, migration, deploy, or rollback occurs;
- a parallel patch attempt starts, finishes, or degrades;
- review comments are addressed or left blocked;
- a blocker is discovered;
- the agent is explicitly handing off.

Do not log every small read/search operation. Use transcript or
memory tools for routine turn history and lightweight state
metadata if the repository provides them.

## Validation

Run the narrowest validation that proves the handoff update is
well-formed:

- format check for touched Markdown/YAML/JSON;
- JSON parse for machine-readable metadata;
- script compile/tests for helper changes;
- provenance or other checks the repository's own
  instructions name for these files.

Report pre-existing failures separately from failures caused
by the handoff update.
