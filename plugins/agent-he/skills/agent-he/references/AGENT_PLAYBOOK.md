# The agent playbook

[`METHOD.md`](METHOD.md) is the method, unchanged. This file
is everything an agent has to do differently from a human
evaluator, and it is where the value of running a heuristic
evaluation with an agent actually comes from.

The rules below are agent-specific procedure. The worked
example shipped with this repository is the fixture report
in the full clone at `evidence/findings/WORKED_EXAMPLE.md`
(F1–F4 from the deliberately bad HTML fixture; F5 from a
sample contrast palette). A skill-only install does not
include `evidence/`; clone the repository to read it.
Illustrations in this playbook are synthetic.

## 1. Two passes, cheapest first

The method already asks you to go through the UI twice. For
an agent the two passes are not the same pass repeated. They
use different instruments and they find different classes of
defect.

### Pass one: `curl`, not a browser

Most findings live in the source, not in the render. On a
typical defective page, pass one alone produces: a missing
`lang` attribute on `<html>`, zero Open Graph tags, a
double-escaped HTML entity (`&#8211;`) leaking into the page
title, a zero-byte 404 body, a 404 favicon, and a
`robots.txt` that is comments with no directives. The
shipped bad fixture demonstrates several of these.

None of that needs a browser. A browser would have made it
slower and, in the entity case, harder to see: the render
hides the source.

Fetch, at minimum:

- every distinct **page type** (index, list, detail, error,
  and any authenticated equivalents you can reach)
- `/robots.txt`
- `/sitemap.xml`
- `/favicon.ico`
- a **deliberately bad URL** (`/nobody-here/`) to see the
  real 404

`scripts/inventory.py` does this sweep and reports status,
bytes, `lang`, title, social metadata, raw-entity leakage,
alt-text gaps, media element counts and rate-limit headers
in one pass. Use `curl` directly for anything it does not
cover.

### Pass two: the live browser, for state and interaction only

Pass two exists to observe things that only exist at
runtime: focus order, hover-only affordances, filter
behaviour, media state, async transitions, empty states,
computed geometry. Do not re-derive in a browser anything
you already have from the source.

## 2. Measure, never eyeball

This is the single biggest difference between an agent
evaluation and a human one, and the place an agent is
strictly better — if it actually measures.

### Contrast is arithmetic

Compute WCAG contrast ratios numerically from the CSS custom
properties. Do not judge contrast by looking.

`scripts/contrast.py` implements the relative-luminance
formula and the thresholds:

- **4.5:1** — normal text (WCAG 1.4.3, AA)
- **3:1** — large text (≥ 18.66px bold or ≥ 24px)
- **3:1** — non-text contrast for UI component boundaries
  and graphical objects (WCAG 1.4.11)
- **7:1** — normal text at AAA

```sh
python3 scripts/contrast.py vars site.css
python3 scripts/contrast.py matrix site.css --fg ink,muted --bg bg,surface
python3 scripts/contrast.py ratio '#6b7280' '#ffffff'
```

Text pairs often pass while a control **border** fails the
3:1 that 1.4.11 asks for. No amount of looking at the page
finds that; only the arithmetic does. Run the matrix over
borders, dividers, focus rings and icon fills, not only over
text. The worked example records a 1.24:1 border pair from a
sample palette used to demonstrate that class of defect.

### Geometry comes from the page, not from a screenshot

Read `getBoundingClientRect()` inside the page. Never take a
measurement off an image.

A cropped screenshot can make a centred layout look
off-centre. Reading rectangles in JavaScript can show equal
space on both sides. Screenshots lie about scale, crop, and
device-pixel ratio, and a false finding costs more
credibility than a missed one.

Use screenshots to _illustrate_ a finding you measured.
Never to _derive_ one.

### Hit targets have a number

WCAG 2.5.8 (AA) asks for a 24×24 CSS pixel target. Measure
every interactive element and list the ones under it. Hit
targets under the 24×24 CSS-pixel floor are the shape of
real findings that are invisible to the eye.

`scripts/page_probes.js` has `hitTargets()` for this.

### Quantify everything

"41 of 55 gaps fall under 24px" is actionable. "The marks
look crowded" is not. Every finding should carry at least
one number, one quoted string, or one captured response. If
you cannot produce evidence in one of those three forms, you
have an impression, not a finding — and impressions do not
go in the report.

## 3. Test the same page type at several scales

The highest-yield trick in the whole playbook, and the one a
human evaluator almost never does because it is tedious.

Pick the smallest, the largest, and one middling instance of
each templated page type, and evaluate all three. A small,
middling, and large instance can behave three different ways
— for example a navigation rail that renders only when a
duration exists, so the largest record (no duration) has no
rail at all. Evaluating any single instance would miss that.

Sort by whatever the content axis is (item count, text
length, date range, number of collaborators) and take the
extremes. Zero and one are scales too — see §7.

