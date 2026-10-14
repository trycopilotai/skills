---
name: agent-he
description: >-
  Run a heuristic evaluation (HE) on a UI against the
  thirteen-heuristic CS147 checklist — Nielsen's ten plus
  accessibility, fairness and inclusion, and value alignment
  — and produce a severity-ranked findings report with
  measured evidence. Use when asked for a heuristic
  evaluation, a usability review, a UX audit, an
  accessibility and usability pass over a site or app, or a
  Nielsen-heuristics review of a live UI, a prototype, or
  sketches.
---

# agent-he

Heuristic evaluation, run by an agent, on a real UI.

The method is Nielsen's and it is not yours to improve. It
is reproduced unchanged in
[`references/METHOD.md`](references/METHOD.md). What this
skill adds is everything an agent has to do _differently_ —
measure instead of look, sweep the source before the render,
sample the same page type at several scales, and attack the
product's own promise — which is in
[`references/AGENT_PLAYBOOK.md`](references/AGENT_PLAYBOOK.md).

`$HE` below is the directory holding this `SKILL.md`. Set it
once so every command works from any directory:

```bash
HE=<directory holding this SKILL.md>
```

## Read first

| File                                                             | What it is                                                                                |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| [`references/METHOD.md`](references/METHOD.md)                   | The method and the thirteen heuristics, verbatim from the source. Never paraphrase these. |
| [`references/AGENT_PLAYBOOK.md`](references/AGENT_PLAYBOOK.md)   | The ten agent-specific rules. This is where the value is.                                 |
| [`references/MULTI_EVALUATOR.md`](references/MULTI_EVALUATOR.md) | How to run the 3–5 evaluators the method actually asks for.                               |
| [`references/REPORT_TEMPLATE.md`](references/REPORT_TEMPLATE.md) | The output shape, and why each section is there.                                          |

The worked example for this release is the fixture report in
a full repository clone at
`evidence/findings/WORKED_EXAMPLE.md` (F1–F4 from
`tests/fixtures/bad.html`; F5 from
`evidence/inventory/sample.css`). A skill-only install does
not copy `evidence/`; clone the repository if you need the
report. The report is the shape to aim at, not a live-site
benchmark.

## The one thing to decide before you start

**Are you one evaluator or several?**

The method asks for 3–5 independent evaluators, because no
single evaluator finds every problem. A single agent cannot
satisfy that. Several agents can — and better than humans
can, because the fan-out costs minutes rather than a week.

Read
[`references/MULTI_EVALUATOR.md`](references/MULTI_EVALUATOR.md)
and decide. **You must be explicitly authorized to spawn
subagents.** If you are not, run alone and say so in the
limitations section. Running alone is a legitimate result;
claiming to be five evaluators is not.

## Workflow

### 0. Fix the scope

Write down, before fetching anything:

- the target, and whether it is a live UI, a prototype, or
  sketches (all three are in scope for the method);
- every distinct **page type**;
- for each templated type, a **scale sample** — the
  smallest, the largest, and one middling instance. This is
  the highest-yield step in the whole procedure and it is
  step zero for a reason. See playbook §3.
- the product's **own promise**, copied verbatim from its
  homepage headline and lede. You are going to try to
  falsify it. See playbook §4.

### 1. Pass one — the source, without a browser

```bash
python3 "$HE/scripts/inventory.py" \
  https://example.com/ \
  https://example.com/some/detail/page/ \
  --extras
```

`--extras` adds `/robots.txt`, `/sitemap.xml`,
`/favicon.ico` and a deliberately bad URL. The sweep reports
status and bytes, `lang`, title, Open Graph and Twitter-card
metadata, favicon links, raw-entity leakage in titles and
body text, missing `alt`, heading outline, element counts,
inline-script size, and any rate-limit headers.

**Check the rate-limit headers before you widen the sweep.**
The script sleeps 1s between requests by default. This is
somebody's production site.

Then the contrast arithmetic, from the shipped CSS:

```bash
curl -s https://example.com/style.css > /tmp/site.css
python3 "$HE/scripts/contrast.py" vars /tmp/site.css
python3 "$HE/scripts/contrast.py" matrix /tmp/site.css --min 4.5
```

