#!/usr/bin/env python3
"""Decide whether an adversarial review loop should continue.

The loop this exists for does not end on its own. Every round
returns findings, so there is never a round after which
stopping feels finished, and the yield curve that would show
the loop has gone negative is invisible unless somebody keeps
the numbers.

So keep the numbers. One record per round, eight clauses,
and a verdict that does not need judgment at the moment when
judgment is least available.

Clauses 1 to 7 are ordered by when they fired in the episode
this was derived from. The first two fire earliest and are
worth the most; they are also the two whose inputs are
easiest to leave out, so their absence is reported rather
than passed over. Clause 8 was added later, for a review
that hands its findings back instead of fixing them. On
that review's first round (no fixes, so no regressions and
nothing user-visible), clause 3 has no repair to count,
clause 4 skips a round with no fixes, clause 5 needs three
rounds and clause 6 needs two. Unless clause 1, 2 or 7
tripped, that round returned CONTINUE, and a second round
over unchanged code was needed before clause 6 could stop
the review.

Usage:

    python3 round_yield.py rounds.json
    python3 round_yield.py --explain rounds.json

The record is a JSON object with a "rounds" array, oldest
first, and an optional top-level "token_ceiling_per_high"
declared before round one.

Required per round:

    round          int   round number, for reporting
    claims         int   findings the round raised
    fixed          int   findings that became a real fix
    user_visible   int   of those, how many change what a
                         person experiences
    regressions    int   defects of any severity THIS round
                         fixed that an earlier fix in this
                         same loop introduced

Optional, and each one buys a clause:

    unbounded_domain    bool   is the fix for this round's
                               worst finding "handle one more
                               member of a set with no
                               enumeration"?           (1)
    shared_shape_ratio  0..1   share of survivors whose fixes
                               touch the same function or
                               extend the same list    (2)
    high_regressions    int    of the regressions, how many
                               were high-severity   (3, 7)
    high_fixed          int    high-severity defects fixed (7)
    introduced          int    defects THIS round's fixes were
                               later found to cause; unknown
                               until the next round
    tokens              int
    minutes             number

Exit codes: 0 continue, 1 stop, 2 the record is unusable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_CONTINUE = 0
EXIT_STOP = 1
EXIT_UNUSABLE = 2

REQUIRED_FIELDS = ("claims", "fixed", "user_visible", "regressions")
OPTIONAL_COUNTS = ("high_regressions", "high_fixed", "introduced", "tokens")

SHAPE_THRESHOLD = 0.6
NET_NEGATIVE_SHARE = 0.25

# Returned by a clause that cannot run because the record
# does not carry what it needs. Distinct from "quiet",
# because a clause nobody fed is not a clause that passed.
NOT_EVALUATED = None


class Unusable(Exception):
    """The record cannot support a verdict."""


def load_record(path):
    """Read the record, or say precisely what is wrong with it."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise Unusable("cannot read %s: %s" % (path, error))
    try:
        payload = json.loads(raw)
    except ValueError as error:
        raise Unusable("%s is not valid JSON: %s" % (path, error))
    if isinstance(payload, list):
        rounds = payload
        ceiling = 0
    elif isinstance(payload, dict):
        rounds = payload.get("rounds")
        ceiling = payload.get("token_ceiling_per_high", 0)
    else:
        raise Unusable("expected an object with a rounds array")
    if not isinstance(rounds, list) or not rounds:
        raise Unusable("no rounds recorded yet")
    for index, entry in enumerate(rounds):
        if not isinstance(entry, dict):
            raise Unusable("round %d is not an object" % index)
        for field in REQUIRED_FIELDS:
            if field not in entry:
                raise Unusable(
                    "round %s is missing %s. Every clause needs it, and "
                    "guessing it defeats the point of keeping the record."
                    % (entry.get("round", index), field)
                )
            value = entry[field]
            if not isinstance(value, int) or isinstance(value, bool):
                raise Unusable(
                    "round %s has a non-count %s"
                    % (entry.get("round", index), field)
                )
            if value < 0:
                raise Unusable(
                    "round %s has a negative %s"
                    % (entry.get("round", index), field)
                )
        for field in OPTIONAL_COUNTS:
            if field not in entry:
                continue
            value = entry[field]
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise Unusable(
                    "round %s has a non-count %s"
                    % (entry.get("round", index), field)
                )
        if "minutes" in entry:
            value = entry["minutes"]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
            ):
                raise Unusable(
                    "round %s has a non-numeric minutes"
                    % entry.get("round", index)
                )
        if "shared_shape_ratio" in entry:
            ratio = entry["shared_shape_ratio"]
            if (
                not isinstance(ratio, (int, float))
                or isinstance(ratio, bool)
                or not 0 <= ratio <= 1
            ):
                raise Unusable(
                    "round %s has a shared_shape_ratio outside 0..1"
                    % entry.get("round", index)
                )
        if "unbounded_domain" in entry and not isinstance(
            entry["unbounded_domain"], bool
        ):
            raise Unusable(
                "round %s has an unbounded_domain that is not true or false"
                % entry.get("round", index)
            )
        if entry.get("high_regressions", 0) > entry["regressions"]:
            raise Unusable(
                "round %s has more high_regressions than regressions"
                % entry.get("round", index)
            )
    if (
        not isinstance(ceiling, (int, float))
        or isinstance(ceiling, bool)
        or ceiling < 0
    ):
        raise Unusable("token_ceiling_per_high must be a non-negative number")
    return rounds, ceiling


