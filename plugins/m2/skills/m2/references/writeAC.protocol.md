# writeAC protocol

Goal: convert one free-form user request or
protocol-supplied intent bundle into structured, testable
acceptance criteria. The public `writeAC(...)` invocation
replies in chat only. Other protocols may apply this file as
a reusable acceptance criteria normalization module.

Public invocation contract
(`writeAC(requiredFreeFormInput)`):

- Required: exactly one free-form input argument.
- Accept either `writeAC(text)`, `writeAC("text")`, or
  `writeAC(text)`.
- If the argument is wrapped in one matching pair of single
  or double quotes, strip only that outer pair.
- Trim surrounding whitespace after quote stripping.
- If the remaining input is empty, reply exactly:
  `Usage: writeAC(requiredFreeFormInput).`.
- Treat the remaining input as the complete source material.
  Do not inspect repo files, run terminal commands, call
  tools, write files, stage changes, commit, push, open a
  pull request, or ask follow-up questions unless the user
  explicitly requests that extra work.

Module contract for callers:

- Another protocol may depend on this file when it already
  owns the authority to read context, write artifacts, or
  execute a larger workflow.
- The caller provides the source inputs and artifact
  destination. `writeAC` provides only the criteria-shaping
  rules, required fields, and safety constraints.
- Public `writeAC(...)` output remains chat-only. Module use
  does not grant public `writeAC(...)` permission to write
  files or mutate the repo.
- Callers must preserve source traceability. Every produced
  criterion or acceptance row must cite the plan section,
  user request, project manifest row, issue, diff, artifact,
  source file, screenshot, or other source input that
  justified it.
- If source material conflicts, is too vague, or would
  require inventing product behavior, produce a blocking
  question instead of silently choosing an answer.

Transformation rules:

1. Preserve scope.
   - Write acceptance criteria only for behavior stated or
     directly implied by the input.
   - Do not invent features, roles, data fields, validation
     rules, error states, storage behavior, analytics,
     permissions, rollout steps, or implementation details
     that are not present in the input.
   - If a missing detail is important to test the behavior,
     list it under `Open Questions` for public output or
     `blocking_questions` for module output.
   - Explicitly preserve out-of-scope behavior, removals,
     exclusions, and non-goals when the source material
     names them or when omitting them would invite unsafe
     scope expansion.

2. Make criteria atomic and observable.
   - Each criterion must describe one user-visible,
     operator-visible, or system-observable outcome.
   - Split compound requirements into separate criteria when
     they need different evidence, owners, journeys, or
     gates.
   - Prefer crisp `Given / When / Then` phrasing when it
     makes the condition and expected result clearer.
   - Use plain numbered criteria, not nested checklists.
   - Keep each criterion concise enough to paste into an
     issue, PR, plan, or run artifact.

3. Require evidence.
   - Each criterion must name the evidence that can prove
     it: command output, lint result, test, browser
     screenshot, manual click-through, trace, review
     signoff, diff inspection, fixture, schema inspection,
     API response, log entry, or an explicit blocker.
   - Evidence must be specific enough that a later reviewer
     can tell whether the criterion passed, failed, or is
     blocked.
   - Do not count intent, implementation effort, PR
     creation, queued CI, or elapsed time as evidence by
     itself.

4. Group by behavior.
   - If the input contains multiple behaviors, organize the
     numbered criteria with short behavior labels.
   - If the input describes only one behavior, use one
     numbered list without extra grouping.
   - Merge duplicate or overlapping expectations.
   - Keep ordering logical: primary success path first,
     followed by stated edge cases, failures, constraints,
     out-of-scope notes, or removals.

5. Handle ambiguity safely.
   - Do not block on ambiguity that can be represented as an
     open question or blocking question.
   - Do not convert open questions into acceptance criteria.
   - If the input is too vague to produce any testable
     criterion, reply with an `Open Questions` section or
     module blocking questions that ask for the minimum
     information needed.
   - When a caller must continue despite ambiguity, mark the
     affected row `blocked` and include owner, reason, next
     action, and whether human input is required.

M2 acceptance module contract:

- `m2()` must apply this contract during acceptance-first
  planning before it materializes an acceptance matrix.
- Inputs may include the invoked plan, project manifest,
  existing acceptance matrix rows, packet registry,
  interface contracts, relevant source files, tests, docs,
  previous run artifacts, screenshots, browser state, or
  external reference material that `m2()` is already allowed
  to inspect.
- Output rows for `m2()` must be acceptance matrix-ready and
  include:
  - acceptance id or stable placeholder id;
  - source inputs;
  - current-state summary;
  - target behavior;
  - affected user, operator, maintainer, reviewer, or
    automation journey;
  - applicable gates;
  - owning packet ids when known;
  - required evidence;
  - status;
  - blocking questions;
  - explicit out-of-scope behavior, removals, or non-goals
    when material.
- `m2()` budget-plan acceptance criteria must be derived
  from active acceptance matrix rows shaped by this module.
  Do not draft fresh ad hoc budget acceptance prose that is
  not traceable to the active acceptance matrix.
- Packet prompts, manager plans, TL reviews, verification
  rows, delivery events, handoffs, and final response gates
  should cite the same acceptance ids rather than restating
  detached criteria.

Public output contract:

- Reply in chat only. Do not write files, modify the repo,
  stage changes, commit, push, or open a pull request.
- Start with this exact heading: `Acceptance Criteria`.
- Under the heading, output numbered acceptance criteria
  with observable outcomes.
- Include evidence expectations in the criterion text when
  useful, but do not add implementation commentary.
- Include an `Open Questions` heading only when unresolved
  details are needed to make the criteria complete or
  testable.
- Keep output ASCII unless the user input requires
  preserving non-ASCII text.
- Do not include implementation notes, commentary, or a
  summary unless the user explicitly asks for them.
