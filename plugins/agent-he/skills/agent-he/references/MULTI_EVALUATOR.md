# Running 3–5 evaluators

The method's requirement of 3–5 independent evaluators is
the one part a single agent structurally **cannot** satisfy.
It is also the part an agent can satisfy _better_ than a
team of humans, because dispatching five evaluators costs
minutes rather than a week of calendar time.

Read this before deciding to run alone.

## Why the method insists on it

From [`METHOD.md`](METHOD.md):

> Good evaluators find both easy and hard problems. Every
> evaluator doesn't find every problem. These two factors
> impel us to have multiple evaluators.

And:

> Evaluators only communicate after their individual tests
> and aggregate them afterwards.

Independence is not a formality. It is the mechanism. Two
evaluators who talk during the pass converge, and a
converged pair finds roughly what one finds. The value comes
from the union of genuinely separate readings.

## When it is worth the cost

Run the multi-evaluator protocol when:

- the UI is going in front of real users, or is already
  live;
- the surface is large enough that one agent's context will
  not hold every page type at every scale;
- the product makes a **claim** worth attacking (§4 of the
  playbook), which deserves an evaluator of its own;
- the result will be used to prioritise engineering work,
  where a missed severity-4 is expensive.

Run alone when:

- the surface is a single screen or a sketch;
- you are doing a fast pre-review before a real evaluation;
- the parent agent is **not authorized to spawn subagents**
  — which is the common case, and is not a defect. Run
  alone, and say so in the limitations section.

**The parent agent must be explicitly authorized to spawn
subagents.** Do not fan out on your own initiative. If you
believe fanning out is warranted and you lack authorization,
say so and let the human decide.

## The five lenses

Assign each evaluator a genuinely different lens. Different
lenses, not different pages — overlapping coverage with
different priors is the point.

| #   | Lens                            | Reads for                                                                                             | Heuristics it leads with |
| --- | ------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------ |
| 1   | **Accessibility**               | contrast arithmetic, `lang`, headings, ARIA, focus order, hit targets, reduced motion, alt text       | H11, H6, H4              |
| 2   | **Information architecture**    | navigation, URL shape, breadcrumbs, findability, search, page-type consistency, scale behaviour       | H2, H4, H7               |
| 3   | **Error paths and edge states** | 404s, empty results, zero and one and very-many, offline, slow media, invalid input, stale links      | H1, H3, H5, H9           |
| 4   | **Content correctness**         | does the copy say true things; entity leakage, numbers, attribution, the product's own promise        | H2, H13, H12             |
| 5   | **First-time visitor**          | can a stranger understand what this is, choose a path, and recover; help, about, coverage, onboarding | H10, H6, H8              |

Three evaluators: take lenses 1, 3, and 4. Content
correctness is the lens that attacks the product's own
promise (§4 of the playbook); never drop it.

## The protocol

### 1. Brief each evaluator identically, except for the lens

Every evaluator gets: the target, the page inventory (so
they cover the same surface), this skill, the 0–4 severity
scale, and their lens. Nothing else.

Do **not** give an evaluator another evaluator's findings, a
running total, or a hint about what has already been found.
Blindness is the whole design.

### 2. Fix the scale sample up front

The parent picks the page instances (§3 of the playbook —
smallest, largest, middling of each type) and hands the same
list to every evaluator. Otherwise you cannot tell a
disagreement about severity from a disagreement about which
page they looked at.

### 3. Require the same output shape from each

Each evaluator returns findings only, in the per-finding
block of [`REPORT_TEMPLATE.md`](REPORT_TEMPLATE.md):
evidence, heuristics, independent severity, fix. Plus its
own `What complies` list — compliance judgments merge too,
and a heuristic that three independent evaluators found no
violation of is a much stronger statement than one evaluator
saying so.

### 4. Aggregate, then reconcile

The parent does this. It is real work, not concatenation.

**Merge.** Two findings are the same finding when they name
the same defect in the same element, even when they came in
under different heuristics. Keep the union of the
heuristics, the union of the evidence, and the clearest
statement of the fix.

**Count independent discovery.** Record how many evaluators
found each merged finding. That number is signal: it belongs
in the report, and it is one of the few things a
multi-evaluator run can report that a single one cannot.

**Reconcile severity.** The evaluators rated independently,
so the ratings will differ. Resolve them by this order:

1. **Evidence beats opinion.** If one evaluator measured and
   another estimated, take the measured rating.
2. **Take the maximum when the disagreement is about
   reach.** An evaluator who found the defect on the largest
   page and rated it 3 saw a case the evaluator who rated it
   1 did not. Take the 3 and cite the instance.
3. **Take the median when the disagreement is about
   judgment** — same evidence, different weighting — and say
   in the finding that ratings ranged, with the range.
4. **A 4 needs a purpose argument, not a vote.** Do not
   promote to 4 because two evaluators said 4. Promote only
   when the finding defeats the product's stated purpose (§4
   of the playbook). A single evaluator who makes that
   argument with evidence outranks three who did not.
5. **Never average.** An averaged 2.33 hides the fact that
   two evaluators disagreed about something real. Pick a
   number and record the spread.

**Record what did not reconcile.** If two evaluators reached
incompatible conclusions about the same element — one says
it works, one says it does not — that is a finding in
itself, and usually means the behaviour is
instance-dependent or timing-dependent. Go look again rather
than picking a side.

### 5. Report the protocol you ran

The report says how many evaluators, with which lenses, and
how severity was reconciled. Without it a reader cannot tell
a five-evaluator union from one agent's list.

## Cost control

- Five evaluators over four page types is the usual ceiling
  for a site of a few dozen pages.
- Do the `curl` pass **once**, in the parent, and hand the
  captured sources to every evaluator. Re-fetching five
  times is wasteful and can trip rate limits (§9 of the
  playbook).
- Browser work does not parallelise well when there is one
  browser. Either serialise pass two, or give the
  interaction-heavy lenses (1, 3, 5) the browser budget and
  let lenses 2 and 4 work from captured source.

## If you ran alone

Say so, plainly, in the limitations section:

> This is **one** evaluator. The method asks for 3–5,
> precisely because no single evaluator finds every problem.
> Treat this list as a floor, not a ceiling.

That sentence is not boilerplate. It is the method's own
reasoning, and omitting it overstates the result.
