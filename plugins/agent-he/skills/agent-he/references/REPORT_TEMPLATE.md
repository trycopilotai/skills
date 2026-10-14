# Report template

The shape below is the one that worked on the first real
run. The worked example in a full clone is
`evidence/findings/WORKED_EXAMPLE.md` (fixture evaluation).

Write the report to `FINDINGS.md` in a dated project folder.
Keep captured sources, screenshots and probe output beside
it in `evidence/`.

Sections are ordered so a reader who stops after the first
screen still gets the thing that matters.

---

## Template

````markdown
# Heuristic evaluation: <target>

**Evaluated** <date>, <time range> <tz>. **Build** <version,
commit, or build id — whatever the site exposes>. **Method**
[Heuristic evaluation, p13i.io HCI notes](https://p13i.io/posts/2022/07/intro-hci-design/#heuristic-evaluation)
— the thirteen-heuristic checklist (Nielsen's ten plus
accessibility, fairness and inclusion, and value alignment).

## The one-line verdict

<Two to four sentences. Name the one or two findings that
actually matter and say why the rest is ordinary. State it
as an interpretation — this is the one section that is
judgment rather than measurement, and it should read that
way. End with a sentence like "F1 and F2 are the report." so
the reader knows what to skip.>

---

## Scope and method

I examined the UI twice, as the method prescribes: once
reading the shipped HTML and CSS end to end, once driving
the live site in a browser and measuring the rendered
result.

<Table of every page type covered, with the exact URLs, and
the scale sample for each templated type.>

| type | URL |
| ---- | --- |
|      |     |

**Severity** uses Nielsen's standard 0–4 scale, since the
source notes call for independent severity ratings without
fixing a scale:

| Rating | Meaning                                                                |
| ------ | ---------------------------------------------------------------------- |
| 4      | Catastrophic — defeats the product's purpose; fix before anything else |
| 3      | Major — blocks or badly degrades a core task                           |
| 2      | Minor — real friction, fix when convenient                             |
| 1      | Cosmetic — fix if spare time allows                                    |

<If you ran multiple evaluators: how many, which lenses, and
how severity was reconciled. If you ran alone, say nothing
here and put it in Limitations below.>

**Honest limitation.** <Put the one-evaluator sentence here
too, where the reader is still paying attention.>

---

## What complies

The method asks evaluators to judge compliance, not just
hunt for failures.

<Bullets. Each one specific and, where possible, measured.
"Text contrast passes WCAG AA in both themes, measured, no
exceptions: 5.20:1 to 17.60:1" — not "contrast is good".
Name the heuristics that drew zero violations explicitly:
that is a positive result and it makes the failure list
credible.>

---

## Findings

Ranked by severity. Heuristic IDs follow the source list.

| #   | Severity | Finding | Heuristics violated | Evidence |
| --- | -------- | ------- | ------------------- | -------- |
| F1  | **4**    |         |                     |          |

---

### F1 — <one-line title> — severity <n>

**<heuristic name> · <heuristic name>**

<Evidence first. A quotation, a measurement, a captured
response, or a probe transcript in a fenced block. The
reader should be able to disagree with your conclusion while
accepting your evidence.>

<Why this severity — one short paragraph, and mandatory for
any 4. A 4 says the defect defeats the product's stated
purpose; make that argument explicitly.>

**Fix.** <Concrete and small enough to act on. Where the fix
has an ordering constraint or a migration cost, say so.>

<Repeat per finding, in severity order.>

---

## Heuristic coverage

Where the violations landed across all thirteen. A heuristic
with zero violations is a result, not a gap in the
evaluation — say which of the two it is.

| Heuristic                                                  | Findings | Notes |
| ---------------------------------------------------------- | -------- | ----- |
| H1 Visibility of system status                             |          |       |
| H2 Match between system and the real world                 |          |       |
| H3 User control and freedom                                |          |       |
| H4 Consistency and standards                               |          |       |
| H5 Error prevention                                        |          |       |
| H6 Recognition rather than recall                          |          |       |
| H7 Flexibility and efficiency of use                       |          |       |
| H8 Aesthetic and minimalist design                         |          |       |
| H9 Help users recognize, diagnose, and recover from errors |          |       |
| H10 Help and documentation                                 |          |       |
| H11\* Accessible                                           |          |       |
| H12\* Fairness and inclusion                               |          |       |
| H13\* Value alignment                                      |          |       |

---

## Suggested order of work

**Before anything else** — <the severity 4s, and anything
that has to ship with them to make the fix honest.>

**Then, cheap and high-value** — <the one-attribute and
one-line fixes. Group them; each is minutes of work.>

**Then, structural** — <the ones that need a design
decision.>

**When convenient** — <the rest, listed by ID only.>

---

## Limitations

- **This is one evaluator.** The method asks for 3–5
  independent evaluators precisely because no single
  evaluator finds every problem. Treat this list as a
  **floor, not a ceiling**. <Or, for a fan-out run: state
  the evaluator count and lenses, and that even 5 evaluators
  is a floor.>
- <Environment: which browser, which viewport, which OS.
  Anything you could not test — Safari, iOS, screen readers,
  authenticated flows, slow networks.>
- <Any finding marked unverified, and why.>
- <Any root cause stated as a guess, flagged as a guess. The
  usability finding usually holds regardless of cause; say
  that.>

---

## Reproducing this

```sh
<The exact commands. Pass-one curl lines, the contrast and
inventory script invocations, and a note on how the in-page
probes were run.>
```

<Where the captured sources and screenshots live.>
````

## Chat delivery

When presenting the evaluation in chat, reproduce the
complete severity-ranked findings table rather than only a
verdict or a link. Use the same five columns as the report:

| #   | Severity | Finding | Heuristics violated | Evidence |
| --- | -------- | ------- | ------------------- | -------- |

The heuristic column contains exact IDs such as `H1, H11`.
The evidence column contains one compact measurement,
quotation, or captured response; the detailed finding in the
report remains the authoritative evidence record. Follow the
table with measured compliance results, limitations, and the
report link.

---

## Notes on the shape

**Why the verdict comes first.** A severity-ranked table
buries the point when finding #1 is worth more than the
other twenty-one combined. The verdict band says which
findings are the report and gives the reader permission to
skim the rest. Mark it visually as interpretation so it is
not read as a measurement.

**Why `What complies` is not optional.** The method
explicitly asks evaluators to check for compliance and say
why — not to hunt for failures. It also does real work for
the reader: a report that says "the contrast palette is
excellent, and here is the one value that misses" is
believed. A report that lists only failures reads as a
grievance.

**Why the coverage matrix.** It shows the reader which
lenses you actually applied. An evaluation with nothing
under H12 and H13 usually means those lenses were never
picked up, not that the product is fine on them — and the
matrix makes that visible instead of hiding it.

**Why the fix goes inside each finding.** A separate
recommendations section decouples the fix from its evidence,
and the fix is the part that gets read. Keep them together.

**Why limitations are explicit.** See
[`MULTI_EVALUATOR.md`](MULTI_EVALUATOR.md). Stating that one
evaluator is a floor is the method's own reasoning; omitting
it overstates the result.
