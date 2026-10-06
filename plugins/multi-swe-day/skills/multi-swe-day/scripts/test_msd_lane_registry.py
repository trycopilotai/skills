#!/usr/bin/env python3
"""Unit tests for msd_lane_registry.

Covers the disjointness invariant (exact, ancestor, and proposed-state
conflicts), a clean register, the status-transition chain, lock-owner
enforcement, and the atomic temp-file+rename write. Pure stdlib;
run with `python3 -m unittest test_msd_lane_registry`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


# Load the module from its file beside this test.
_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "msd_lane_registry",
    _HERE / "msd_lane_registry.py",
)
reg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(reg)


class LaneRegistryTest(unittest.TestCase):
    """Exercise the registry's invariant + transition machinery."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="msd-reg-test-")
        self.registry = os.path.join(self.tmp, "handoff", "msd.json")
        # Initialize the registry skeleton (lock-exempt in tests).
        self.run_cmd(self.base_args("init", leader="test-leader"))

    def base_args(self, command: str, **kwargs):
        """Build a parsed-arg-like namespace for one subcommand.

        Mutations are run lock-exempt (no --lock-path) so the tests
        focus on registry logic; lock enforcement is tested separately.
        """
        argv = ["--registry", self.registry, command]
        for key, value in kwargs.items():
            flag = "--" + key.replace("_", "-")
            if isinstance(value, list):
                for item in value:
                    argv += [flag, item]
            else:
                argv += [flag, str(value)]
        return argv

    def run_cmd(self, argv) -> int:
        """Run main() and return its exit code."""
        return reg.main(argv)

    def seed_builder(self, slug, role, lanes, **extra):
        """Register one builder with the given lanes."""
        kwargs = {
            "slug": slug,
            "role": role,
            "day": "D42",
            "plan_path": "plans/d42.plan.md",
            "lane": lanes,
        }
        kwargs.update(extra)
        return self.run_cmd(self.base_args("register", **kwargs))

    def clear_review(self) -> None:
        """Record the human-review gate, clear it, advance to reconcile."""
        self.run_cmd(
            self.base_args(
                "run-advance", phase="human-review", owner="human",
                gate="human-review",
            )
        )
        self.run_cmd(
            ["--registry", self.registry, "run-clear-gate", "human-review"]
        )
        self.run_cmd(
            self.base_args("run-advance", phase="reconcile", owner="agent")
        )

    # ---- clean register --------------------------------------------

    def test_clean_register(self) -> None:
        code = self.seed_builder(
            "swe-day-follower-01",
            "builder-01",
            ["src/auth", "src/billing/types.ts"],
        )
        self.assertEqual(code, 0)
        data = reg.read_registry(self.registry)
        record = data["followers"]["swe-day-follower-01"]
        self.assertEqual(record["status"], "proposed")
        self.assertEqual(record["role"], "builder-01")
        self.assertEqual(
            record["lanes"], ["src/auth", "src/billing/types.ts"]
        )
        self.assertIsNone(record["commit"])
        self.assertEqual(data["schema_version"], reg.SCHEMA_VERSION)

    # ---- exact-path conflict ---------------------------------------

    def test_exact_path_conflict(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/auth/login.ts"])
        code = self.seed_builder("b2", "builder-02", ["src/auth/login.ts"])
        self.assertEqual(code, 4)
        # The losing register must not have written b2.
        data = reg.read_registry(self.registry)
        self.assertNotIn("b2", data["followers"])

    # ---- ancestor-path conflict ------------------------------------

    def test_ancestor_path_conflict(self) -> None:
        # b1 owns a deep file; b2 proposes an ancestor directory.
        self.seed_builder("b1", "builder-01", ["src/auth/login.ts"])
        code = self.seed_builder("b2", "builder-02", ["src/auth"])
        self.assertEqual(code, 4)
        # And the descendant direction also conflicts.
        self.run_cmd(["--registry", self.registry, "release", "--slug", "b1"])
        self.seed_builder("b3", "builder-03", ["src"])
        code2 = self.seed_builder("b4", "builder-04", ["src/auth/login.ts"])
        self.assertEqual(code2, 4)

    def test_non_overlapping_prefix_is_ok(self) -> None:
        # `src/a` and `src/ab` share a textual prefix but are disjoint.
        self.seed_builder("b1", "builder-01", ["src/a"])
        code = self.seed_builder("b2", "builder-02", ["src/ab"])
        self.assertEqual(code, 0)

    # ---- proposed-state conflict -----------------------------------

    def test_proposed_conflict(self) -> None:
        # b1 stays in `proposed` (never confirmed); b2 must still
        # collide against it.
        self.seed_builder("b1", "builder-01", ["pkg/core"])
        data = reg.read_registry(self.registry)
        self.assertEqual(data["followers"]["b1"]["status"], "proposed")
        code = self.seed_builder("b2", "builder-02", ["pkg/core/util.ts"])
        self.assertEqual(code, 4)

    # ---- path rejection --------------------------------------------

    def test_absolute_lane_rejected(self) -> None:
        code = self.seed_builder("b1", "builder-01", ["/etc/passwd"])
        self.assertEqual(code, 2)

    def test_dotdot_lane_rejected(self) -> None:
        code = self.seed_builder("b1", "builder-01", ["../escape"])
        self.assertEqual(code, 2)

    # ---- transitions -----------------------------------------------

    def test_transition_chain(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/x"])
        # confirm: proposed -> assigned
        self.assertEqual(
            self.run_cmd(self.base_args("confirm", slug="b1", propose="p1")), 0
        )
        self.assertEqual(
            reg.read_registry(self.registry)["followers"]["b1"]["status"],
            "assigned",
        )
        # update: assigned -> in-progress -> reported -> landed
        self.assertEqual(
            self.run_cmd(
                self.base_args("update", slug="b1", status="in-progress")
            ),
            0,
        )
        self.assertEqual(
            self.run_cmd(
                self.base_args(
                    "update", slug="b1", status="reported", commit="abc123"
                )
            ),
            0,
        )
        self.clear_review()
        self.assertEqual(
            self.run_cmd(
                self.base_args("update", slug="b1", status="landed")
            ),
            0,
        )
        record = reg.read_registry(self.registry)["followers"]["b1"]
        self.assertEqual(record["status"], "landed")
        self.assertEqual(record["commit"], "abc123")

    def test_illegal_transition_rejected(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/x"])
        # proposed -> reported skips the chain.
        code = self.run_cmd(
            self.base_args("update", slug="b1", status="reported")
        )
        self.assertEqual(code, 5)
        self.assertEqual(
            reg.read_registry(self.registry)["followers"]["b1"]["status"],
            "proposed",
        )

    def test_update_cannot_bypass_confirm(self) -> None:
        """update --status assigned from proposed must be rejected.

        Only confirm is allowed for proposed -> assigned; it is the
        signal to send the build-go prompt.
        """
        self.seed_builder("b1", "builder-01", ["src/x"])
        code = self.run_cmd(
            self.base_args("update", slug="b1", status="assigned")
        )
        self.assertEqual(code, 5)
        self.assertEqual(
            reg.read_registry(self.registry)["followers"]["b1"]["status"],
            "proposed",
        )

    def test_reported_can_abort(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/x"])
        self.run_cmd(self.base_args("confirm", slug="b1", propose="p1"))
        self.run_cmd(
            self.base_args("update", slug="b1", status="in-progress")
        )
        self.run_cmd(
            self.base_args("update", slug="b1", status="reported")
        )
        self.assertEqual(
            self.run_cmd(
                self.base_args("update", slug="b1", status="aborted")
            ),
            0,
        )

    # ---- release re-opens lanes ------------------------------------

    def test_release_frees_lanes(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/shared"])
        self.assertEqual(
            self.seed_builder("b2", "builder-02", ["src/shared"]), 4
        )
        self.run_cmd(["--registry", self.registry, "release", "--slug", "b1"])
        self.assertEqual(
            self.seed_builder("b2", "builder-02", ["src/shared"]), 0
        )

    # ---- aborted lane is re-registerable ---------------------------

    def test_aborted_lane_is_reregisterable(self) -> None:
        # Drive b1 to `aborted`, then a different slug must be able to
        # register the same lane without an explicit release.
        self.seed_builder("b1", "builder-01", ["src/abandoned"])
        self.run_cmd(self.base_args("confirm", slug="b1", propose="p1"))
        self.run_cmd(
            self.base_args("update", slug="b1", status="in-progress")
        )
        self.run_cmd(
            self.base_args("update", slug="b1", status="reported")
        )
        self.assertEqual(
            self.run_cmd(
                self.base_args("update", slug="b1", status="aborted")
            ),
            0,
        )
        # b2 can now claim the abandoned lane.
        self.assertEqual(
            self.seed_builder("b2", "builder-02", ["src/abandoned"]), 0
        )
        # A `landed` lane, by contrast, still blocks.
        self.run_cmd(self.base_args("confirm", slug="b2", propose="p2"))
        self.run_cmd(
            self.base_args("update", slug="b2", status="in-progress")
        )
        self.run_cmd(
            self.base_args("update", slug="b2", status="reported")
        )
        self.clear_review()
        self.assertEqual(
            self.run_cmd(self.base_args("update", slug="b2", status="landed")),
            0,
        )
        self.assertEqual(
            self.seed_builder("b3", "builder-03", ["src/abandoned"]), 4
        )

    # ---- gates the registry enforces -------------------------------

    def drive_to_reported(self, slug) -> None:
        """Take one registered builder through confirm to `reported`."""
        self.run_cmd(self.base_args("confirm", slug=slug, propose="p-" + slug))
        self.run_cmd(self.base_args("update", slug=slug, status="in-progress"))
        self.run_cmd(self.base_args("update", slug=slug, status="reported"))

    def status_of(self, slug) -> str:
        return reg.read_registry(self.registry)["followers"][slug]["status"]

    def test_confirm_without_propose_is_refused(self) -> None:
        # register straight to confirm skips the verify step.
        self.seed_builder("b1", "builder-01", ["src/x"])
        self.assertEqual(self.run_cmd(self.base_args("confirm", slug="b1")), 5)
        self.assertEqual(self.status_of("b1"), "proposed")
        code = self.run_cmd(
            self.base_args("confirm", slug="b1", propose="msg-0001")
        )
        self.assertEqual(code, 0)
        record = reg.read_registry(self.registry)["followers"]["b1"]
        self.assertEqual(record["status"], "assigned")
        self.assertEqual(record["propose"], "msg-0001")

    def test_whitespace_propose_is_refused_and_value_is_trimmed(self) -> None:
        # The docs say: not empty or only whitespace, stored trimmed.
        self.seed_builder("b1", "builder-01", ["src/x"])
        self.assertEqual(
            self.run_cmd(self.base_args("confirm", slug="b1", propose="  ")),
            5,
        )
        self.assertEqual(
            self.run_cmd(
                self.base_args("confirm", slug="b1", propose=" run/b1.md ")
            ),
            0,
        )
        record = reg.read_registry(self.registry)["followers"]["b1"]
        self.assertEqual(record["propose"], "run/b1.md")

    def test_landed_refused_when_review_never_recorded(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/x"])
        self.drive_to_reported("b1")
        code = self.run_cmd(self.base_args("update", slug="b1", status="landed"))
        self.assertEqual(code, 5)
        self.assertEqual(self.status_of("b1"), "reported")

    def test_landed_refused_while_review_gate_pending(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/x"])
        self.drive_to_reported("b1")
        self.run_cmd(
            self.base_args(
                "run-advance", phase="human-review", owner="human",
                gate="human-review",
            )
        )
        code = self.run_cmd(self.base_args("update", slug="b1", status="landed"))
        self.assertEqual(code, 5)
        # Advancing past the gate without clearing it does not help.
        self.run_cmd(self.base_args("run-advance", phase="reconcile", owner="agent"))
        code = self.run_cmd(self.base_args("update", slug="b1", status="landed"))
        self.assertEqual(code, 5)
        self.assertEqual(self.status_of("b1"), "reported")

    def test_landed_allowed_after_review_cleared(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/x"])
        self.seed_builder("b2", "builder-02", ["src/y"])
        self.drive_to_reported("b1")
        self.drive_to_reported("b2")
        self.clear_review()
        run = reg.read_registry(self.registry)["run"]
        self.assertEqual(run["cleared_gates"], ["human-review"])
        code = self.run_cmd(self.base_args("update", slug="b1", status="landed"))
        self.assertEqual(code, 0)
        # Any other pending human gate blocks landing too.
        self.run_cmd(
            self.base_args(
                "run-advance", phase="land-approval", owner="human",
                gate="land-approval",
            )
        )
        code = self.run_cmd(self.base_args("update", slug="b2", status="landed"))
        self.assertEqual(code, 5)
        self.assertEqual(self.status_of("b2"), "reported")

    def test_recording_review_again_makes_it_pending(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/x"])
        self.drive_to_reported("b1")
        self.clear_review()
        self.run_cmd(
            self.base_args(
                "run-advance", phase="human-review", owner="human",
                gate="human-review",
            )
        )
        self.assertEqual(
            reg.read_registry(self.registry)["run"]["cleared_gates"], []
        )
        self.run_cmd(self.base_args("run-advance", phase="reconcile", owner="agent"))
        code = self.run_cmd(self.base_args("update", slug="b1", status="landed"))
        self.assertEqual(code, 5)

    # ---- lock-owner enforcement ------------------------------------

    def _make_lock(self, owner, session_id=None):
        """Create a swe-day-style lock dir with metadata.json."""
        lock_path = os.path.join(self.tmp, "swe-day.lock")
        os.makedirs(lock_path, exist_ok=True)
        metadata = {"owner": owner, "schema_version": 1}
        if session_id is not None:
            metadata["session_id"] = session_id
        with open(os.path.join(lock_path, "metadata.json"), "w") as fh:
            json.dump(metadata, fh)
        return lock_path

    def test_lock_owner_required_and_matched(self) -> None:
        lock_path = self._make_lock("swe-day-leader")
        # Missing --lock-owner is refused.
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "register",
                "--slug",
                "b1",
                "--role",
                "builder-01",
                "--day",
                "D42",
                "--plan-path",
                "plans/d42.plan.md",
                "--lane",
                "src/x",
            ]
        )
        self.assertEqual(code, 3)
        # Wrong owner is refused.
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "register",
                "--slug",
                "b1",
                "--role",
                "builder-01",
                "--day",
                "D42",
                "--plan-path",
                "plans/d42.plan.md",
                "--lane",
                "src/x",
                "--lock-owner",
                "impostor",
            ]
        )
        self.assertEqual(code, 3)
        # Correct owner succeeds.
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "register",
                "--slug",
                "b1",
                "--role",
                "builder-01",
                "--day",
                "D42",
                "--plan-path",
                "plans/d42.plan.md",
                "--lane",
                "src/x",
                "--lock-owner",
                "swe-day-leader",
            ]
        )
        self.assertEqual(code, 0)

    def test_lock_session_enforced(self) -> None:
        lock_path = self._make_lock("swe-day-leader", session_id="sid-1")
        # Right owner but missing/mismatched session.
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "release",
                "--slug",
                "nobody",
                "--lock-owner",
                "swe-day-leader",
                "--session-id",
                "sid-2",
            ]
        )
        self.assertEqual(code, 3)

    def test_status_is_lock_exempt(self) -> None:
        # status never touches the lock even when one is configured.
        lock_path = self._make_lock("swe-day-leader")
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "status",
            ]
        )
        self.assertEqual(code, 0)

    # ---- run object: advance + clear-gate --------------------------

    def test_run_advance_sets_run_object(self) -> None:
        # Lock-exempt (no --lock-path) so this isolates run-object logic.
        self.run_cmd(
            self.base_args(
                "run-advance",
                phase="human-review",
                owner="human",
                gate="human-review",
                note="operator reviews held diffs",
            )
        )
        run = reg.read_registry(self.registry)["run"]
        self.assertEqual(run["phase"], "human-review")
        self.assertEqual(run["next_owner"], "human")
        self.assertEqual(run["blocking_gate"], "human-review")
        self.assertEqual(run["note"], "operator reviews held diffs")

    def test_run_advance_rejects_unknown_phase(self) -> None:
        code = self.run_cmd(
            self.base_args("run-advance", phase="bogus", owner="agent")
        )
        self.assertEqual(code, 2)

    def test_run_clear_gate_clears_matching_gate(self) -> None:
        self.run_cmd(
            self.base_args(
                "run-advance",
                phase="human-review",
                owner="human",
                gate="human-review",
            )
        )
        code = self.run_cmd(
            ["--registry", self.registry, "run-clear-gate", "human-review"]
        )
        self.assertEqual(code, 0)
        run = reg.read_registry(self.registry)["run"]
        self.assertIsNone(run["blocking_gate"])

    def test_run_clear_gate_mismatch_rejected(self) -> None:
        self.run_cmd(
            self.base_args(
                "run-advance",
                phase="human-review",
                owner="human",
                gate="human-review",
            )
        )
        # Clearing a different gate name must not silently unblock.
        code = self.run_cmd(
            ["--registry", self.registry, "run-clear-gate", "land-approval"]
        )
        self.assertEqual(code, 5)
        run = reg.read_registry(self.registry)["run"]
        self.assertEqual(run["blocking_gate"], "human-review")

    def test_run_advance_is_lock_guarded(self) -> None:
        # With a lock configured, run-advance demands the held owner.
        lock_path = self._make_lock("swe-day-leader")
        # Missing --lock-owner is refused.
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "run-advance",
                "--phase",
                "reconcile",
                "--owner",
                "agent",
            ]
        )
        self.assertEqual(code, 3)
        # Wrong owner is refused.
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "run-advance",
                "--phase",
                "reconcile",
                "--owner",
                "agent",
                "--lock-owner",
                "impostor",
            ]
        )
        self.assertEqual(code, 3)
        # Correct owner succeeds (registry skeleton is created first).
        self.run_cmd(self.base_args("run-advance", phase="plan", owner="human"))
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "run-advance",
                "--phase",
                "reconcile",
                "--owner",
                "agent",
                "--lock-owner",
                "swe-day-leader",
            ]
        )
        self.assertEqual(code, 0)

    def test_run_clear_gate_is_lock_guarded(self) -> None:
        lock_path = self._make_lock("swe-day-leader")
        # Seed a blocking gate lock-exempt, then clearing it under a lock
        # demands the held owner.
        self.run_cmd(
            self.base_args(
                "run-advance",
                phase="human-review",
                owner="human",
                gate="human-review",
            )
        )
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "run-clear-gate",
                "human-review",
            ]
        )
        self.assertEqual(code, 3)
        # Still set: the rejected clear did not mutate the gate.
        run = reg.read_registry(self.registry)["run"]
        self.assertEqual(run["blocking_gate"], "human-review")
        # Correct owner clears it.
        code = self.run_cmd(
            [
                "--registry",
                self.registry,
                "--lock-path",
                lock_path,
                "run-clear-gate",
                "human-review",
                "--lock-owner",
                "swe-day-leader",
            ]
        )
        self.assertEqual(code, 0)

    # ---- the single-session sequence in SKILL.md --------------------

    def test_single_session_sequence_runs_under_the_lock(self) -> None:
        # The ordered steps SKILL.md's "Single session" note gives, each
        # lock-checked; the opening plan gate has no clear to run.
        lock_path = self._make_lock("leader", session_id="s1")
        registry = os.path.join(self.tmp, "single", "msd.json")
        proof = ["--lock-owner", "leader", "--session-id", "s1"]

        def run(*argv: str) -> int:
            return self.run_cmd(
                ["--registry", registry, "--lock-path", lock_path,
                 *argv, *proof]
            )

        steps = [
            ("init", "--leader", "leader"),
            ("register", "--slug", "b1", "--role", "builder-01",
             "--day", "D01", "--plan-path", "plans/d01.md",
             "--lane", "src/auth"),
            ("confirm", "--slug", "b1", "--propose", "run/b1.propose.md"),
            ("run-advance", "--phase", "build", "--owner", "agent"),
            ("update", "--slug", "b1", "--status", "in-progress"),
            ("update", "--slug", "b1", "--status", "reported"),
            ("run-advance", "--phase", "human-review", "--owner",
             "human", "--gate", "human-review"),
        ]
        # Right after init there is no run object to clear a gate on.
        self.assertEqual(run(*steps[0]), 0)
        self.assertEqual(run("run-clear-gate", "plan"), 1)
        for step in steps[1:]:
            self.assertEqual(run(*step), 0, step)
        # Once a gate is recorded, any other gate is a mismatch.
        self.assertEqual(run("run-clear-gate", "plan"), 5)
        self.assertEqual(
            run("update", "--slug", "b1", "--status", "landed"), 5
        )
        for step in [
            ("run-clear-gate", "human-review"),
            ("run-advance", "--phase", "reconcile", "--owner", "agent"),
            ("update", "--slug", "b1", "--status", "landed"),
            ("run-advance", "--phase", "land-approval", "--owner",
             "human", "--gate", "land-approval"),
        ]:
            self.assertEqual(run(*step), 0, step)
        run_state = reg.read_registry(registry)["run"]
        self.assertEqual(run_state["blocking_gate"], "land-approval")

    def test_usage_shows_lock_path_on_every_mutation(self) -> None:
        usage = reg.__doc__.split("Usage:\n", 1)[1].split("\nOn a ", 1)[0]
        examples = [block for block in usage.split("\n\n") if block.strip()]
        mutations = [b for b in examples if " status" not in b
                     and "msd_lane_registry.py" in b]
        self.assertGreaterEqual(len(mutations), 7)
        for block in mutations:
            self.assertIn("--lock-path", block)
            self.assertIn("--lock-owner", block)
            self.assertIn("--session-id", block)

    # ---- atomic write ----------------------------------------------

    def test_atomic_write_no_tmp_left(self) -> None:
        self.seed_builder("b1", "builder-01", ["src/x"])
        directory = os.path.dirname(self.registry)
        leftovers = [
            name
            for name in os.listdir(directory)
            if name.startswith(".") and name.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])
        # The committed file is valid JSON (rename was complete).
        with open(self.registry) as fh:
            json.load(fh)

    def test_write_is_via_replace(self) -> None:
        # Overwriting an existing registry preserves a valid object at
        # the destination path the whole time (rename is atomic).
        self.seed_builder("b1", "builder-01", ["src/x"])
        first = reg.read_registry(self.registry)
        self.seed_builder("b2", "builder-02", ["src/y"])
        second = reg.read_registry(self.registry)
        self.assertIn("b1", second["followers"])
        self.assertIn("b2", second["followers"])
        self.assertGreaterEqual(
            second["updated_at"], first["updated_at"]
        )


if __name__ == "__main__":
    unittest.main()