def clause_unbounded_domain(rounds, ceiling):
    """The fix domain has no last member."""
    latest = rounds[-1]
    if "unbounded_domain" not in latest:
        return NOT_EVALUATED
    if latest["unbounded_domain"]:
        return (
            "the fix for round %s's worst finding adds one more member of a "
            "set that has no enumeration. The loop cannot reach the end of "
            "that set. Change the approach: refuse what you cannot process "
            "rather than enumerate every form of it."
            % latest.get("round", len(rounds))
        )
    return ""


def clause_one_shape(rounds, ceiling):
    """The round found one design defect, N times."""
    latest = rounds[-1]
    if "shared_shape_ratio" not in latest:
        return NOT_EVALUATED
    ratio = latest["shared_shape_ratio"]
    if ratio >= SHAPE_THRESHOLD:
        return (
            "%d%% of round %s's survivors share a root cause. That is one "
            "design defect reported many times, and fixing them one at a "
            "time guarantees the next round reports it again in a form you "
            "did not enumerate."
            % (round(ratio * 100), latest.get("round", "?"))
        )
    return ""


def clause_self_feeding(rounds, ceiling):
    """The loop is repairing its own fixes."""
    latest = rounds[-1]
    if "high_regressions" not in latest:
        return NOT_EVALUATED
    if latest["high_regressions"] > 0:
        return (
            "round %s fixed %d high-severity defect(s) that an earlier fix "
            "in this loop introduced. The loop is now reviewing itself, and "
            "every further round pays to repair the last one."
            % (latest.get("round", len(rounds)), latest["high_regressions"])
        )
    return ""


def clause_net_negative(rounds, ceiling):
    """More than a quarter of the round undid earlier rounds."""
    latest = rounds[-1]
    if latest["fixed"] == 0:
        return ""
    share = latest["regressions"] / latest["fixed"]
    if share > NET_NEGATIVE_SHARE:
        return (
            "round %s spent %d of %d fixes (%d%%) undoing earlier rounds, "
            "above the %d%% mark. Too much of this round's work was cleanup."
            % (
                latest.get("round", "?"),
                latest["regressions"],
                latest["fixed"],
                round(share * 100),
                round(NET_NEGATIVE_SHARE * 100),
            )
        )
    return ""


def clause_flat_yield(rounds, ceiling):
    """Fixed-defect yield flat or falling, twice running."""
    if len(rounds) < 3:
        return ""
    third, second, latest = rounds[-3], rounds[-2], rounds[-1]
    falling = (
        latest["fixed"] <= second["fixed"] and second["fixed"] <= third["fixed"]
    )
    if falling:
        return (
            "fixed-defect count has not risen for two rounds (%d, %d, %d). "
            "Claim counts stay high indefinitely; what you actually fixed is "
            "the yield." % (third["fixed"], second["fixed"], latest["fixed"])
        )
    return ""


def clause_nothing_visible(rounds, ceiling):
    """Two rounds running with nothing a person would notice."""
    if len(rounds) < 2:
        return ""
    recent = rounds[-2:]
    if all(entry["user_visible"] == 0 for entry in recent):
        return (
            "the last two rounds fixed nothing a person would experience "
            "(%s). Findings are not the same as defects."
            % ", ".join(
                "round %s: %d claims, %d fixed, 0 user-visible"
                % (entry.get("round", "?"), entry["claims"], entry["fixed"])
                for entry in recent
            )
        )
    return ""


def clause_budget(rounds, ceiling):
    """Cost per net-new high-severity defect past the ceiling."""
    if not ceiling:
        return NOT_EVALUATED
    needed = ("high_fixed", "high_regressions", "tokens")
    if not all(field in entry for entry in rounds for field in needed):
        return NOT_EVALUATED
    tokens = sum(entry["tokens"] for entry in rounds)
    if not tokens:
        return NOT_EVALUATED
    net_new = sum(entry["high_fixed"] for entry in rounds) - sum(
        entry["high_regressions"] for entry in rounds
    )
    if sum(entry["high_fixed"] for entry in rounds) == 0:
        return (
            "no high-severity defect has been fixed yet (%s tokens spent)."
            % format(tokens, ",")
        )
    if net_new <= 0:
        return (
            "every high-severity defect fixed so far was one this loop "
            "itself introduced (%s tokens spent, net-new high-severity "
            "defects: %d)." % (format(tokens, ","), net_new)
        )
    per_defect = tokens / net_new
    if per_defect > ceiling:
        return (
            "cost per net-new high-severity defect is %s tokens, past the "
            "%s ceiling declared at the start."
            % (format(int(per_defect), ","), format(int(ceiling), ","))
        )
    return ""


