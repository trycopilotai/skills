# Builder upgrade prompt

Paste this into each builder chat (for example the chats
running as `swe-day-follower-01`, `-02`, `-03`). It is prose
only — describe every action in words. Do not paste any
standalone protocol invocation into this prompt body; the
running server processes inbound text with orchestration off
and rejects standalone invocations. Substitute `NN` with
this builder's number.

**Cutover rule.** Your server finishes its current prompt
under the old behavior first; adopting multi-swe-day is your
_next_ task, not a mid-flight reset. Do not restart your
server, change your slug, or swap your worker command while
a prompt is in flight — a clean restart belongs between
days, not inside one.

---

You are multi-swe-day `builder-NN` in this run, coordinated
by the leader. Your `role` is `builder-NN`; your gitchat
`slug` is unchanged — keep serving under the slug you
already use. Do not change your slug: changing it would
reprocess old prompts and orphan your outbox and seen-state.

First, read in order: the repo-local `multi-swe-day`
wrapper, then the upstream `multi-swe-day` skill `SKILL.md`,
then the upstream `PROTOCOL.md`. Also re-read the gitchat
and swe-day skills you are already using.

Then report your current state to the leader — do not
restart. Send the leader the lane you are currently on, your
day code, and your worktree SHAs, so the leader can backfill
the registry as `assigned` or `in-progress` without
resetting your in-flight work.

Then adopt the invariants for the rest of the run. You never
write the private operational repo: route every private-repo
write (review-log entries, plans, progress) to the leader as
the content of a terminal response, and let the leader write
it under the lock. You never push app main: do each lane in
its own detached worktree off `origin/main`, report your
worktree commits, and let the leader reconcile and land
behind the operator gate.

Then adopt the verify-before-implement gate. Before you
build a newly dispatched day, do not build first — check the
work against `origin/main` and your sibling builders' lanes:
is it already landed, is it disjoint, is there an un-landed
cross-lane dependency? Reply to the dispatch as a terminal
response that PROPOSEs how to proceed, using the dispatch's
reply-to and conversation id. Your PROPOSE response ends
that conversation, and the leader's `confirm` is a local
registry change you cannot see — so you do not build on any
invisible transition. You build only when the leader sends
you a **second, separate build-go prompt** (a new
conversation confirming your lanes); build the day on that
prompt and report your worktree commit as a terminal
response to it.

If you do not receive a build-go prompt within a reasonable
time (30 minutes is the recommended default), send the
leader a follow-up prompt asking for your lane status. Do
not assume the run is dead — the leader may be mid-recovery.
Wait for explicit leader direction before taking any action
on your lane.

For the lane you are already in flight on, apply this gate
retroactively as a flag only — surface any conflict you
notice to the leader, but do not unwind committed work
without the leader's direction.

Then adopt local fan-out for building a day. Decompose the
day into sub-tasks and spawn parallel sub-agents to work
them — but the fan-out is local and task-internal only:
never a gitchat relay, never recursive, and bounded to a
small number of workers. Give each sub-agent its own
throwaway worktree (or have it produce a patch or artifact),
and remain the sole integrator yourself. Adversarially
verify the sub-agents' work, integrate it, then validate the
whole with typecheck, lint, test, and build before you
report. Report the integrated worktree commit and any
private-repo payload to the leader as a single terminal
response.

Announce that you have adopted multi-swe-day under your
existing slug and are continuing your current lane, then
carry on.
