#!/usr/bin/env python3
"""Prove the tooling's guards fire, on a throwaway copy.

Every test here corresponds to a way this repository could
have shipped something wrong: a path that escapes the
checkout, a pin that re-pins itself, a validator that crashes
on the one entry worth reporting, a badge that says read-only
about a skill which runs commands.

A guard with no test is a comment. These run the real tools
against a copied tree with a deliberately broken meta/ or
marketplace.json, and assert on what the tool did, not on
what it says in its source.

    python3 -m unittest discover -s tools -p 'test_*.py' -q

No third-party packages, same as everything else here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META = "meta/replx.skill.yml"


class GuardTest(unittest.TestCase):
    """Each test gets its own copy of the repository."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "skills"
        shutil.copytree(
            ROOT, self.repo,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )
        # A canary beside the copy, so an escaping write lands
        # somewhere this test can see rather than somewhere it
        # cannot.
        self.canary = self.tmp / "CANARY"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers ---------------------------------------------

    def run_tool(self, name: str, *args: str):
        return subprocess.run(
            [sys.executable, f"tools/{name}", *args],
            cwd=self.repo, capture_output=True, text=True,
        )

    def edit_meta(self, key: str, value: str | None) -> None:
        """Set a top-level key in meta/, or drop it when None."""
        path = self.repo / META
        out = []
        for line in path.read_text().split("\n"):
            if line.startswith(key + ":"):
                if value is not None:
                    out.append(f"{key}: {value}")
                continue
            out.append(line)
        path.write_text("\n".join(out))

    def edit_marketplace(self, mutate) -> None:
        path = self.repo / ".claude-plugin/marketplace.json"
        data = json.loads(path.read_text())
        mutate(data)
        path.write_text(json.dumps(data, indent=2) + "\n")

    # -- containment -----------------------------------------

    def test_sync_refuses_a_traversing_vendored_path(self) -> None:
        """`../` in meta/ must not write outside the checkout.

        vendored_path is data a pull request controls. Joined to
        the repository root with no check, it is an arbitrary
        file write.
        """
        self.edit_meta("vendored_path", "../../../../CANARY")
        result = self.run_tool("sync_skills.gpt.py")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(
            self.canary.exists(),
            "sync wrote outside the repository despite the guard",
        )

    def test_sync_refuses_an_absolute_vendored_path(self) -> None:
        """`Path('/a') / '/etc/x'` is `/etc/x`, not `/a/etc/x`."""
        self.edit_meta("vendored_path", "/tmp/CANARY-absolute")
        result = self.run_tool("sync_skills.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stdout + result.stderr)
        self.assertFalse(Path("/tmp/CANARY-absolute").exists())

    def test_validate_refuses_a_traversing_vendored_path(self) -> None:
        """The validator reads the same field and needs the same guard."""
        self.edit_meta("vendored_path", "../../../../CANARY")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    # -- the pin ---------------------------------------------

    def test_sync_refuses_a_tag_that_moved(self) -> None:
        """A tag is mutable, so cloning it is not evidence.

        The old version overwrote upstream_sha with whatever the
        tag pointed at now, which meant the file recording the
        pin was rewritten by the tool that should have checked
        it.
        """
        self.edit_meta("upstream_sha", "0" * 40)
        result = self.run_tool("sync_skills.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has moved", result.stdout)
        self.assertIn(
            "0" * 40,
            (self.repo / META).read_text(),
            "sync overwrote the pin it was supposed to verify",
        )

    # -- the validator's own robustness ----------------------

    def test_plugin_entry_without_a_source_is_reported(self) -> None:
        """It used to raise TypeError and hide every other error."""
        self.edit_marketplace(
            lambda d: d["plugins"].append({"name": "sourceless"})
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("has no source", result.stdout)

    def test_unparseable_plugin_json_is_reported(self) -> None:
        """Existing is not the same as being valid."""
        (self.repo / "plugins/replx/.claude-plugin/plugin.json").write_text(
            "{ not json"
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not parse", result.stdout)

    # -- honest badges ---------------------------------------

    def test_a_missing_side_effect_flag_fails_validation(self) -> None:
        """An omitted flag used to render as `read-only`.

        That is the one wrong answer the badge must never give:
        a skill that runs commands advertising itself as safe.
        """
        self.edit_meta("executes", None)
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("side-effect", result.stdout)

    def test_a_misspelled_flag_never_renders_as_a_capability(self) -> None:
        self.edit_meta("executes", "ture")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be true or false", result.stdout)

        self.run_tool("build_catalogue.gpt.py")
        index = (self.repo / "INDEX.md").read_text()
        self.assertNotIn(
            "ture", index, "a malformed flag reached the rendered index"
        )

    # -- the two copies of one fact --------------------------

    def test_meta_and_marketplace_must_agree(self) -> None:
        """Two copies drift; this is what notices."""
        self.edit_meta("license", "Apache-2.0")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("disagrees", result.stdout)

    # -- the check that used to fix what it checked ----------

    def test_catalogue_check_does_not_write(self) -> None:
        """It regenerated before diffing, so it could not fail
        for the reason it existed to catch."""
        index = self.repo / "INDEX.md"
        index.write_text(index.read_text() + "STALE\n")
        before = index.read_bytes()

        result = self.run_tool("build_catalogue.gpt.py", "--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale", result.stdout)
        self.assertEqual(
            before, index.read_bytes(),
            "--check rewrote the file it was checking",
        )

    def test_the_committed_repository_passes(self) -> None:
        """The guards above must not be firing on the real tree."""
        self.assertEqual(
            self.run_tool("validate.gpt.py").returncode, 0
        )
        self.assertEqual(
            self.run_tool("build_catalogue.gpt.py", "--check").returncode, 0
        )


if __name__ == "__main__":
    unittest.main()