def clause_nothing_fixed(rounds, ceiling):
    """The round applied no fixes, so the code under review is unchanged."""
    latest = rounds[-1]
    if latest["fixed"] == 0:
        return (
            "round %s applied no fixes (%d claims, 0 fixed). Hand the "
            "findings back now: another round would re-read unchanged code. "
            "A later round runs only after fixes land."
            % (latest.get("round", len(rounds)), latest["claims"])
        )
    return ""


CLAUSES = (
    ("1", "unbounded fix domain", clause_unbounded_domain),
    ("2", "one design defect, reported N times", clause_one_shape),
    ("3", "a fix from an earlier round broke something", clause_self_feeding),
    ("4", "over a quarter of the round was cleanup", clause_net_negative),
    ("5", "fixed-defect yield flat or falling", clause_flat_yield),
    ("6", "two rounds with nothing user-visible", clause_nothing_visible),
    ("7", "past the declared token ceiling", clause_budget),
    ("8", "the round applied no fixes", clause_nothing_fixed),
)


def cost_report(rounds, ceiling):
    """What the loop has spent, for the person paying.

    A total is printed only when every round recorded it; a
    partial sum would understate what was spent.
    """
    tokens = 0
    tokens_recorded = all("tokens" in entry for entry in rounds)
    if tokens_recorded:
        tokens = sum(entry["tokens"] for entry in rounds)
    minutes = 0
    if all("minutes" in entry for entry in rounds):
        minutes = sum(entry["minutes"] for entry in rounds)
    visible = sum(entry["user_visible"] for entry in rounds)
    lines = [
        "rounds: %d   claims: %d   fixed: %d   user-visible: %d"
        % (
            len(rounds),
            sum(entry["claims"] for entry in rounds),
            sum(entry["fixed"] for entry in rounds),
            visible,
        )
    ]
    if tokens_recorded:
        lines.append("tokens: %s" % format(tokens, ","))
    else:
        lines.append("tokens: not recorded for every round")
    if minutes:
        lines.append("wall-clock: %g min" % minutes)
    if tokens and visible:
        lines.append(
            "cost per user-visible defect: %s tokens"
            % format(int(tokens / visible), ",")
        )
    if tokens and not visible:
        lines.append("cost per user-visible defect: undefined — none were fixed")
    return lines


def yield_curve(rounds):
    """The line an operator cannot see and you can."""
    lines = []
    for entry in rounds:
        marks = []
        if entry["regressions"] > 0:
            marks.append("%d self-inflicted" % entry["regressions"])
        if "introduced" in entry:
            marks.append("introduced %s" % entry["introduced"])
        suffix = ""
        if marks:
            suffix = "   <- " + ", ".join(marks)
        lines.append(
            "  round %-3s claims %-4d fixed %-4d user-visible %-4d%s"
            % (
                entry.get("round", "?"),
                entry["claims"],
                entry["fixed"],
                entry["user_visible"],
                suffix,
            )
        )
    return lines


def verdict(rounds, ceiling):
    """(stop, fired, unevaluated) for the recorded rounds."""
    fired = []
    unevaluated = []
    for number, summary, clause in CLAUSES:
        outcome = clause(rounds, ceiling)
        if outcome is NOT_EVALUATED:
            unevaluated.append((number, summary))
            continue
        if outcome:
            fired.append((number, outcome))
    return bool(fired), fired, unevaluated


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Decide whether an adversarial review loop continues."
    )
    parser.add_argument("record", help="JSON file of per-round counts")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="print the yield curve and every clause, fired or not",
    )
    args = parser.parse_args(argv)

    try:
        rounds, ceiling = load_record(args.record)
        stop, fired, unevaluated = verdict(rounds, ceiling)
    except Unusable as problem:
        print("unusable record: %s" % problem)
        return EXIT_UNUSABLE

    if args.explain:
        print("yield curve")
        for line in yield_curve(rounds):
            print(line)
        print()
        fired_numbers = {number for number, _ in fired}
        skipped = {number for number, _ in unevaluated}
        print("clauses")
        for number, summary, _ in CLAUSES:
            state = "quiet"
            if number in fired_numbers:
                state = "FIRED"
            if number in skipped:
                state = "-----"
            print("  %-5s clause %s: %s" % (state, number, summary))
        print()
        for line in cost_report(rounds, ceiling):
            print(line)
        print()

    if unevaluated:
        print(
            "not evaluated: clause(s) %s — the record does not carry what "
            "they need."
            % ", ".join(number for number, _ in unevaluated)
        )
        if any(number in ("1", "2") for number, _ in unevaluated):
            print(
                "  Clauses 1 and 2 fire earliest and save the most. Record "
                "unbounded_domain and shared_shape_ratio, or you are running "
                "without the two checks that would end this soonest."
            )
        print()

    if stop:
        print("STOP")
        for number, reason in fired:
            print("  clause %s: %s" % (number, reason))
        print()
        print(
            "Say this to the operator now, with the yield curve. Do not run "
            "another round first."
        )
        return EXIT_STOP

    print("CONTINUE")
    print(
        "  No clause has fired. Quote the cost of the next round before "
        "dispatching it."
    )
    return EXIT_CONTINUE


if __name__ == "__main__":
    sys.exit(main())