## 4. Falsify the product's own promise, and make that finding #1

Read the homepage headline and lede as **testable claims**.
Then try to break them. This is the finding that matters,
and it is the one a heuristics checklist will not hand you,
because it lives under H2 (match with the real world) and
H13 (value alignment) rather than under anything about
buttons.

Copy the product's headline claims and turn them into checks
you can run over real content at volume. A promise of
"verbatim" content that fails on a measurable fraction of
items is usually severity 4 — it defeats the stated purpose
— and it belongs in the first paragraph of the report.

Reserve **severity 4** for exactly this class: a defect that
defeats the stated purpose. A slow page is a 3. A page that
does the opposite of what the product advertises is a 4.

Concretely:

1. Copy the product's own promise into your notes verbatim.
2. Turn each clause into a check you can run over real
   content at volume.
3. Report the denominator. "6 of 74 audited" is a finding;
   "some passages" is a complaint.

## 5. Instrument media and async state; never trust the control

The UI's own indicator is a claim, not an observation.

Sixty seconds after clicking play you might observe:

```
paused:        false      ← the button showed "pause"
currentTime:   0
duration:      NaN
readyState:    0          (HAVE_NOTHING)
networkState:  2          (LOADING)
buffered:      0 ranges
```

The interface asserted playback that was not happening.
Reading the element's real state is the difference between
"the player seems slow" and a severity-4 finding with a
transcript.

Read the actual properties for every stateful control:

- media — `readyState`, `networkState`, `duration`,
  `currentTime`, `paused`, `buffered.length`, `error`
- forms — `validity`, `validationMessage`, `disabled`
- fetch/XHR — the network log, not the spinner
- ARIA live regions — the text that was actually announced

`scripts/page_probes.js` has `mediaState()`.

## 6. Read the shipped JavaScript

The source tells you what is **not** wired, which is usually
invisible from the outside.

An inline script that handles only the filter and never
attaches a `play` listener means starting a second media
item may never stop the first. That is a real finding
derived from an absence.

Label anything read from code but not observed live as
**unverified**, in the finding itself. An honest
`unverified` marker costs nothing and protects every other
finding in the report.

## 7. Exercise every empty and zero state

Type a query that matches nothing into every filter, search
box and date range. Load the list with no items. Open the
detail page for the record with no children.

Filtering to zero can collapse a list to **0px** with no
empty state rendered, while other counters still report
unfiltered totals. Two findings from one keystroke.

The CSS often already contains the empty state; check
whether the class exists and is simply never reached. That
turns "add an empty state" into "render the empty state you
already wrote", which is a much cheaper fix to land.

## 8. Walk the tab order and count it

Tab from the top of the document and record every stop, in
order, with its size and accessible name.

A typical defective order is: skip link → wordmark →
breadcrumbs → dozens of near-invisible 3px links → the
page's only search box. Report the count, not the
impression.

`scripts/page_probes.js` has `tabOrder()`. It walks the DOM
in document order (with a safety cap); treat the output as a
measured list to inspect, not a fully sorted tabindex model.

## 9. Operational traps

Each of these cost real time on the first run.

- **Programmatic `.play()` is blocked by autoplay policy.**
  You need a genuine user-gesture click first. A script that
  calls `.play()` and reports failure has measured the
  browser's autoplay policy, not the product.
- **A large media fetch can hang the renderer.** A
  `Runtime.evaluate` call can time out mid-evaluation while
  a large fetch is in flight. Budget for it, and re-read the
  state in a _separate, short_ call rather than one long one
  that dies with the page.
- **Chrome automation cannot open `file://` URLs.** To
  inspect your own generated HTML output, serve it:
  `python3 -m http.server 8123 --bind 127.0.0.1` and open
  `http://127.0.0.1:8123/`.
- **Check rate-limit headers before sweeping.**
  `inventory.py` prints any `ratelimit-*` / `x-ratelimit-*`
  / `retry-after` header it sees and sleeps between requests
  by default. Space your requests. This is somebody's
  production site.
- **A cropped screenshot is not the viewport.** See §2.
- **Do not evaluate a page you have modified.** If you
  injected CSS or JavaScript to probe something, reload
  before measuring anything else.

## 10. What not to do

- Do not file a finding you cannot evidence. Delete it
  instead.
- Do not rewrite the heuristics to fit what you found. Map
  the finding to the heuristics it actually violates, and
  accept that some findings map to several.
- Do not pad the count. A short list of evidenced findings
  beats a long list padded with impressions.
- Do not report only failures. The method asks for
  compliance judgments, and the compliance section is what
  makes the failure section credible.
- Do not claim to be 3–5 evaluators. See
  [`MULTI_EVALUATOR.md`](MULTI_EVALUATOR.md) and the
  limitations section of the report template.
