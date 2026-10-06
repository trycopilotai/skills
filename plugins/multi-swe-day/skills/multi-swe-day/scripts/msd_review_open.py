#!/usr/bin/env python3
"""msd_review_open — build and open the human-review-gate review surface.

When a multi-swe-day run parks at the `human-review` gate, the operator
must read the held diffs before reconcile is unblocked. This helper turns
a `base..head` range over a repo into a reviewable surface and opens it
in VS Code with the checklist on the LEFT and the per-file diffs on the
RIGHT:

  1. Resolve the changed files for ``<base>..<head>`` in ``--repo``.
  2. Write ONE ``<flattened-path>.diff`` per changed file into a fresh
     temp review directory (one tab per file — never a single combined
     diff, never a newline-joined variable passed to one ``open``).
  3. Generate ``CHECKLIST.md`` — one review item per changed file plus a
     verdict section the operator fills in.
  4. Drop a sentinel pair (``publish.manifest`` + ``PROVENANCE.schema.json``)
     and a ``.vscode/settings.json`` into the diff directory so the
     companion VS Code review extension (not included) activates
     there. The temp dir is not a workspace it activates in on its own, so
     the sentinels are what make Cmd+Opt+A fire on the diff tabs, which
     feeds the address-comments ``.diff`` mode. ``files.exclude`` hides
     the sentinels and ``.vscode`` so the operator sees only diffs +
     checklist.
  5. Open VS Code: the checklist window (its own folder) on the left
     half of the screen, the diff FOLDER window on the right half, using
     ``osascript`` to set window bounds. If accessibility automation is
     blocked, fall back to simply opening both — no positioning.

VS Code is always launched with ``open -a "Visual Studio Code"`` — never
the ``code`` CLI shim, which is frequently not on PATH.

Usage:
  msd_review_open.py --repo <path> --range <base>..<head> [options]
  msd_review_open.py --repo <path> --base <base> --head <head> [options]

Options:
  --review-dir <path>   Use this dir instead of a fresh mkdtemp one.
  --skip-glob <glob>    Repeatable. Skip changed paths matching this glob
                        (e.g. 'drizzle/meta/*'); huge generated snapshots.
  --no-open             Build the surface but do not launch VS Code.
  --no-position         Open both windows but skip osascript positioning.
  --self-test           Run the embedded unit tests and exit.

Limits: paths are taken from ``git diff --name-only`` as git prints
them, so a path git quotes (non-ASCII bytes, quotes, control characters)
gets an empty ``.diff``; a rename is listed under its new path only;
leading and trailing whitespace of each diff is stripped; ``a...b`` is
diffed as ``a..b``; and a reused ``--review-dir`` keeps earlier ``.diff``
files, which are opened with the new ones. Each name is passed back to
git as a pathspec, so a name with glob characters can pull in other
files, and a ``--repo`` that is a subdirectory of the work tree gets
empty or wrong diffs: pass the top level. When every changed file is skipped the checklist
says no file changed. A malformed range or a failing git command ends
in a traceback. Window positioning moves the first two VS Code windows
it finds and does not check which they are.

Pure stdlib; no third-party deps.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


VSCODE_APP = "Visual Studio Code"

# The sentinel pair a companion review extension looks for
# (publish.manifest + PROVENANCE.schema.json). Dropping both into the
# diff folder makes that extension activate there.
SENTINEL_MANIFEST = "publish.manifest"
SENTINEL_SCHEMA = "PROVENANCE.schema.json"


# A short banner written into the sentinel files so they are obviously
# placeholders for the review surface and never mistaken for real ones.
SENTINEL_NOTE = (
    "# Review-surface sentinel — placeholder so the\n"
    "# companion review extension activates\n"
    "# Cmd+Opt+A on the .diff tabs. Not a real publish manifest.\n"
)


# ---------------------------------------------------------------------------
# Range / git plumbing
# ---------------------------------------------------------------------------


# Split a "<base>..<head>" string into its two endpoints, tolerating the
# "..." form. Returns (base, head); raises ValueError on a malformed range.
def parse_range(range_str: str) -> tuple[str, str]:
    match = re.match(r"^(.+?)\.\.\.?(.+)$", range_str)
    if not match:
        raise ValueError(
            f"range must be '<base>..<head>', got {range_str!r}"
        )
    return match.group(1), match.group(2)


# Run a git command in the repo and return stripped stdout. Raises
# CalledProcessError (stderr is captured, not printed) on a non-zero exit.
def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# List the repo-relative paths changed between base and head. Uses
# name-only diff so renames/copies surface as their head-side path.
def changed_files(repo: Path, base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", f"{base}..{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    # Split on newlines only and keep every non-empty line, unstripped: a
    # name may be, start with, or end with whitespace.
    files = [line for line in result.stdout.split("\n") if line]
    return files


# Flatten a repo-relative path into a single safe filename by replacing
# path separators with '-', then append '.diff'. Keeps the original
# extension visible (e.g. 'src/a/b.ts' -> 'src-a-b.ts.diff') so the
# companion extension can pick the right comment leader.
def diff_filename_for(rel_path: str) -> str:
    flattened = rel_path.replace(os.sep, "-").replace("/", "-")
    return f"{flattened}.diff"


# True when rel_path matches any of the skip globs.
def should_skip(rel_path: str, skip_globs: list[str]) -> bool:
    for glob in skip_globs:
        if fnmatch.fnmatch(rel_path, glob):
            return True
    return False


# ---------------------------------------------------------------------------
# Surface construction
# ---------------------------------------------------------------------------


# Write one .diff file per changed (non-skipped) file into diff_dir.
# Returns (written, skipped) lists of repo-relative paths. A file that
# produces an empty diff (e.g. mode-only) is still written so its tab and
# checklist item exist.
def write_per_file_diffs(
    repo: Path,
    base: str,
    head: str,
    files: list[str],
    diff_dir: Path,
    skip_globs: list[str],
) -> tuple[list[str], list[str]]:
    written: list[str] = []
    skipped: list[str] = []
    for rel_path in files:
        if should_skip(rel_path, skip_globs):
            skipped.append(rel_path)
            continue
        diff_text = git(
            repo, "diff", f"{base}..{head}", "--", rel_path
        )
        out_path = diff_dir / diff_filename_for(rel_path)
        out_path.write_text(diff_text + "\n", encoding="utf-8")
        written.append(rel_path)
    return written, skipped


# Render the CHECKLIST.md body: a header, one unchecked item per changed
# file (naming its .diff tab), a skipped section, and a verdict section
# the operator fills in. This is the LEFT pane of the review surface.
def render_checklist(
    repo: Path,
    base: str,
    head: str,
    written: list[str],
    skipped: list[str],
    diff_dir: Path,
) -> str:
    lines: list[str] = []
    lines.append("# Human-review gate — change review")
    lines.append("")
    lines.append(f"- Repo: `{repo}`")
    lines.append(f"- Range: `{base}..{head}`")
    lines.append(f"- Diffs: `{diff_dir}`")
    lines.append("")
    lines.append(
        "Read each `.diff` tab on the right. With the companion review "
        "extension installed (it is not bundled), on a changed line, "
        "Cmd+Opt+A drops a `TODO(agent):` review comment that the "
        "address-comments `.diff` mode then consumes. Check an item "
        "once you have reviewed that file."
    )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    if not written:
        lines.append("_No changed files in range._")
    for rel_path in written:
        diff_name = diff_filename_for(rel_path)
        lines.append(f"- [ ] `{rel_path}` — `{diff_name}`")
    lines.append("")
    if skipped:
        lines.append("## Skipped (not opened)")
        lines.append("")
        for rel_path in skipped:
            lines.append(f"- `{rel_path}`")
        lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append("- [ ] Reviewed every diff above")
    lines.append("- [ ] No blocking concerns")
    lines.append(
        "- Decision: _approve_ / _request changes_ / _abort_ "
        "(operator fills in)"
    )
    lines.append("")
    lines.append("Notes:")
    lines.append("")
    lines.append("> ")
    lines.append("")
    return "\n".join(lines)


# Drop the sentinel pair and a .vscode/settings.json into diff_dir so the
# companion extension activates there and the operator does not
# see the sentinels or the .vscode dir in the file tree.
def write_extension_scoping(diff_dir: Path) -> None:
    (diff_dir / SENTINEL_MANIFEST).write_text(
        SENTINEL_NOTE, encoding="utf-8"
    )
    (diff_dir / SENTINEL_SCHEMA).write_text(
        '{\n  "_note": "review-surface sentinel placeholder"\n}\n',
        encoding="utf-8",
    )
    vscode_dir = diff_dir / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    settings = (
        "{\n"
        '  "files.exclude": {\n'
        f'    "{SENTINEL_MANIFEST}": true,\n'
        f'    "{SENTINEL_SCHEMA}": true,\n'
        '    ".vscode": true\n'
        "  }\n"
        "}\n"
    )
    (vscode_dir / "settings.json").write_text(
        settings, encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Opening VS Code
# ---------------------------------------------------------------------------


# Open a folder in VS Code via `open -a` (never the `code` shim). Each
# .diff path is passed as its own argument so VS Code opens one tab per
# file — the glob is expanded HERE in Python, not by joining a newline
# string and handing it to one open (the historical bug).
def open_diff_window(diff_dir: Path, diff_paths: list[Path]) -> None:
    args = ["open", "-a", VSCODE_APP, str(diff_dir)]
    for path in diff_paths:
        args.append(str(path))
    subprocess.run(args, check=True)


# Open the checklist in its own VS Code window. The checklist lives in its
# own folder so it becomes a separate window we can position independently
# of the diff window.
def open_checklist_window(checklist_dir: Path, checklist_path: Path) -> None:
    subprocess.run(
        [
            "open",
            "-a",
            VSCODE_APP,
            "-n",
            str(checklist_dir),
            str(checklist_path),
        ],
        check=True,
    )


# Best-effort: position the two front VS Code windows side by side — the
# checklist on the left half, the diffs on the right half — using
# osascript window bounds. Returns True on success; False (and a stderr
# note) when accessibility automation is blocked, so the caller can leave
# the windows wherever they opened.
def position_windows_side_by_side() -> bool:
    script = r'''
tell application "Finder"
  set screenBounds to bounds of window of desktop
end tell
set screenW to item 3 of screenBounds
set screenH to item 4 of screenBounds
set halfW to screenW / 2
tell application "System Events"
  tell process "Code"
    set theWindows to windows
    if (count of theWindows) < 1 then return "no-windows"
    set position of window 1 to {halfW as integer, 0}
    set size of window 1 to {(screenW - halfW) as integer, screenH as integer}
    if (count of theWindows) >= 2 then
      set position of window 2 to {0, 0}
      set size of window 2 to {halfW as integer, screenH as integer}
    end if
  end tell
end tell
return "ok"
'''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(
            "msd_review_open: window positioning skipped "
            f"(accessibility/automation blocked): {result.stderr.strip()}\n"
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


# Build the review surface and (unless --no-open) open it. Returns the
# review directory path so the caller can report it.
def build_and_open(args: argparse.Namespace) -> Path:
    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        # Allow worktrees, which have a .git FILE, and plain repos.
        if not git_dir_exists(repo):
            raise SystemExit(f"not a git repo: {repo}")

    if args.range:
        base, head = parse_range(args.range)
    else:
        base, head = args.base, args.head

    if args.review_dir:
        review_dir = Path(args.review_dir).resolve()
        review_dir.mkdir(parents=True, exist_ok=True)
    else:
        review_dir = Path(
            tempfile.mkdtemp(prefix="msd-review-")
        )

    diff_dir = review_dir / "diffs"
    diff_dir.mkdir(parents=True, exist_ok=True)
    checklist_dir = review_dir / "checklist"
    checklist_dir.mkdir(parents=True, exist_ok=True)

    files = changed_files(repo, base, head)
    written, skipped = write_per_file_diffs(
        repo, base, head, files, diff_dir, args.skip_glob
    )
    write_extension_scoping(diff_dir)

    checklist_text = render_checklist(
        repo, base, head, written, skipped, diff_dir
    )
    checklist_path = checklist_dir / "CHECKLIST.md"
    checklist_path.write_text(checklist_text, encoding="utf-8")

    diff_paths = sorted(diff_dir.glob("*.diff"))

    print(f"review dir:  {review_dir}")
    print(f"diffs:       {diff_dir} ({len(written)} files)")
    if skipped:
        print(f"skipped:     {len(skipped)} files")
    print(f"checklist:   {checklist_path}")

    if args.no_open:
        return review_dir

    open_checklist_window(checklist_dir, checklist_path)
    open_diff_window(diff_dir, diff_paths)

    if not args.no_position:
        position_windows_side_by_side()

    return review_dir


# True when `repo` is inside a git working tree (handles worktrees whose
# .git is a file). Cheap shell-out; returns False on any git failure.
def git_dir_exists(repo: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and open the multi-swe-day human-review-gate "
            "review surface (checklist left, per-file diffs right)."
        )
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repo / worktree path to diff.",
    )
    parser.add_argument(
        "--range",
        help="Git range '<base>..<head>'.",
    )
    parser.add_argument("--base", help="Base ref (with --head).")
    parser.add_argument("--head", help="Head ref (with --base).")
    parser.add_argument(
        "--review-dir",
        help="Use this review dir instead of a fresh temp one.",
    )
    parser.add_argument(
        "--skip-glob",
        action="append",
        default=[],
        help="Repeatable glob of changed paths to skip.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Build the surface but do not open VS Code.",
    )
    parser.add_argument(
        "--no-position",
        action="store_true",
        help="Open both windows but skip osascript positioning.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run embedded unit tests and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.range and not (args.base and args.head):
        parser.error("provide --range or both --base and --head")

    build_and_open(args)
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


# Exercise the pure helpers (range parsing, flattening, skip, checklist,
# scoping files) against a throwaway git repo. No VS Code is launched.
def run_self_test() -> int:
    import unittest

    class ReviewOpenTests(unittest.TestCase):
        def test_parse_range_two_dot(self) -> None:
            self.assertEqual(parse_range("a..b"), ("a", "b"))

        def test_parse_range_three_dot(self) -> None:
            self.assertEqual(parse_range("a...b"), ("a", "b"))

        def test_parse_range_sha(self) -> None:
            self.assertEqual(
                parse_range("HEAD~3..HEAD"), ("HEAD~3", "HEAD")
            )

        def test_parse_range_bad(self) -> None:
            with self.assertRaises(ValueError):
                parse_range("not-a-range")

        def test_diff_filename_flatten(self) -> None:
            self.assertEqual(
                diff_filename_for("src/a/b.ts"), "src-a-b.ts.diff"
            )

        def test_diff_filename_root(self) -> None:
            self.assertEqual(diff_filename_for("README.md"), "README.md.diff")

        def test_should_skip(self) -> None:
            self.assertTrue(
                should_skip("drizzle/meta/x.json", ["drizzle/meta/*"])
            )
            self.assertFalse(
                should_skip("src/app.ts", ["drizzle/meta/*"])
            )

        def test_changed_files_keeps_whitespace_names(self) -> None:
            with tempfile.TemporaryDirectory() as tmp:
                repo = Path(tmp)
                run = lambda *a: subprocess.run(
                    ["git", "-C", str(repo), *a],
                    check=True,
                    capture_output=True,
                )
                run("init", "-q")
                run("config", "user.email", "t@example.com")
                run("config", "user.name", "t")
                (repo / "a.txt").write_text("one\n")
                run("add", "-A")
                run("commit", "-q", "-m", "base")
                (repo / " ").write_text("spaces\n")
                (repo / "a.txt").write_text("two\n")
                (repo / "z ").write_text("trailing\n")
                run("add", "-A")
                run("commit", "-q", "-m", "head")
                self.assertEqual(
                    changed_files(repo, "HEAD~1", "HEAD"),
                    [" ", "a.txt", "z "],
                )

        def test_end_to_end_build(self) -> None:
            with tempfile.TemporaryDirectory() as tmp:
                repo = Path(tmp) / "repo"
                repo.mkdir()
                run = lambda *a: subprocess.run(
                    ["git", "-C", str(repo), *a],
                    check=True,
                    capture_output=True,
                )
                run("init", "-q")
                run("config", "user.email", "t@example.com")
                run("config", "user.name", "t")
                (repo / "a.txt").write_text("one\n")
                sub = repo / "src"
                sub.mkdir()
                (sub / "b.ts").write_text("const x = 1;\n")
                run("add", "-A")
                run("commit", "-q", "-m", "base")
                base = git(repo, "rev-parse", "HEAD")
                (repo / "a.txt").write_text("one\ntwo\n")
                (sub / "b.ts").write_text("const x = 2;\n")
                (repo / "gen.json").write_text("{}\n")
                run("add", "-A")
                run("commit", "-q", "-m", "head")
                head = git(repo, "rev-parse", "HEAD")

                review_dir = Path(tmp) / "review"
                args = argparse.Namespace(
                    repo=str(repo),
                    range=f"{base}..{head}",
                    base=None,
                    head=None,
                    review_dir=str(review_dir),
                    skip_glob=["gen.json"],
                    no_open=True,
                    no_position=True,
                    self_test=False,
                )
                out = build_and_open(args)
                self.assertEqual(out, review_dir.resolve())

                diff_dir = review_dir / "diffs"
                # One .diff per non-skipped changed file.
                self.assertTrue((diff_dir / "a.txt.diff").exists())
                self.assertTrue((diff_dir / "src-b.ts.diff").exists())
                # Skipped file gets no .diff.
                self.assertFalse((diff_dir / "gen.json.diff").exists())
                # Sentinel pair + .vscode present.
                self.assertTrue((diff_dir / SENTINEL_MANIFEST).exists())
                self.assertTrue((diff_dir / SENTINEL_SCHEMA).exists())
                self.assertTrue(
                    (diff_dir / ".vscode" / "settings.json").exists()
                )
                # Checklist names both files and a verdict section.
                checklist = (
                    review_dir / "checklist" / "CHECKLIST.md"
                ).read_text()
                self.assertIn("a.txt", checklist)
                self.assertIn("src/b.ts", checklist)
                self.assertIn("## Verdict", checklist)
                self.assertIn("gen.json", checklist)  # in Skipped section

    suite = unittest.TestLoader().loadTestsFromTestCase(ReviewOpenTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
