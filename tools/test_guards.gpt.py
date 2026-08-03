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

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META = "meta/replx.skill.yml"
HTMLIFY_META = "meta/htmlify.skill.yml"

# What the published replx entry is, written out rather than
# read from the file the tests are checking. These are the
# values that went out to everyone who has already run
# `/plugin install replx@trycopilotai`, so a change to any of
# them changes what an existing user's next update installs.
REPLX_PUBLISHED = {
    "version": "0.2.0",
    "upstream_ref": "v0.2.0",
    "upstream_sha": "8669615675a920b7c8926e0377cc75b4d963ee7b",
    "vendored_path": "plugins/replx/skills/replx/SKILL.md",
    "vendored_sha256":
        "7c885fd38801e3d0d84879c9ddc46730e975ea5116ea4e7783f58712fc577e61",
}


class ReplxNonRegressionTest(unittest.TestCase):
    """The first published entry, checked against its own past.

    Every other test here runs against a throwaway copy. These
    run against the tracked tree, because the question is not
    whether the tooling would catch a change to replx, it is
    whether this commit made one.
    """

    def meta_fields(self) -> dict:
        out = {}
        for line in (ROOT / META).read_text().splitlines():
            key, sep, value = line.partition(":")
            if sep and not line.startswith(" "):
                out[key.strip()] = value.strip()
        return out

    def test_the_published_pin_and_digest_are_untouched(self) -> None:
        fields = self.meta_fields()
        for key, expected in REPLX_PUBLISHED.items():
            if key == "version":
                continue
            self.assertEqual(
                fields.get(key), expected,
                f"replx {key} moved away from the published entry",
            )

    def test_the_vendored_bytes_still_hash_to_the_published_digest(
        self,
    ) -> None:
        """Recorded and actual, checked independently of meta/.

        A commit that changed the bytes and the recorded digest
        together would pass `make validate`, which only compares
        the two against each other.
        """
        vendored = ROOT / REPLX_PUBLISHED["vendored_path"]
        self.assertEqual(
            hashlib.sha256(vendored.read_bytes()).hexdigest(),
            REPLX_PUBLISHED["vendored_sha256"],
            "replx's vendored SKILL.md is not the published copy",
        )

    def test_it_is_still_vendored_as_a_single_file(self) -> None:
        """Repackaging replx would change every existing install."""
        self.assertTrue((ROOT / REPLX_PUBLISHED["vendored_path"]).is_file())

    def test_it_still_claims_only_the_client_it_was_tested_on(self) -> None:
        """replx ships no Codex metadata, so it must claim none.

        The marketplace gained a second client. Quietly listing
        an untested skill for it would be the marketplace making
        a claim the skill cannot support.
        """
        self.assertFalse(
            (ROOT / "plugins/replx/.codex-plugin").exists(),
            "replx grew a Codex manifest it was never tested with",
        )
        codex = json.loads(
            (ROOT / ".agents/plugins/marketplace.json").read_text()
        )
        self.assertNotIn(
            "replx",
            {p.get("name") for p in codex["plugins"]},
            "replx is listed for Codex without shipping Codex metadata",
        )
        catalogue = json.loads((ROOT / "catalogue.json").read_text())
        entry = next(
            s for s in catalogue["skills"] if s["name"] == "replx"
        )
        self.assertEqual(entry["clients"], ["claude-code"])

    def test_its_marketplace_entry_still_describes_the_same_plugin(
        self,
    ) -> None:
        mkt = json.loads(
            (ROOT / ".claude-plugin/marketplace.json").read_text()
        )
        entry = next(p for p in mkt["plugins"] if p["name"] == "replx")
        self.assertEqual(entry["version"], REPLX_PUBLISHED["version"])
        self.assertEqual(entry["license"], "MIT")
        manifest = json.loads(
            (ROOT / "plugins/replx/.claude-plugin/plugin.json").read_text()
        )
        self.assertEqual(manifest["version"], REPLX_PUBLISHED["version"])


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

    def edit_codex_marketplace(self, mutate) -> None:
        path = self.repo / ".agents/plugins/marketplace.json"
        data = json.loads(path.read_text())
        mutate(data)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def edit_json(self, relative: str, mutate) -> None:
        path = self.repo / relative
        data = json.loads(path.read_text())
        mutate(data)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def edit_meta_file(self, relative: str, key: str, value) -> None:
        """Set a top-level key in any meta/ file, or drop it."""
        path = self.repo / relative
        out = []
        skipping = False
        for line in path.read_text().split("\n"):
            if line.startswith(key + ":"):
                skipping = True
                if value is not None:
                    out.append(f"{key}: {value}")
                continue
            # A sequence value's items are indented under it, so
            # dropping the key has to drop them too.
            if skipping and line.startswith("  "):
                continue
            skipping = False
            out.append(line)
        path.write_text("\n".join(out))

    def isolate_sync_fixture(self) -> None:
        """Leave only replx's meta entry in the copy.

        `make sync` walks every entry, so a guard case aimed at
        one of them would otherwise reach the network on behalf
        of the others and fail for a reason unrelated to the
        guard under test.
        """
        for meta in (self.repo / "meta").glob("*.skill.yml"):
            if meta.name != Path(META).name:
                meta.unlink()

    # -- containment -----------------------------------------

    def test_sync_refuses_a_traversing_vendored_path(self) -> None:
        """`../` in meta/ must not write outside the checkout.

        vendored_path is data a pull request controls. Joined to
        the repository root with no check, it is an arbitrary
        file write.
        """
        self.isolate_sync_fixture()
        self.edit_meta("vendored_path", "../../../../CANARY")
        result = self.run_tool("sync_skills.gpt.py")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(
            self.canary.exists(),
            "sync wrote outside the repository despite the guard",
        )

    def test_sync_refuses_an_absolute_vendored_path(self) -> None:
        """`Path('/a') / '/etc/x'` is `/etc/x`, not `/a/etc/x`."""
        self.isolate_sync_fixture()
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
        def git(*a):
            return subprocess.run(
                ["git", *a], cwd=up, capture_output=True, text=True,
                check=True)

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
        self.isolate_sync_fixture()
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
        self.isolate_sync_fixture()
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
        self.isolate_sync_fixture()
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

    # -- a second entry, and a second client -----------------

    def test_a_source_that_omits_the_plugin_directory_is_refused(
        self,
    ) -> None:
        """The shorter form validated, then failed at install.

        `metadata.pluginRoot` reads like a base directory for
        every `source`. Claude Code 2.1.220 ignores it and
        resolves `source` against the marketplace root, so
        {"pluginRoot": "./plugins"} with {"source": "./replx"}
        passed every check here and then failed with "Source
        path does not exist".
        """
        self.edit_marketplace(
            lambda d: self.plugin(d, "replx").__setitem__("source", "./replx")
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("./plugins/replx", result.stdout)

    def test_plugin_root_metadata_is_refused(self) -> None:
        """The key that made the broken form look deliberate."""
        self.edit_marketplace(
            lambda d: d.setdefault("metadata", {}).__setitem__(
                "pluginRoot", "./plugins")
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pluginRoot", result.stdout)

    def test_a_codex_manifest_nobody_declared_is_reported(self) -> None:
        """Shipping for a client without saying so is still a claim."""
        self.edit_meta_file(HTMLIFY_META, "clients", "\n  - claude-code")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".codex-plugin/plugin.json", result.stdout)

    def test_declaring_codex_without_the_manifest_is_reported(self) -> None:
        shutil.rmtree(self.repo / "plugins/htmlify/.codex-plugin")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".codex-plugin/plugin.json", result.stdout)

    def test_declaring_codex_without_the_agent_metadata_is_reported(
        self,
    ) -> None:
        """Codex installs the plugin, then cannot invoke the skill."""
        (self.repo
         / "plugins/htmlify/skills/htmlify/agents/openai.yaml").unlink()
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agents/openai.yaml", result.stdout)

    def test_a_plugin_missing_from_the_codex_marketplace_is_reported(
        self,
    ) -> None:
        self.edit_codex_marketplace(
            lambda d: d.__setitem__(
                "plugins",
                [p for p in d["plugins"] if p.get("name") != "htmlify"],
            )
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Codex marketplace", result.stdout)

    def test_a_codex_entry_for_no_such_plugin_is_reported(self) -> None:
        self.edit_codex_marketplace(
            lambda d: d["plugins"].append({
                "name": "ghost",
                "source": {"source": "local", "path": "./plugins/ghost"},
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Developer Tools",
            })
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a plugin in the Claude Code marketplace",
                      result.stdout)

    def test_manifests_that_disagree_are_reported(self) -> None:
        """Two manifests are two copies of one plugin's identity."""
        self.edit_json(
            "plugins/htmlify/.codex-plugin/plugin.json",
            lambda d: d.__setitem__("description", "something else"),
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("disagree on 'description'", result.stdout)

    def test_the_two_codex_interfaces_must_agree(self) -> None:
        """The manifest and agents/openai.yaml both name the skill."""
        self.edit_json(
            "plugins/htmlify/.codex-plugin/plugin.json",
            lambda d: d["interface"].__setitem__(
                "shortDescription", "a different summary"),
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("short_description", result.stdout)

    def test_a_default_prompt_naming_another_skill_is_reported(self) -> None:
        path = (self.repo
                / "plugins/htmlify/skills/htmlify/agents/openai.yaml")
        path.write_text(path.read_text().replace("$htmlify", "$something"))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("$htmlify", result.stdout)

    def test_a_manifest_version_that_is_not_the_vendored_tag_is_reported(
        self,
    ) -> None:
        """Otherwise the listing advertises bytes it did not ship."""
        self.edit_json(
            "plugins/htmlify/.claude-plugin/plugin.json",
            lambda d: d.__setitem__("version", "9.9.9"),
        )
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the vendored tag", result.stdout)

    # -- the digest over a whole package ---------------------

    def package_file(self, name: str) -> Path:
        return self.repo / "plugins/htmlify/skills/htmlify" / name

    def test_an_edited_byte_in_a_vendored_package_is_caught(self) -> None:
        path = self.package_file("scripts/formal_render.py")
        path.write_text(path.read_text() + "\n# edited\n")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("drifted from upstream", result.stdout)

    def test_a_file_added_to_a_vendored_package_is_caught(self) -> None:
        """A file-by-file check would not see an addition."""
        self.package_file("scripts/extra.py").write_text("print('extra')\n")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("drifted from upstream", result.stdout)

    def test_a_file_removed_from_a_vendored_package_is_caught(self) -> None:
        self.package_file("scripts/formal_render.py").unlink()
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("drifted from upstream", result.stdout)

    def test_a_renamed_file_in_a_vendored_package_is_caught(self) -> None:
        """The same bytes under a new name install differently.

        A digest over concatenated contents alone would call
        this unchanged, which is why the relative path is inside
        the hash.
        """
        source = self.package_file("scripts/formal_render.py")
        source.rename(self.package_file("scripts/renderer.py"))
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("drifted from upstream", result.stdout)

    def test_a_symlink_in_a_vendored_package_is_refused(self) -> None:
        """A link makes the digest describe bytes it does not ship."""
        outside = self.tmp / "outside.txt"
        outside.write_text("not part of the package\n")
        self.package_file("scripts/link.py").symlink_to(outside)
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symbolic links are not allowed", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    # -- generating more than one row ------------------------

    def test_every_meta_entry_reaches_every_generated_surface(self) -> None:
        """One entry rendered by hand; two have to be generated."""
        self.run_tool("build_catalogue.gpt.py")
        catalogue = json.loads((self.repo / "catalogue.json").read_text())
        names = [s["name"] for s in catalogue["skills"]]
        self.assertEqual(names, ["replx", "htmlify"], "order key ignored")

        index = (self.repo / "INDEX.md").read_text()
        readme = (self.repo / "README.md").read_text()
        self.assertIn("2 skills in the `trycopilotai` marketplace.", index)
        for name in names:
            self.assertIn(f"`{name}`", index)
            self.assertIn(f"`{name}`", readme)

    def test_a_new_entry_makes_the_committed_surfaces_stale(self) -> None:
        """--check has to notice a row that was never rendered."""
        source = (self.repo / HTMLIFY_META).read_text()
        (self.repo / "meta/zzz.skill.yml").write_text(
            source.replace("name: htmlify", "name: zzz").replace(
                "order: 2", "order: 9")
        )
        result = self.run_tool("build_catalogue.gpt.py", "--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale", result.stdout)

    def test_a_hand_edited_readme_table_is_stale(self) -> None:
        """The README's table is generated, so it can rot too."""
        readme = self.repo / "README.md"
        readme.write_text(
            readme.read_text().replace("Claude Code, Codex", "Every client")
        )
        result = self.run_tool("build_catalogue.gpt.py", "--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("README.md", result.stdout)

    def test_the_readme_table_region_is_rewritten_not_appended(self) -> None:
        """Regenerating must be idempotent, not additive."""
        first = self.run_tool("build_catalogue.gpt.py")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        once = (self.repo / "README.md").read_text()
        self.run_tool("build_catalogue.gpt.py")
        self.assertEqual(once, (self.repo / "README.md").read_text())
        self.assertEqual(once.count("# skills"), 1)

    def test_a_pending_entry_is_not_linked_to_a_missing_upstream(
        self,
    ) -> None:
        """A link is a claim the repository exists at that name."""
        self.edit_meta_file(HTMLIFY_META, "status", "pending-publication")
        self.run_tool("build_catalogue.gpt.py")
        index = (self.repo / "INDEX.md").read_text()
        self.assertIn("`htmlify`", index)
        self.assertNotIn(
            "[`htmlify`](https://github.com/trycopilotai/htmlify)", index
        )

    def test_an_unknown_status_is_reported(self) -> None:
        self.edit_meta_file(HTMLIFY_META, "status", "probably-fine")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status", result.stdout)

    def test_an_unresolved_pin_must_say_it_is_unpublished(self) -> None:
        """The sentinel is not a way to skip the pin check.

        An entry may record UNRESOLVED instead of a commit id,
        because inventing one would make every later check pass.
        It may not do that while also calling itself published.
        """
        self.edit_meta_file(HTMLIFY_META, "upstream_sha", "UNRESOLVED")
        result = self.run_tool("validate.gpt.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pending-publication", result.stdout)

    def test_the_committed_repository_passes(self) -> None:
        """The guards above must not be firing on the real tree."""
        self.assertEqual(
            self.run_tool("validate.gpt.py").returncode, 0
        )
        self.assertEqual(
            self.run_tool("build_catalogue.gpt.py", "--check").returncode, 0
        )

    def plugin(self, data: dict, name: str) -> dict:
        for entry in data["plugins"]:
            if entry.get("name") == name:
                return entry
        self.fail(f"no {name!r} plugin in the fixture")


class ReleaseGateTest(GuardTest):
    """The gate that decides whether an entry may be published.

    Every case here builds its own remote on disk, so the suite
    still needs no network. The gate's whole point is that it
    asks a remote, and a test that asked the real one would
    fail for reasons that have nothing to do with the gate.
    """

    def remote(self, package_bytes: str | None = None,
               tag: str | None = "v0.2.3") -> str:
        """A git repository laid out the way htmlify is."""
        up = self.tmp / "remote"
        package = up / "skills" / "htmlify"
        package.mkdir(parents=True)
        shutil.copytree(
            self.repo / "plugins/htmlify/skills/htmlify",
            package, dirs_exist_ok=True,
        )
        if package_bytes is not None:
            (package / "SKILL.md").write_text(package_bytes)
        def git(*a):
            return subprocess.run(
                ["git", *a], cwd=up, capture_output=True, text=True,
                check=True)

        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        git("config", "commit.gpgsign", "false")
        git("add", "-A")
        git("commit", "-q", "-m", "upstream")
        if tag:
            git("tag", tag)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=up,
            capture_output=True, text=True, check=True).stdout.strip()
        self.edit_meta_file(HTMLIFY_META, "upstream", up.as_uri())
        return head

    def gate(self, *args: str):
        return self.run_tool("release_gate.gpt.py", "--entry", "htmlify",
                             *args)

    def test_it_passes_when_the_remote_matches(self) -> None:
        """The positive control. Without it the rest proves nothing."""
        head = self.remote()
        self.edit_meta_file(HTMLIFY_META, "upstream_sha", head)
        result = self.gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PUBLISHABLE", result.stdout)

    def test_it_holds_an_unresolved_pin(self) -> None:
        """The lint case: a tag that has not been pushed yet."""
        self.edit_meta_file(HTMLIFY_META, "upstream_sha", "UNRESOLVED")
        self.edit_meta_file(HTMLIFY_META, "status", "pending-publication")
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HELD", result.stdout)
        self.assertIn("UNRESOLVED", result.stdout)

    def test_it_holds_a_tag_the_remote_does_not_have(self) -> None:
        head = self.remote(tag=None)
        self.edit_meta_file(HTMLIFY_META, "upstream_sha", head)
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no tag v0.2.3", result.stdout)

    def test_it_holds_a_tag_that_points_somewhere_else(self) -> None:
        self.remote()
        self.edit_meta_file(HTMLIFY_META, "upstream_sha", "0" * 40)
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pinned 000000000000", result.stdout)

    def test_it_holds_when_the_remote_ships_different_bytes(self) -> None:
        """A tag can exist, match the pin, and still not match.

        This is the case the pin alone cannot catch: the commit
        is right and the vendored copy is not what that commit
        contains.
        """
        head = self.remote(package_bytes="---\nname: htmlify\n---\nother\n")
        self.edit_meta_file(HTMLIFY_META, "upstream_sha", head)
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("this repository vendored", result.stdout)

    def test_it_holds_an_unreachable_remote(self) -> None:
        """Not being able to check is a failure, not a pass.

        The reason is asserted, not just the verdict. A remote
        that cannot be reached and a remote that simply has no
        such tag are different diagnoses, and reporting the
        second for the first is the confusion `make sync`
        already had to be fixed for once: a network problem read
        as evidence about the pin.
        """
        self.edit_meta_file(
            HTMLIFY_META, "upstream", (self.tmp / "nothing-here").as_uri()
        )
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HELD", result.stdout)
        self.assertIn("cannot reach", result.stdout)
        self.assertNotIn("has no tag", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_it_holds_a_pending_entry(self) -> None:
        """Publishable means published, not merely consistent."""
        head = self.remote()
        self.edit_meta_file(HTMLIFY_META, "upstream_sha", head)
        self.edit_meta_file(HTMLIFY_META, "status", "pending-publication")
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not 'published'", result.stdout)

    def test_it_holds_a_vendored_copy_that_drifted(self) -> None:
        head = self.remote()
        self.edit_meta_file(HTMLIFY_META, "upstream_sha", head)
        path = self.repo / "plugins/htmlify/skills/htmlify/SKILL.md"
        path.write_text(path.read_text() + "\nlocal edit\n")
        result = self.gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HELD", result.stdout)

    # The inherited cases exercise validate and sync, not the
    # gate, and running them a second time only doubles the
    # suite's cost.
    def test_the_committed_repository_passes(self) -> None:
        raise unittest.SkipTest("covered by GuardTest")


def load_tests(loader, tests, pattern):
    """Keep ReleaseGateTest from re-running everything it inherits."""
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(ReplxNonRegressionTest))
    suite.addTests(loader.loadTestsFromTestCase(GuardTest))
    for name in loader.getTestCaseNames(ReleaseGateTest):
        if name in loader.getTestCaseNames(GuardTest):
            continue
        suite.addTest(ReleaseGateTest(name))
    return suite


if __name__ == "__main__":
    unittest.main()
