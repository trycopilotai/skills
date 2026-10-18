---
name: mechanical-summarize
description: >-
  Create mechanical, deletion-only reductions controlled by
  raw word-count ratios while retaining the source's order,
  claims, qualifications, and voice. Use when a user asks
  for linear summarization, a `.50per` copy, a fixed
  percentage reduction, word-count-biased compression,
  deletion-only shortening, shorter prose without semantic
  rewriting, or cutting a text by half or another fraction
  without rewording it.
---

# Mechanical Summarize

Shorten prose by deleting source words, not by generating a
semantic summary. Treat the raw word count as the budget and
semantic accuracy, grammatical continuity, and voice as
constraints.

Default to 50% retention unless the user supplies another
ratio.

## Invariants

- Keep the source file unchanged.
- Retain source wording and order. Use KEEP and DELETE
  operations only.
- Add no claims, synonyms, paraphrases, transitions,
  ellipses, or reordered material.
- Preserve every distinct claim, negation, qualification,
  causal link, attribution, comparison direction, number,
  unit, named entity, result, and conclusion.
- Preserve first-person stance, register, cadence, and
  characteristic phrasing.
- Change punctuation only where a deletion creates a seam.
  Change capitalization only where retained text becomes
  sentence-initial. Do not silently normalize style.
- Stop above the numerical target when the next deletion
  would violate an invariant.

## Workflow

### 1. Fix the scope

Identify the compressible bodies and the structural
envelope. Keep headings, prompts, questions, numbering,
labels, metadata, greetings, signoffs, links, and required
template text unchanged unless the user explicitly includes
them.

For a multi-section document, treat each independent body as
a unit. Apply the retention ratio to every unit by default
so one long section does not consume the entire budget.

### 2. Name the copy

Insert the retention marker before the file extension:

- `draft.txt` becomes `draft.50per.txt`.
- `notes.md` becomes `notes.50per.md`.

For a non-integer percentage, replace the decimal point with
`p`, such as `.37p5per`.

### 3. Measure before editing

Count whitespace-delimited words. The target is a
preserve-first floor:

```text
target = ceil(original_words * retention_ratio)
```

Run the bundled verifier. `<skill-dir>` is the directory
that holds this `SKILL.md`:

```bash
python3 <skill-dir>/scripts/verify_reduction.py measure \
  <source-body> --retain 0.5
```

The verifier reads files. For a unit inside a larger
document, write the unit's body to a file in a fresh
temporary directory, such as one from `mktemp -d`, never
beside the source. Delete that directory after the report.

Record the original and target counts for every unit and in
aggregate.

### 4. Make deletion passes

Delete contiguous spans in this order:

1. filled pauses and false starts;
2. immediate repetition;
3. abandoned self-correction residue;
4. procedural asides;
5. redundant restatements;
6. secondary clauses that add no distinct proposition.

Choose cuts by their raw word savings, not by semantic
salience scoring. Re-read after every pass. Restore a span
when its removal changes meaning, reference, tone, or
grammatical continuity.

When units differ in compressibility, keep a unit above its
floor instead of deleting protected content. Use aggregate
word savings only to describe the final result; do not
over-compress another unit to compensate.

### 5. Verify mechanically

Run the verifier on each source body and compressed body,
using the same temporary directory:

```bash
python3 <skill-dir>/scripts/verify_reduction.py verify \
  <source-body> <compressed-body> --retain 0.5
```

The verifier requires the compressed lexical tokens to be an
ordered, case-insensitive subsequence of the source and
requires its whitespace-word count to stay at or above the
target floor. It reports case changes for manual review.

For an unchanged structural envelope, also verify the entire
source and copy without applying the body budget:

```bash
python3 <skill-dir>/scripts/verify_reduction.py verify \
  <source-document> <compressed-document> --skip-budget
```

Use `--strict-case` when no capitalization seam changes are
permitted. Use `--json` for machine-readable evidence.

### 6. Review semantic seams

Mechanical validation cannot prove semantic equivalence.
Inspect every deletion seam and confirm:

- negation and modality still bind to the same claim;
- attribution and pronoun references still resolve;
- comparisons retain their direction and basis;
- numbers retain their units and referents;
- causal and chronological relationships remain intact;
- no distinct evidence, result, or conclusion disappeared;
- the text still sounds like the source speaker.

Compare the structural envelope directly against the source.
For an outward-facing artifact, inspect the filename,
metadata, names, dates, links, placeholders, and signoff as
the recipient will see them.

### 7. Report the reduction

Report, per unit and in aggregate:

| Unit | Original | Target floor | Final | Retained |
| ---- | -------: | -----------: | ----: | -------: |

State any unit that remains above target and the protected
content that prevented another safe cut. Do not describe the
result as exactly 50% when the measured retention differs.

## Method basis

Read [references/method.md](references/method.md) when
changing the algorithm, adding automation, or deciding
whether an existing compression system fits this workflow.
