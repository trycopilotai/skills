"""Check actual cross-client package closure, without network or models."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/what-next"

class TestWhatNextPackage(unittest.TestCase):
    def test_all_catalogue_versions_match_their_manifests(self):
        entries = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())["plugins"]
        for entry in entries:
            manifest = json.loads((ROOT / entry["source"] / ".claude-plugin/plugin.json").read_text())
            self.assertEqual(entry["version"], manifest["version"], entry["name"])

    def test_validator_rejects_catalogue_version_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            clone = Path(tmp) / "repository"
            shutil.copytree(ROOT, clone, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            path = clone / ".claude-plugin/marketplace.json"
            catalogue = json.loads(path.read_text())
            next(p for p in catalogue["plugins"] if p["name"] == "agent-usage")["version"] = "0.1.0"
            path.write_text(json.dumps(catalogue))
            result = subprocess.run([sys.executable, "tools/validate.gpt.py"], cwd=clone, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("marketplace version '0.1.0' disagrees with plugin.json version '0.2.1'", result.stdout)

    def test_common_metadata_and_native_paths_agree(self):
        portable = json.loads((PLUGIN / "plugin.json").read_text())
        for host in ("claude", "codex"):
            native = json.loads((PLUGIN / ("." + host + "-plugin/plugin.json")).read_text())
            for field in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords"):
                self.assertEqual(portable[field], native[field], field)
            self.assertEqual("./skills/", native["skills"])
            self.assertTrue((PLUGIN / native["skills"] / native["name"] / "SKILL.md").is_file())

    def test_both_catalogues_resolve_the_same_regular_plugin(self):
        claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        c = next(p for p in claude["plugins"] if p["name"] == "what-next")
        a = next(p for p in codex["plugins"] if p["name"] == "what-next")
        self.assertEqual(c["source"], a["source"]["path"])
        self.assertEqual("local", a["source"]["source"])
        self.assertEqual(PLUGIN.resolve(), (ROOT / c["source"]).resolve())
        self.assertEqual("AVAILABLE", a["policy"]["installation"])
        self.assertEqual("ON_INSTALL", a["policy"]["authentication"])

    def test_payload_is_one_skills_only_regular_package(self):
        package = PLUGIN / "skills/what-next"
        files = sorted(p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file())
        self.assertEqual(["SKILL.md", "agents/openai.yaml"], files)
        self.assertFalse(any(p.is_symlink() for p in PLUGIN.rglob("*")))
        self.assertEqual({"what-next"}, {p.name for p in (PLUGIN / "skills").iterdir()})
        for host in ("claude", "codex"):
            native = json.loads((PLUGIN / ("." + host + "-plugin/plugin.json")).read_text())
            self.assertFalse(set(native).intersection({"mcpServers", "hooks", "commands", "agents", "apps"}))

    def test_catalogue_version_and_provenance_match_package(self):
        entry = next(e for e in json.loads((ROOT / "catalogue.json").read_text())["skills"] if e["name"] == "what-next")
        portable = json.loads((PLUGIN / "plugin.json").read_text())
        self.assertEqual("v" + portable["version"], entry["upstream_ref"])
        self.assertRegex(entry["upstream_sha"], r"^[0-9a-f]{40}$")
        self.assertRegex(entry["vendored_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn(entry["upstream_sha"], (PLUGIN / "NOTICE").read_text())
        self.assertEqual(["claude-code", "codex"], entry["clients"])

if __name__ == "__main__":
    unittest.main()
