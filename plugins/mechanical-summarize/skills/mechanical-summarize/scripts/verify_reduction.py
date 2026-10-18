#!/usr/bin/env python3
"""Measure and verify deletion-only, word-budgeted reductions."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


LEXICAL_TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
CASE_EXAMPLE_LIMIT = 10


def parse_retention(value: str) -> Decimal:
    """Parse one retention ratio in the interval (0, 1]."""
    try:
        retention = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError(
            "retention must be a decimal number"
        ) from error
    if not retention.is_finite():
        raise argparse.ArgumentTypeError("retention must be a finite decimal number")
    if retention <= 0 or retention > 1:
        raise argparse.ArgumentTypeError(
            "retention must be greater than 0 and at most 1"
        )
    return retention


def count_words(text: str) -> int:
    """Count whitespace-delimited words."""
    return len(text.split())


def target_word_count(source_words: int, retention: Decimal) -> int:
    """Return the preserve-first target floor."""
    raw_target = Decimal(source_words) * retention
    return math.ceil(raw_target)


def retention_suffix(retention: Decimal) -> str:
    """Render a filename marker such as .50per or .37p5per."""
    percent = retention * Decimal(100)
    value = format(percent, "f")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    value = value.replace(".", "p")
    return "." + value + "per"


def lexical_tokens(text: str) -> list[str]:
    """Return lexical tokens while excluding punctuation."""
    return [match.group(0) for match in LEXICAL_TOKEN.finditer(text)]


def match_subsequence(
    source_tokens: list[str],
    candidate_tokens: list[str],
) -> tuple[bool, int | None, int, list[dict[str, Any]]]:
    """Match candidate tokens to the earliest source subsequence."""
    source_cursor = 0
    case_change_count = 0
    case_changes: list[dict[str, Any]] = []
    for candidate_index, candidate_token in enumerate(candidate_tokens):
        candidate_key = candidate_token.casefold()
        while source_cursor < len(source_tokens):
            source_key = source_tokens[source_cursor].casefold()
            if source_key == candidate_key:
                break
            source_cursor += 1
        if source_cursor == len(source_tokens):
            return (
                False,
                candidate_index,
                case_change_count,
                case_changes,
            )
        source_token = source_tokens[source_cursor]
        if source_token != candidate_token:
            case_change_count += 1
            if len(case_changes) < CASE_EXAMPLE_LIMIT:
                case_changes.append(
                    {
                        "candidate_index": candidate_index,
                        "source_index": source_cursor,
                        "source": source_token,
                        "candidate": candidate_token,
                    }
                )
        source_cursor += 1
    return True, None, case_change_count, case_changes


def analyze_reduction(
    source_text: str,
    candidate_text: str,
    retention: Decimal,
    enforce_budget: bool,
    strict_case: bool,
) -> dict[str, Any]:
    """Analyze one source/candidate reduction pair."""
    source_words = count_words(source_text)
    candidate_words = count_words(candidate_text)
    source_tokens = lexical_tokens(source_text)
    candidate_tokens = lexical_tokens(candidate_text)
    (
        subsequence,
        missing_index,
        case_change_count,
        case_examples,
    ) = match_subsequence(source_tokens, candidate_tokens)

    issues: list[str] = []
    target_words: int | None = None
    if source_words == 0:
        issues.append("source_has_no_words")
    if candidate_words > source_words:
        issues.append("candidate_exceeds_source_word_count")
    if enforce_budget:
        target_words = target_word_count(source_words, retention)
        if candidate_words < target_words:
            issues.append("candidate_below_target_floor")
    if not subsequence:
        issues.append("candidate_is_not_an_ordered_lexical_subsequence")
    if strict_case and case_change_count > 0:
        issues.append("candidate_changes_lexical_token_case")

    retained_percent: float | None = None
    if source_words > 0:
        retained_percent = round(candidate_words / source_words * 100, 4)

    missing_token: str | None = None
    if missing_index is not None:
        missing_token = candidate_tokens[missing_index]

    return {
        "valid": not issues,
        "source_words": source_words,
        "target_words": target_words,
        "candidate_words": candidate_words,
        "retained_percent": retained_percent,
        "retention_ratio": str(retention),
        "suggested_suffix": retention_suffix(retention),
        "ordered_lexical_subsequence": subsequence,
        "missing_candidate_token_index": missing_index,
        "missing_candidate_token": missing_token,
        "case_change_count": case_change_count,
        "case_change_examples": case_examples,
        "issues": issues,
    }


def measure(source_text: str, retention: Decimal) -> dict[str, Any]:
    """Measure a source and its requested preserve-first floor."""
    source_words = count_words(source_text)
    return {
        "source_words": source_words,
        "target_words": target_word_count(source_words, retention),
        "retention_ratio": str(retention),
        "suggested_suffix": retention_suffix(retention),
    }


def print_report(report: dict[str, Any], as_json: bool) -> None:
    """Print a deterministic report."""
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    for key, value in report.items():
        if isinstance(value, list) or isinstance(value, dict):
            rendered = json.dumps(value, ensure_ascii=False)
        elif value is None:
            rendered = "none"
        else:
            rendered = str(value)
        print(key + "=" + rendered)


def read_text(path: Path) -> str:
    """Read one UTF-8 text file."""
    return path.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=("Measure or verify a deletion-only, word-budgeted reduction.")
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    measure_parser = subparsers.add_parser(
        "measure",
        help="measure a source and calculate its target floor",
    )
    measure_parser.add_argument("source", type=Path)
    measure_parser.add_argument(
        "--retain",
        type=parse_retention,
        default=Decimal("0.5"),
    )
    measure_parser.add_argument("--json", action="store_true")

    verify_parser = subparsers.add_parser(
        "verify",
        help="verify a compressed candidate against its source",
    )
    verify_parser.add_argument("source", type=Path)
    verify_parser.add_argument("candidate", type=Path)
    verify_parser.add_argument(
        "--retain",
        type=parse_retention,
        default=Decimal("0.5"),
    )
    verify_parser.add_argument("--skip-budget", action="store_true")
    verify_parser.add_argument("--strict-case", action="store_true")
    verify_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        source_text = read_text(arguments.source)
        if arguments.command == "measure":
            report = measure(source_text, arguments.retain)
            print_report(report, arguments.json)
            return 0

        candidate_text = read_text(arguments.candidate)
    except (OSError, UnicodeDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2

    enforce_budget = not arguments.skip_budget
    report = analyze_reduction(
        source_text,
        candidate_text,
        arguments.retain,
        enforce_budget,
        arguments.strict_case,
    )
    print_report(report, arguments.json)
    if report["valid"]:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
