# The method

Source:
[Intro to HCI design — Heuristic Evaluation](https://p13i.io/posts/2022/07/intro-hci-design/#heuristic-evaluation).

This file reproduces the method as the source states it. Do
not paraphrase it into something more convenient. The
agent-specific material lives in
[`AGENT_PLAYBOOK.md`](AGENT_PLAYBOOK.md) and is clearly
separated from the method for that reason.

## What heuristic evaluation is

> Heuristic evaluation is a 25 year old method that is
> useful in companies and startups for testing software
> products.

> Jakob Nielsen developed the Heuristic Evaluation to help
> find usability problems in a UI design. The key idea is to
> take a small set of evaluators (3-5) to examine a UI to
> independently check for compliance with usability
> principles ("heuristics"). Evaluators only communicate
> after their individual tests and aggregate them
> afterwards. Heuristics are not laws but tools to help us
> find problems. We use these violations to redesign/fix
> problems. This test can be performed on a working UI or on
> sketches.

> Good evaluators find both easy and hard problems. Every
> evaluator doesn't find every problem. These two factors
> impel us to have multiple evaluators.

The four load-bearing consequences:

1. **3–5 evaluators**, not one.
2. They work **independently**, and communicate only
   afterwards.
3. Heuristics are **tools, not laws** — a violation is an
   argument, not a verdict.
4. It works on a **live UI or on sketches**.

## The thirteen heuristics

The source frames the checklist as thirteen usability
heuristics, adapted from Nielsen's second-version list:
Nielsen's ten rules of thumb, plus accessibility, fairness
and inclusion, and value alignment as course-staff
additions. Heuristics marked with an asterisk (`*`) are
those course-staff additions.

The wording below is the source's own.

**H1: Visibility of system status.** Keep users informed
about what is going on through timely, appropriate feedback.
Loading states, progress, confirmations, selected states,
and clear consequences of actions all help users stay
oriented.

**H2: Match between system and the real world.** Speak the
users' language, with words, phrases, concepts, and
metaphors that are familiar to them rather than
system-oriented terms. Follow real-world conventions so
information appears in a natural and logical order.

**H3: User control and freedom.** Users often choose actions
by mistake. Provide clear exits, cancellation, undo, redo,
and back navigation so they can leave an unwanted state
without going through an extended dialogue.

**H4: Consistency and standards.** Users should not have to
wonder whether different words, situations, or actions mean
the same thing. Follow platform conventions and use design
systems or shared components to make consistency durable.

**H5: Error prevention.** Prevent problems before they
occur. Remove invalid choices when possible, validate input
as the user goes, use constraints and helpful defaults, and
confirm high-cost or destructive actions before users
commit.

**H6: Recognition rather than recall.** Minimize the user's
memory load by making objects, actions, and options visible.
Instructions should be visible or easily retrievable;
parsing or previewing input as the user types can help
people recognize valid choices rather than remember formats.

**H7: Flexibility and efficiency of use.** Support both
novice and expert users. Accelerators, shortcuts, defaults,
templates, search, customization, and saved frequent actions
can speed up expert workflows while leaving simple paths for
new users.

**H8: Aesthetic and minimalist design.** Dialogues should
not contain information that is irrelevant or rarely needed.
Every extra unit competes with the relevant units of
information and diminishes their relative visibility, so
hierarchy, spacing, and copy should serve the current task.

**H9: Help users recognize, diagnose, and recover from
errors.** Error messages should be plain language, polite,
highly noticeable, precise about the problem, and
constructive: describe what happened, explain the recovery
path, or offer to fix the issue for the user.

**H10: Help and documentation.** It is better if the system
can be used without documentation, but help may still be
necessary. Any such information should be easy to search,
focused on the user's task, concrete about the steps to
take, and not too large.

**H11\*: Accessible.** Users can interact with the system
using alternative input methods and assistive technologies.
Content should be legible with distinguishable contrast and
text size. Key information should be upfront and not nested
for screen readers. Purely visual or auditory content should
have text-based alternatives for users with low vision and
low hearing.

**H12\*: Fairness and inclusion.** Users should not feel
that the design was not made for them. The design should
meet users' needs equitably, prevent the reproduction of
pre-existing inequities, and avoid creating additional
burdens for members of disadvantaged populations.

**H13\*: Value alignment.** The design should encode values
that users can understand and relate to. Conflicting
collateral values should not emerge when the user interacts
with the product. Encoded values should match users' values
across a broad set of use contexts.

> \* Heuristics marked with an asterisk (\*) are custom
> additions by the course staff to reflect new values that
> are important to making accessible and socially-conscious
> products.

## Example violations, from the source

These are the source's own worked examples of what a
violation looks like when it is written down. Note how short
each one is, and that each carries a heuristic ID.

- Inconsistent colors for text (red vs. black) — H4
- Inconsistent or extra spacing — H4
- Price vs. total doesn't make sense — H2
- "h" value is accepted into the input — H5
- Yes and no are both checkboxes — H5
- Inconsistent highlighting of table rows — H4
- Black on blue text — H11
- Red font means different things — H4

## The process, as the source summarizes it

> - Have evaluators go through the UI twice
> - Ask them to see if it complies with the heuristics, not
>   where it doesn't and say why
> - Have evaluators independently rate severity
> - Combine the findings from 3-5 evaluators, come to
>   agreement

Read the second bullet carefully. The instruction is to
check for **compliance** and to say **why**, not to go
hunting for failures. A report that lists only violations
has not run the method. See the `What complies` section in
[`REPORT_TEMPLATE.md`](REPORT_TEMPLATE.md).

## Severity

**The source does not fix a severity scale.** It asks only
that evaluators rate severity independently.

This skill adopts Nielsen's standard 0–4 scale as its
convention, and every report must say so rather than
implying the scale came from the source:

| Rating | Meaning                                                            |
| ------ | ------------------------------------------------------------------ |
| 0      | Not a usability problem at all                                     |
| 1      | Cosmetic problem only — fix if spare time allows                   |
| 2      | Minor usability problem — low priority                             |
| 3      | Major usability problem — important to fix, high priority          |
| 4      | Usability catastrophe — imperative to fix before the product ships |

Reserve **4** for a defect that defeats the product's stated
purpose, not one that merely annoys. See
`Falsify the product's own promise` in
[`AGENT_PLAYBOOK.md`](AGENT_PLAYBOOK.md).