`--min 4.5` prints only the pairs that fail AA for normal
text. Run it again with `--min 3.0` over borders, dividers,
focus rings and icon fills — WCAG 1.4.11 asks 3:1 for a UI
component's boundary, and that is where the real finding
usually is.

Read the shipped JavaScript in this pass too. It tells you
what is _not_ wired, which the render cannot. See playbook
§6.

### 2. Pass two — the live browser, for state and interaction

Load `scripts/page_probes.js` into the page once, then call
the probes:

```javascript
agentHE.viewport(); // the real viewport, not the screenshot's
agentHE.hitTargets(); // everything under 24x24 (WCAG 2.5.8)
agentHE.tabOrder(); // document-order stops (capped); inspect sizes
agentHE.mediaState(); // readyState / networkState / duration
agentHE.centering("main"); // settles an off-centre suspicion
agentHE.spacing(".rail .mark");
agentHE.emptyState(".list"); // run before and after a no-match query
agentHE.headings(); // the outline, for skipped levels
agentHE.links(); // internal vs external
```

In this pass, and only in this pass:

- exercise **every empty and zero state** — playbook §7;
- walk the **tab order** and count it — playbook §8;
- **instrument media and async state** rather than trusting
  the control — playbook §5;
- take **every geometry number from the page**, never from a
  screenshot — playbook §2.

Screenshots illustrate a finding you measured. They never
derive one.

### 3. Judge compliance, not only failure

The method's own summary says to check whether the UI
**complies** with the heuristics and to say why — not to
hunt for failures. Walk all thirteen. Record which ones drew
**zero** violations; that is a result, and it is what makes
the failure list believable.

### 4. Rate severity independently

Use Nielsen's 0–4 scale, and label it as this skill's
convention rather than the source's — the source calls for
independent severity ratings without fixing a scale.

| Rating | Meaning                                             |
| ------ | --------------------------------------------------- |
| 4      | Catastrophic — defeats the product's stated purpose |
| 3      | Major — blocks or badly degrades a core task        |
| 2      | Minor — real friction                               |
| 1      | Cosmetic                                            |
| 0      | Not a usability problem                             |

**A 4 needs a purpose argument**, written into the finding.
"Annoying" is never a 4.

### 5. Write the report

Follow
[`references/REPORT_TEMPLATE.md`](references/REPORT_TEMPLATE.md).
Write `FINDINGS.md` into a dated project folder and keep
captured sources, probe output and screenshots beside it in
`evidence/`.

### 6. Present the findings

When the result is delivered in chat, follow the
`Chat delivery` section of
[`references/REPORT_TEMPLATE.md`](references/REPORT_TEMPLATE.md).
The chat response includes the complete findings table with
exact heuristic IDs, not only a verdict or report link.

## Invariants

These hold whether you run alone or with five evaluators.

- **The heuristics are quoted, not rewritten.** Their
  numbering, their asterisks and their wording come from
  `METHOD.md`.
- **Every finding carries evidence** — a measurement, a
  quotation, or a captured response. No evidence, no
  finding; delete it rather than softening it.
- **Nothing is measured from a screenshot.** Geometry comes
  from `getBoundingClientRect()`, contrast from the
  arithmetic.
- **Anything read from code but not observed live is marked
  `unverified`**, in the finding itself.
- **The report says how many evaluators ran.** One evaluator
  is a floor, not a ceiling, and the report says that in
  those terms.
- **The severity scale is attributed to Nielsen, not to the
  source post.**
- **The compliance section is not optional.**

## Scope

Standard library, `curl`, and whatever browser automation
the host offers. No package installs, no services, no
network dependencies beyond the target itself.

The scripts are:

| Script                   | Runs where | Does                                                                          |
| ------------------------ | ---------- | ----------------------------------------------------------------------------- |
| `scripts/inventory.py`   | your shell | pass-one sweep of every page type plus robots, sitemap, favicon and a bad URL |
| `scripts/contrast.py`    | your shell | WCAG contrast ratios from CSS custom properties                               |
| `scripts/page_probes.js` | the page   | viewport, hit targets, tab order, media state, spacing, empty states          |

Run `make check` in the repo root to compile the scripts and
run their tests.
