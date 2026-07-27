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

    python3 tools/test_guards.gpt.py

Run it directly. `unittest discover` cannot import this file:
`test_guards.gpt` is not a valid module name, which is the one
practical cost of the `.gpt` provenance infix.

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

    def _local_upstream(self) -> str:
        """A real git repository on disk, with the expected layout.

        The pin tests used to clone from GitHub, which made them
        fail in CI for reasons that had nothing to do with the
        guard under test. A unit test should not need a network.
        """
        up = self.tmp / "upstream"
        (up / "skill").mkdir(parents=True)
        (up / "skill" / "SKILL.md").write_text(
            (self.repo / "plugins/replx/skills/replx/SKILL.md").read_text()
        )
        git = lambda *a: subprocess.run(
            ["git", *a], cwd=up, capture_output=True, text=True, check=True)
        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        git("config", "commit.gpgsign", "false")
        git("add", "-A")
        git("commit", "-q", "-m", "upstream")
        git("tag", "v0.2.0")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=up,
                              capture_output=True, text=True,
                              check=True).stdout.strip()
        self.edit_meta("upstream", up.as_uri())
        return head

    def test_sync_refuses_a_tag_that_moved(self) -> None:
        """A tag is mutable, so cloning it is not evidence.

        The old version overwrote upstream_sha with whatever the
        tag pointed at now, which meant the file recording the
        pin was rewritten by the tool that should have checked
        it.
        """
        self._local_upstream()
        self.edit_meta("upstream_sha", "0" * 40)
        result = self.run_tool("sync_skills.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has moved", result.stdout)
        self.assertIn(
            "0" * 40,
            (self.repo / META).read_text(),
            "sync overwrote the pin it was supposed to verify",
        )

    def test_sync_accepts_the_pin_it_was_given(self) -> None:
        """The guard must not fire when the tag has not moved."""
        head = self._local_upstream()
        self.edit_meta("upstream_sha", head)
        result = self.run_tool("sync_skills.gpt.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("unchanged", result.stdout)

    def test_sync_reports_an_unreachable_upstream(self) -> None:
        """A failed clone used to raise CalledProcessError.

        Empty stdout and a traceback, which is what a network
        problem in CI looked like: indistinguishable from the
        guard under test not firing.
        """
        self.edit_meta("upstream", (self.tmp / "does-not-exist").as_uri())
        result = self.run_tool("sync_skills.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot fetch", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

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

    # -- what an independent review found --------------------

    def test_a_null_owner_is_reported_not_crashed(self) -> None:
        """`{"owner": null}` is valid JSON a pull request can write.

        `mkt.get("owner", {})` returns None when the key exists
        with a null value, so the default never applied and the
        validator raised instead of reporting.
        """
        self.edit_marketplace(lambda d: d.__setitem__("owner", None))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("owner", result.stdout)

    def test_a_null_plugin_entry_is_reported_not_crashed(self) -> None:
        self.edit_marketplace(lambda d: d["plugins"].append(None))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("not an object", result.stdout)

    def test_a_branch_is_not_accepted_as_a_pin(self) -> None:
        """CONTRIBUTING promises never to track a branch.

        The check was `"ref" in src`, so {"ref": "main"} passed
        as a pin and the promise was documentation only.
        """
        self.edit_marketplace(lambda d: d["plugins"].append(
            {"name": "remote-thing",
             "source": {"source": "github", "repo": "a/b", "ref": "main"}}))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("branch", result.stdout)

    def test_an_empty_ref_is_not_accepted_as_a_pin(self) -> None:
        self.edit_marketplace(lambda d: d["plugins"].append(
            {"name": "remote-thing",
             "source": {"source": "github", "repo": "a/b", "ref": ""}}))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no ref or sha pin", result.stdout)

    def test_deleting_upstream_sha_is_not_a_way_out(self) -> None:
        """sync only compares the pin when the pin is present.

        So removing the line disabled the check entirely, and
        nothing else required the field.
        """
        self.edit_meta("upstream_sha", None)
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upstream_sha", result.stdout)

    def test_plugin_root_cannot_escape_the_checkout(self) -> None:
        self.edit_marketplace(
            lambda d: d.setdefault("metadata", {}).__setitem__(
                "pluginRoot", "../../../../etc"))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_plugin_source_cannot_escape_the_plugin_root(self) -> None:
        self.edit_marketplace(lambda d: d["plugins"].append(
            {"name": "escapee", "source": "../../../../etc"}))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_renames_cannot_point_at_a_live_name(self) -> None:
        """A name cannot be both current and former."""
        self.edit_marketplace(
            lambda d: d.__setitem__("renames", {"replx": "replx"}))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("still a live plugin name", result.stdout)

    def test_renames_cannot_point_at_a_missing_plugin(self) -> None:
        self.edit_marketplace(
            lambda d: d.__setitem__("renames", {"old-name": "nonexistent"}))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a plugin in this marketplace", result.stdout)

    def test_a_removal_rename_is_accepted(self) -> None:
        """Mapping to null records that a plugin is gone."""
        self.edit_marketplace(
            lambda d: d.__setitem__("renames", {"old-name": None}))
        result = self.run_tool("validate.gpt.py")
        self.assertEqual(result.returncode, 0, result.stdout)

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
