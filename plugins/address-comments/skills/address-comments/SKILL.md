---
name: address-comments
description: >-
  Find and address agent-directed review comments left in
  source or docs as AGENT:, AGENTS:, TO AGENT, or TO AGENTS
  labels (plus any operator-attribution labels a host
  wrapper registers) or TODO(agent) / TODO(agents) markers,
  and code-review markers written as TODO(code-review:<id>);
  make or plan the requested change,
  remove the addressed comments, and append a private
  review-log entry at an operator-chosen path (default
  .address-comments/review-log.md in the repository being
  edited). Canonical, agent-neutral and product-neutral
  spec; an optional per-repo wrapper binds the review-log
  path, extra labels, and search excludes.
---

# Address Comments

Use this skill when the user asks to address review
comments, to scan for agent comments, or to process the
`AGENT:` / `AGENTS:` / `TODO(code-review:<id>)`
conventions.

## Trigger Markers

Address-comments owns two trigger classes.

### Agent and operator labels

Treat text as an agent/operator address-comments item when it
appears in a code or document comment and uses one of these
labels, case-insensitively:

- `AGENT:`
- `AGENTS:`
- `TO AGENT`
- `TO AGENTS`

`AGENT:` covers the singular form for any comment leader,
including the Python `# agent:` style.

A host wrapper may register additional operator-attribution
labels of the form `<name> says:` (for example
`reviewer says:`). Treat any registered label with the same
authority as `AGENT:`.

Also treat the marker shapes `TODO(agent)` and
`TODO(agents)` as agent-directed instructions, with the same
authority as `AGENT:`. Match them case-insensitively, in
either the singular or plural form, and tolerate accidental
whitespace inside or before the parentheses (for example
`TODO ( agent )`). The instruction text follows the marker,
typically after a colon (for example
`// TODO(agent): rename this helper`). These are handled like
the agent labels — implement the change, then remove the
comment — not like the code-review markers below, which
require finding verification first. Bare `TODO:` without the
`(agent)` / `(agents)` (or `(code-review:<id>)`) shape is
still not a trigger.

### Code-review markers

Treat this exact marker shape as an address-comments item:

```text
TODO(code-review:<id>)
```

The marker may appear in an inline source/document comment or
inside a `CODE_REVIEW.gpt.md` checklist entry. The `<id>` is
the stable code-review finding id. When present, parse the
severity (`[P0]`-`[P3]`), finding text, impact, fix
direction, evidence, and persona tags from the marker text,
but do not require every field to exist.

Do not treat generic `TODO:` comments as address-comments
items. Only the explicit `TODO(code-review:<id>)` shape is a
code-review marker.

The separately installed `multi-persona-code-review` skill
writes markers in this shape. It is not part of this skill.
Markers in this shape are handled the same way whoever
wrote them, so this skill does not depend on it.

## Search

Search from the repository root with `rg` first. Exclude
generated, vendored, transcript, and mock-output trees
unless the user explicitly asks to inspect them; a host
wrapper supplies the repo-specific exclude globs.

Base scan (extend the alternation with any registered
operator labels, and add the host's exclude globs):

```bash
rg -n -i \
  '((^|[[:space:]])(//|#|--|/\*|\*|<!--)\s*(agents?:|to[[:space:]]+agents?\b)|TODO\s*\(\s*agents?\s*\)|TODO\(code-review:[^)]+\))'
```

The `TODO(agent)` / `TODO(agents)` arm matches singular and
plural, is case-insensitive (`rg -i`), and tolerates
accidental whitespace inside or before the parentheses (for
example `TODO ( agent )`).

The scan is a candidate finder, not a substitute for
reading. For every match, read enough surrounding context to
confirm the label is inside a real comment and not a string
literal, URL, generated artifact, or unrelated prose. For
`TODO(code-review:<id>)`, also confirm whether the marker is
inline in a comment or in a `CODE_REVIEW.gpt.md` checklist
entry.

## Workflow

1. Scan for supported markers.
2. Read each matched file with enough context to understand
   the requested change.
3. Classify every comment as one of:
   - code change;
   - documentation/process change;
   - question to answer in chat;
   - blocked or needs user decision.
4. If the current collaboration mode allows implementation,
   make the requested change. If the current mode is Plan
   Mode, produce a decision-complete plan instead.
5. For `TODO(code-review:<id>)` markers, verify the finding
   before acting:
   - If the finding is still valid and execution is allowed,
     implement the fix and remove the marker.
   - If the finding is stale or invalid, remove it only with
     an explicit review-log note explaining why.
   - If the finding needs user input or is intentionally
     deferred, leave the marker in place and log the blocker.
6. Remove addressed inline review comments from source
   files and remove or check off addressed
   `CODE_REVIEW.gpt.md` entries. Leave unresolved comments
   only when the user needs to decide or the issue is
   intentionally deferred.
7. Produce post-lint artifacts. After editing, run the host
   repo's formatter/linter over the files you touched and
   make sure every inserted comment or code block is itself
   clean and matches the surrounding style. A marker often
   sits glued to an adjacent declaration (for example a
   `TODO(agent)` directly above a function with no blank line
   between it and the preceding `}`); when you replace such a
   marker with a permanent comment, restore the idiomatic
   separation (a blank line between top-level declarations)
   rather than inheriting the marker's cramped placement.
   Restrict formatting to the lines you changed: do not let
   the formatter rewrite unrelated lines, and leave any
   pre-existing, unrelated formatter deviation in place. A
   host wrapper names the concrete formatter command.
8. Append an entry to the review log (see Review Log)
   with:
   - date;
   - source paths;
   - marker ids and labels/comment themes;
   - decisions made;
   - actions taken;
   - validation run;
   - unresolved items.

## Mutation Discipline

When running the skill, mutation is limited to:

- implementing the requested fix or documentation/process
  change;
- removing review comments that were addressed or proven
  stale;
- appending the review-log entry (see Review Log).

Do not change unrelated code, do not remove unresolved
comments, and do not stage, commit, or push unless the user
explicitly asks for that action.

## Review Log

The operator chooses where the review log goes: a path named
when the skill is invoked, or one bound by a per-repo
wrapper. When no path is given, use
`.address-comments/review-log.md` at the root of the
repository being edited, and create that directory if it
does not exist. Do not write the log anywhere else unless
the operator names that path.

This skill does not add the default path to the
repository's ignore rules, so a log at the default path
can show up as an untracked file. An operator who wants it
kept out of version control adds `.address-comments/` to
those rules.

## Private Boundary

The review log is private operational memory. Follow the
host repo's publish/private boundary: do not publish it, do
not copy it into shareable docs, and do not summarize its
contents into shareable docs. A host wrapper may name a
different review-log path, any required publish-boundary
sentinel, and any provenance bookkeeping.

## Installing

Copy or vendor this skill's directory where your coding
agent loads skills. A thin per-repo wrapper is optional: it
can bind the review-log path, any operator-attribution
labels, the search excludes, and the private-boundary
handling, and delegate here. Do not fork the spec per repo.
