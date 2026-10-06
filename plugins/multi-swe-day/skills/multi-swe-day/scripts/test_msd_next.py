#!/usr/bin/env python3
"""Unit tests for msd_next — the Active-Run next-action driver.

Covers phase derivation from lane statuses, the explicit `run.phase`
override, the human-gate guard (OWNER human at `human-review`, and that
`render` does not surface reconcile at `human-review`, while a
blocking gate is set, or through a recorded note), and
the end-to-end clear-gate/advance flow that hands the run to the agent.
Pure stdlib; run with `python3 test_msd_next.py`.

The driver under test is `msd_next.py`.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


# Load both modules from beside this test. msd_next is the driver
# under test; reg drives the lane statuses + run object it reads.
_HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    """Import a sibling module from its source filename."""
    spec = importlib.util.spec_from_file_location(name, _HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nxt = _load("msd_next", "msd_next.py")
reg = _load("msd_lane_registry", "msd_lane_registry.py")


class MsdNextTest(unittest.TestCase):
    """Exercise phase derivation, the override, and the human gate."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="msd-next-test-")
        self.registry = os.path.join(self.tmp, "handoff", "msd.json")

    # ---- helpers ---------------------------------------------------

    def reg_cmd(self, argv) -> int:
        """Run a lock-exempt registry command; return its exit code."""
        return reg.main(["--registry", self.registry] + argv)

    def seed_builder(self, slug, lanes):
        """Register one builder (status: proposed)."""
        # `register` needs an initialized registry; `init` leaves an
        # existing one as it is.
        self.reg_cmd(["init", "--leader", "swe-day-leader"])
        argv = [
            "register",
            "--slug",
            slug,
            "--role",
            "builder-01",
            "--day",
            "D42",
            "--plan-path",
            "plans/d42.plan.md",
        ]
        for lane in lanes:
            argv += ["--lane", lane]
        return self.reg_cmd(argv)

    def drive_to_reported(self, slug) -> None:
        """Push one builder all the way to `reported`."""
        self.reg_cmd(["confirm", "--slug", slug, "--propose", "p-" + slug])
        self.reg_cmd(["update", "--slug", slug, "--status", "in-progress"])
        self.reg_cmd(["update", "--slug", slug, "--status", "reported"])

    def resolve(self):
        """Resolve the run state from the on-disk registry."""
        registry = nxt.read_registry(self.registry)
        return nxt.resolve_run(registry)

    def render(self) -> str:
        """Run `msd_next render` and capture its banner text."""
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = nxt.main(["--registry", self.registry, "render"])
        self.assertEqual(code, 0)
        return buffer.getvalue()

    # ---- derivation ------------------------------------------------

    def test_no_registry_is_plan(self) -> None:
        resolved = nxt.resolve_run(None)
        self.assertEqual(resolved["phase"], "plan")
        self.assertEqual(resolved["owner"], "human")

    def test_proposed_lane_is_dispatch_verify(self) -> None:
        self.seed_builder("b1", ["src/a"])
        resolved = self.resolve()
        self.assertEqual(resolved["phase"], "dispatch+verify")
        self.assertEqual(resolved["owner"], "agent")

    def test_in_progress_lane_is_build(self) -> None:
        self.seed_builder("b1", ["src/a"])
        self.reg_cmd(["confirm", "--slug", "b1", "--propose", "p-b1"])
        self.reg_cmd(["update", "--slug", "b1", "--status", "in-progress"])
        resolved = self.resolve()
        self.assertEqual(resolved["phase"], "build")
        self.assertEqual(resolved["owner"], "agent")

    def test_all_reported_is_human_review(self) -> None:
        self.seed_builder("b1", ["src/a"])
        self.seed_builder("b2", ["src/b"])
        self.drive_to_reported("b1")
        self.drive_to_reported("b2")
        resolved = self.resolve()
        self.assertEqual(resolved["phase"], "human-review")
        self.assertEqual(resolved["owner"], "human")
        self.assertEqual(resolved["blocked_on"], "operator")

    def test_all_landed_is_done(self) -> None:
        self.seed_builder("b1", ["src/a"])
        self.drive_to_reported("b1")
        # The registry lands a lane only after the review gate, which
        # records a run phase; write the status directly so this test
        # still covers the derivation with no `run` object.
        with open(self.registry, encoding="utf-8") as handle:
            data = json.load(handle)
        data["followers"]["b1"]["status"] = "landed"
        with open(self.registry, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        resolved = self.resolve()
        self.assertEqual(resolved["phase"], "done")

    # ---- human-gate guard ------------------------------------------

    def test_render_does_not_surface_reconcile_at_human_review(self) -> None:
        # All lanes reported => human-review. The banner must name the
        # operator's review and MUST NOT offer reconcile.
        self.seed_builder("b1", ["src/a"])
        self.drive_to_reported("b1")
        banner = self.render()
        self.assertIn("phase human-review", banner)
        self.assertIn("OWNER: human", banner)
        self.assertIn("BLOCKED-ON: operator", banner)
        self.assertNotIn("reconcile", banner.lower())

    def test_explicit_blocking_gate_forces_human(self) -> None:
        # Even with no lanes (would derive `plan`), a blocking_gate set
        # on the run forces OWNER human and names that gate.
        self.reg_cmd(["init", "--leader", "swe-day-leader"])
        self.reg_cmd(
            [
                "run-advance",
                "--phase",
                "reconcile",
                "--owner",
                "agent",
                "--gate",
                "land-approval",
            ]
        )
        resolved = self.resolve()
        self.assertEqual(resolved["owner"], "human")
        self.assertEqual(resolved["gate"], "land-approval")

    def test_blocking_gate_on_agent_phase_action_is_clear_gate(self) -> None:
        # Regression for the gate-guard leak: a blocking_gate set on an
        # agent-owned phase (reconcile) must flip the resolved ACTION to
        # the human "clear the gate" action, not leave the agent's own
        # action ("leader merges ...") in place. Otherwise the banner
        # surfaces the agent's NEXT while the gate is still unmet.
        self.reg_cmd(["init", "--leader", "swe-day-leader"])
        self.reg_cmd(
            [
                "run-advance",
                "--phase",
                "reconcile",
                "--owner",
                "agent",
                "--gate",
                "land-approval",
            ]
        )
        resolved = self.resolve()
        self.assertEqual(resolved["owner"], "human")
        self.assertEqual(resolved["gate"], "land-approval")
        # The action must be the human clear-gate action, not the agent's.
        self.assertIn("land-approval", resolved["action"])
        self.assertNotIn("merges", resolved["action"])

    def test_render_blocking_gate_on_agent_phase_no_agent_next(self) -> None:
        # The rendered banner must not show the agent's NEXT while a
        # blocking gate is set on an agent-owned phase.
        self.reg_cmd(["init", "--leader", "swe-day-leader"])
        self.reg_cmd(
            [
                "run-advance",
                "--phase",
                "reconcile",
                "--owner",
                "agent",
                "--gate",
                "land-approval",
            ]
        )
        banner = self.render()
        self.assertIn("OWNER: human", banner)
        self.assertIn("BLOCKED-ON: operator", banner)
        # The agent's reconcile action must not appear as the NEXT item.
        self.assertNotIn("merges reported commits", banner)

    # ---- clear-gate then advance hands the run to the agent --------

    def test_clear_gate_then_advance_to_reconcile(self) -> None:
        # Park the run at human-review with the gate set, then the
        # operator clears the gate and the leader advances to reconcile;
        # the resolved owner becomes the agent and the banner offers
        # reconcile as the concrete next item.
        self.seed_builder("b1", ["src/a"])
        self.drive_to_reported("b1")
        self.reg_cmd(
            [
                "run-advance",
                "--phase",
                "human-review",
                "--owner",
                "human",
                "--gate",
                "human-review",
            ]
        )
        self.assertEqual(self.resolve()["owner"], "human")
        # Operator clears the gate.
        self.assertEqual(
            self.reg_cmd(["run-clear-gate", "human-review"]), 0
        )
        # Leader advances to reconcile (agent-owned).
        self.assertEqual(
            self.reg_cmd(
                [
                    "run-advance",
                    "--phase",
                    "reconcile",
                    "--owner",
                    "agent",
                    "--note",
                    "review cleared; merge locally",
                ]
            ),
            0,
        )
        resolved = self.resolve()
        self.assertEqual(resolved["phase"], "reconcile")
        self.assertEqual(resolved["owner"], "agent")
        banner = self.render()
        self.assertIn("phase reconcile", banner)
        self.assertIn("OWNER: agent", banner)

    def test_note_does_not_replace_the_human_action(self) -> None:
        # A note recorded in a human-owned phase is shown on its own
        # line; NEXT stays the operator's action.
        self.reg_cmd(["init", "--leader", "swe-day-leader"])
        self.reg_cmd(
            [
                "run-advance",
                "--phase",
                "human-review",
                "--owner",
                "human",
                "--note",
                "leader merges reported\ncommits now",
            ]
        )
        resolved = self.resolve()
        self.assertEqual(resolved["owner"], "human")
        self.assertEqual(
            resolved["action"], "operator reviews the held builder diffs"
        )
        lines = self.render().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertIn("NEXT: operator reviews the held builder diffs", lines[0])
        self.assertEqual(lines[1], "  next: operator reviews the held builder diffs")
        self.assertEqual(lines[2], "  note: leader merges reported commits now")
        self.assertIn("gate 'human-review' is unmet", lines[3])

    def test_inactive_when_no_lock_and_no_registry(self) -> None:
        # No registry file and no lock path => the run is inactive.
        missing = os.path.join(self.tmp, "absent.json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            nxt.main(["--registry", missing, "render"])
        self.assertIn("INACTIVE", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
