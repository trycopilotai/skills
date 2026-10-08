# Log Entry Template

Use this shape for the entries appended to `HANDOFF.log.md`.
Prefer compact but complete entries. Do not duplicate the full
snapshot.

```markdown
## YYYY-MM-DD HH:MM TZ - short title

- **Trigger:** User request, resume, validation, commit,
  blocker, parallel patch attempt, review-comment pass,
  deploy, or handoff.
- **Phase:** plan, edit, validate, commit, blocked, deploy, or
  handoff.
- **Objective:** The active objective in one sentence.
- **State change:** What changed since the prior entry.
- **Files changed:** Important files or directories.
- **Commits / pushes:** Commit SHAs, repos, and remotes, or
  "none".
- **Validation:** Commands run and results.
- **Dirty state:** Remaining dirty files and whether they are
  expected.
- **Blockers:** Anything that prevents progress.
- **Next action:** Exact next action for a resumed agent.
```

Append entries in chronological order. Do not rewrite prior
entries except for typo fixes or explicit user-requested
corrections.
