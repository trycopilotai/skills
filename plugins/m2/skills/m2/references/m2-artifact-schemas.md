# m2 Artifact Schemas

This file defines the machine-readable fields required by
`references/m2.protocol.md`. Markdown artifacts
remain human-facing views. Structured records are the source
for validation, resume, review lifecycle, evidence
freshness, and terminal-state checks.

## General Rules

- Use JSON-compatible field names.
- Every record has `schema_name`, `schema_version`,
  `run_id`, `plan_path`, `created_at_utc`, and `owner`.
- Every artifact path is repo-relative unless it points to a
  sibling worktree.
- Every hash field records the hash algorithm and value in
  one string, such as `sha256:<hex>`.
- When a field is not applicable in `same_thread` mode or
  because an optional derived artifact was not materialized,
  write `null` rather than inventing a placeholder path or
  fake proof.
- Readers must accept legacy records from older fixed-path
  runs when the required identity fields still match.
- Unknown fields may be preserved, but required fields must
  be present.

## Plan Front Matter Record

Required fields:

- `name`.
- `m2_protocol`.
- `execution_intent`.
- `overview`.
- `default_implementation_model`.
- `default_implementation_effort`.
- `todos`.
- `project_root` when the plan uses a project file network.

## Project Manifest Record

Required fields:

- `project_root`.
- `entrypoint_plan`.
- `source_files`.
- `manager_files`.
- `worker_prompt_files`.
- `meeting_files`.
- `packet_registry_path`.
- `acceptance_matrix_path`.
- `file_leases_path`.
- `schema_reference_path`.

`acceptance_matrix_path` must identify the durable project
acceptance matrix source. It must not be a future artifact
when a run is ready to dispatch managers, workers,
reviewers, testers, validation, integration, or delivery.

## Acceptance Matrix Row Record

Required fields:

- `acceptance_id`.
- `source_inputs`.
- `current_state_summary`.
- `target_behavior`.
- `user_journey_ids`.
- `gate_ids`.
- `packet_ids`.
- `required_evidence`.
- `explicit_out_of_scope`.
- `status`.
- `blocking_questions`.
- `owner`.
- `updated_at_utc`.

`source_inputs` is an array of repo paths, project artifact
paths, human prompt references, browser or screenshot
references, command outputs, or external reference notes
used to derive the row.

`current_state_summary` records the observed starting point
from non-mutating discovery. Use `null` only when the row
does not depend on existing behavior.

`target_behavior` is the observable pass condition. It must
be specific enough for a reviewer or tester to decide
whether the row is met without reading hidden chat context.

`user_journey_ids` may identify product users, operators,
maintainers, reviewers, automation, or delivery journeys.

`packet_ids` may be empty while the conductor is still
planning. Before a packet moves to `ready_for_workers`, at
least one packet row must cite each in-scope acceptance id
it owns.

`required_evidence` is an array of commands, browser proof,
screenshots, render artifacts, schema checks, review proof,
manual checks, or other evidence required before the row may
move to `met`.

Valid `status` values:

- `open`.
- `met`.
- `blocked`.
- `superseded`.

## Packet Row Record

Required fields:

- `packet_id`.
- `owner_manager`.
- `worker_role`.
- `allowed_write_paths`.
- `denied_paths`.
- `read_only_context`.
- `dependencies`.
- `contract_ids`.
- `acceptance_criteria_ids`.
- `required_tests`.
- `browser_evidence`.
- `acceptance_evidence`.
- `design_iteration_evidence`.
- `stop_conditions`.
- `integration_owner`.
- `rollback_or_fallback`.
- `status_artifact`.
- `packet_version`.
- `release_blocking`.

`acceptance_criteria_ids` must cite active Acceptance Matrix
Row Record ids. A packet with an empty list may only repair
or create acceptance planning artifacts; it cannot dispatch
implementation work.

`acceptance_evidence` must cite Evidence Row Records whose
`acceptance_row_id` values map to the packet's
`acceptance_criteria_ids`.

## File Lease Record

Required fields:

- `lease_id`.
- `path_or_glob`.
- `lease_order`.
- `integration_owner`.
- `current_holder`.
- `waiting_packets`.
- `conflict_policy`.
- `stacked_patch_policy`.

## Interface Contract Record

Required fields:

- `contract_id`.
- `owner_manager`.
- `consumer_managers`.
- `consumer_packets`.
- `symbols_or_fields`.
- `compatibility_requirements`.
- `defaults`.
- `error_behavior`.
- `tests`.
- `status`.
- `signoffs`.
- `artifact_hash`.
- `invalidation_dependencies`.

Valid `status` values:

- `draft`.
- `review`.
- `accepted`.
- `superseded`.
- `blocked`.

## Run Event Record

Required fields:

- `event_id`.
- `tick_id`.
- `parent_tick_id`.
- `event_type`.
- `timestamp_utc`.
- `execution_mode`.
- `lifecycle_before`.
- `lifecycle_after`.
- `packet_changes`.
- `adapter_operations`.
- `active_agents`.
- `active_worktrees`.
- `tick_classification`.
- `tick_value_type`.
- `increment_eligible`.
- `real_work_result`.
- `support_work_result`.
- `isolation_artifact`.
- `devcontainer_proof_artifact`.
- `git_snapshot`.
- `artifact_hashes`.
- `review_results`.
- `validation_results`.
- `blocking_gate_ids`.
- `gate_updates`.
- `evidence_paths`.
- `canonical_demo_url`.
- `localhost_url`.
- `trace_path`.
- `tick_eligibility`.
- `resume_freshness`.
- `delivery_event`.
- `demo_session`.
- `blockers`.
- `terminal_result`.

`execution_mode` valid values:

- `same_thread`.
- `isolated_control`.

`isolation_artifact` and `devcontainer_proof_artifact` may
be `null` when the current tick did not require those
artifacts.

Valid `event_type` values:

- `bootstrap`.
- `run_started`.
- `resume`.
- `dispatch`.
- `wait`.
- `collect_output`.
- `review`.
- `integrate`.
- `delivery_event`.
- `pull_request`.
- `ci_check`.
- `validate`.
- `evidence`.
- `resume_freshness`.
- `demo_session`.
- `decision`.
- `blocker`.
- `handoff`.
- `terminal`.

Valid `tick_value_type` values:

- `gate_advance`.
- `gate_supporting_code`.
- `gate_supporting_validation`.
- `non_increment_eligible_support`.

`blocking_gate_ids` must always be present. Use an empty
array when the run has no declared blocking gates or when
the current tick is not attached to any declared gate.

`gate_updates` must always be present. Use an empty array
when the current tick did not change any gate state.

`evidence_paths` must always be present. Use an empty array
when the current tick did not create new evidence artifacts.

`canonical_demo_url`, `localhost_url`, and `trace_path` may
be `null` when the current tick is not browser-facing, did
not use a browser demo surface, or did not produce a trace
artifact. For product plans with a declared durable demo
domain, `canonical_demo_url` records that human-facing
surface and `localhost_url` remains an exact-worktree
validation or fallback proof URL for compatibility with
existing events.

`tick_eligibility`, `resume_freshness`, `delivery_event`,
and `demo_session` must always be present. Use `null` when
the event does not exercise that record type.

## Gate Update Record

Required fields:

- `gate_id`.
- `gate_status_before`.
- `gate_status_after`.

Valid `gate_status_before` and `gate_status_after` values:

- `red`.
- `yellow`.
- `green`.

## Gate Portfolio Record

Required fields:

- `gate_id`.
- `tier`.
- `owner_manager`.
- `estimate_range`.
- `source`.
- `evidence_rule`.
- `status`.
- `next_packets`.

Valid `tier` values:

- `current_blocking`.
- `next_capability`.
- `reliability`.
- `delivery_meta`.

Valid `source` values:

- `project_plan`.
- `acceptance_matrix`.
- `interface_contract`.
- `human_prompt`.
- `run_event`.
- `inferred_roadmap`.

`estimate_range` is an object with:

- `hours_low`.
- `hours_high`.
- `ticks_low`.
- `ticks_high`.
- `estimate_source`.
- `updated_at_utc`.

Estimate numeric values may be `null` when unknown. Use
`estimate_source: "inferred"` for roadmap estimates that
come from synthesis rather than measured implementation
history.

Valid `status` values:

- `red`.
- `yellow`.
- `green`.
- `roadmap`.
- `deferred`.

`next_packets` is an array. Use an empty array when the gate
has no declared next packet yet.

## Budget Plan Record

Required fields:

- `run_id`.
- `plan_path`.
- `effective_invocation`.
- `budget_started_at_utc`.
- `budget_minutes`.
- `budget_ticks`.
- `elapsed_wall_clock_minutes`.
- `minimum_wall_clock_minutes`.
- `minimum_ticks`.
- `aggregate_m1_ticks`.
- `aggregate_m1_ticks_completed`.
- `per_lane_ticks`.
- `effective_budget_minutes`.
- `effective_budget_ticks`.
- `time_overrun_exit_minutes`.
- `slice_minutes`.
- `slice_ticks`.
- `budget_slice_count`.
- `target_endstate`.
- `gate_targets`.
- `acceptance_matrix_path`.
- `acceptance_criteria`.
- `user_journeys`.
- `milestone_slices`.
- `evidence_plan`.
- `exit_policy`.
- `numM1s`.
- `lane_plan`.
- `delivery_event_count`.
- `post_delivery_event_next_packet`.
- `final_response_gate_status`.
- `early_stop_violation`.
- `early_stop_violation_reason`.

`schema_name` must be `m2_budget_plan_record`.

`budget_started_at_utc` is the UTC timestamp captured when
the current budget lease begins. It is distinct from run
creation time for resumed runs.

`budget_minutes` is the explicit `duration:D` value
normalized to minutes, or `null` when the invocation did not
include `duration:D`.

`budget_ticks` is the explicit `iterations:N` value, or
`null` when the invocation did not include `iterations:N`.

`elapsed_wall_clock_minutes` is updated before every final
response gate evaluation and before every non-terminal
handoff.

`minimum_wall_clock_minutes` is the wall-clock lease that
must be satisfied before the conductor may final-response
for budget completion. It normally equals
`effective_budget_minutes`; in explicit aggregate M1 mode it
equals the supplied wall-clock duration basis.

`minimum_ticks` is the productive tick lease for the primary
invocation. It normally equals `effective_budget_ticks`;
when aggregate M1 mode is active, it records the aggregate
tick commitment while `per_lane_ticks` records the lane
allocation.

`aggregate_m1_ticks` is `null` by default. It is a positive
integer only when the human or plan capsule explicitly
defines the tick budget as aggregate M1 lane work across
parallel M1s, for example
`16000 ticks = 4 M1 lanes * 4 wall-clock hours * 1000 ticks/hour`.

`aggregate_m1_ticks_completed` is `null` unless aggregate M1
mode is active. When active, it records measured or
estimated completed increment-eligible lane ticks across all
active M1 lanes.

`per_lane_ticks` is `null` unless `aggregate_m1_ticks` is
set. When set, it records the intended tick allocation for
each M1 lane. Use a single positive integer when the
aggregate budget divides evenly across `numM1s`; otherwise
use an object keyed by `owner_m1` with exact positive
integer allocations.

`effective_budget_minutes` and `effective_budget_ticks` use
the canonical `1000 ticks = 1 hour` ratio and must choose
the larger implied budget when both explicit values are
present, except that explicit aggregate M1 tick mode keeps
wall-clock duration separate from aggregate lane throughput.
In aggregate M1 mode with a supplied `duration:D`,
`effective_budget_minutes` remains the normalized wall-clock
duration.

`time_overrun_exit_minutes` must equal
`effective_budget_minutes * 1.10`. In aggregate M1 mode this
uses the wall-clock duration basis; for `duration:4h`, it is
`264`.

`slice_minutes` must be `15`. `slice_ticks` must be `250`
unless a later accepted protocol version changes the global
ratio.

`budget_slice_count` must equal
`ceil(max(effective_budget_ticks / 250, effective_budget_minutes / 15))`.

`target_endstate` is a concise description of what the
system should look like when the budget-plan acceptance
criteria are met.

`gate_targets` is an array of objects with:

- `gate_id`.
- `status_before`.
- `target_status_after`.
- `owner_m1`.
- `acceptance_criteria_ids`.

`acceptance_criteria` is an array of objects with:

- `acceptance_id`.
- `acceptance_matrix_ids`.
- `description`.
- `gate_ids`.
- `required_evidence`.
- `status`.

`acceptance_matrix_path` must identify the full acceptance
matrix used as the budget-plan source of truth.

`acceptance_matrix_ids` is an array of active Acceptance
Matrix Row Record ids. Use a single id when the budget
criterion maps directly to one row. Use multiple ids only
when the budget criterion intentionally aggregates rows.

Valid `acceptance_criteria.status` values:

- `open`.
- `met`.
- `blocked`.
- `superseded`.

`user_journeys` is an array of objects with:

- `journey_id`.
- `description`.
- `interaction_type`.
- `gate_ids`.
- `validation_method`.

Valid `interaction_type` values:

- `click_through`.
- `mouse_through`.
- `keyboard`.
- `screenshot`.
- `playwright`.
- `manual`.
- `test_only`.

`milestone_slices` is an array of objects with:

- `slice_id`.
- `minute_range`.
- `tick_range`.
- `owner_m1`.
- `lane_type`.
- `gate_ids`.
- `planned_deliverable`.
- `validation_or_evidence`.
- `expected_user_visible_delta`.

`lane_type` must use the same values as
`Tick Eligibility Record.lane_role`.

`evidence_plan` is an array of objects with:

- `evidence_id`.
- `gate_ids`.
- `method`.
- `canonical_demo_url`.
- `localhost_url`.
- `expected_artifact_paths`.

`exit_policy` is an object with:

- `exit_when_acceptance_met`.
- `terminal_allowed`.
- `human_pause_allowed`.
- `true_blocker_allowed`.
- `overrun_exit_minutes`.
- `overrun_handoff_required`.
- `final_response_gate_required`.
- `delivery_event_is_nonterminal`.

`delivery_event_count` is the number of PR, push,
validation, screenshot, browser-proof, CI-classification, or
deploy-proof delivery events recorded during this
invocation.

`post_delivery_event_next_packet` is `null` only when no
non-stopping delivery event has occurred or a valid stop
reason has ended the run. Otherwise it is an object with:

- `packet_id`.
- `owner_m1`.
- `lane_type`.
- `gate_ids`.
- `description`.
- `validation_or_evidence`.

`final_response_gate_status` must be one of:

- `continue_required`.
- `budget_acceptance_met`.
- `green_tick_handoff`.
- `human_paused`.
- `true_blocker`.
- `terminal`.
- `overrun_handoff`.

`budget_acceptance_met` may be used only when the
budget-plan acceptance criteria are met and the minimum
wall-clock/tick lease has been satisfied.

`green_tick_handoff` may be used only by a protocol wrapper
that explicitly declares bounded green tick semantics, such
as `greenTick()`. It means one durable green conductor tick
completed, durable M2 state and the runnable resume prompt
were updated, the run remains non-terminal, and
`resume_invocation` names the exact next bounded tick
command.

`early_stop_violation` is a boolean. It is `true` when a
final response or handoff was attempted while
`final_response_gate_status` required continuation.

`early_stop_violation_reason` is `null` unless
`early_stop_violation` is `true`. Valid values are:

- `stopped_after_pr`.
- `stopped_after_validation`.
- `stopped_after_push`.
- `stopped_after_ci_queue`.
- `stopped_after_delivery_event`.
- `stopped_after_clean_slice`.

`numM1s` is the requested M1 lane count for this invocation.

`lane_plan` is an array of objects with:

- `owner_m1`.
- `lane_type`.
- `gate_family`.
- `allowed_work`.
- `parallel_evidence_lane`.
- `per_lane_ticks`.

## Tick Eligibility Record

Required fields:

- `gate_ids`.
- `tick_value_type`.
- `increment_eligible`.
- `changed_paths`.
- `evidence_paths`.
- `validation_commands`.
- `validation_status`.
- `canonical_demo_url`.
- `localhost_url`.
- `lane_role`.
- `increment_reason`.
- `next_action`.

`gate_ids`, `changed_paths`, `evidence_paths`, and
`validation_commands` are arrays. Use empty arrays when the
tick does not attach to gates, change files, create
evidence, or run validation.

`validation_status` valid values:

- `not_run`.
- `passed`.
- `failed`.
- `blocked`.

`canonical_demo_url` and `localhost_url` may be `null` for
non-browser-facing ticks. When a browser-facing tick is
increment-eligible, `canonical_demo_url` must identify the
current human-facing demo URL used for proof when one
exists. `localhost_url` identifies the exact-worktree proof
URL when localhost was used for validation or fallback
diagnostics.

`lane_role` valid values:

- `depth_lane`.
- `breadth_lane`.
- `stabilization_lane`.
- `evidence_lane`.
- `none`.

Use `none` only for non-product runs or support events that
are not attached to a product lane.

The `m1()` protocol (`references/m1.protocol.md`)
consumes the product-lane subset of these `lane_role` values
through its `lane_role` argument: `depth_lane`,
`breadth_lane`, `stabilization_lane`, and `evidence_lane`.
It does not accept `none`; keep that support-only value
reserved for non-product runs or support events.

## Resume Freshness Record

Required fields:

- `worktree_path`.
- `worktree_status`.
- `branch`.
- `head_sha`.
- `remote_tracking_ref`.
- `remote_sync_state`.
- `pull_request_url`.
- `pull_request_state`.
- `localhost_url`.
- `localhost_health`.
- `artifact_paths`.
- `artifact_existence`.
- `local_only_excludes`.
- `repair_action`.

Valid `worktree_status` values:

- `present`.
- `missing`.
- `replaced`.
- `unknown`.

Valid `remote_sync_state` values:

- `in_sync`.
- `ahead`.
- `behind`.
- `diverged`.
- `untracked`.
- `unknown`.

Valid `localhost_health` values:

- `healthy`.
- `restartable`.
- `stale`.
- `missing`.
- `not_required`.

`repair_action` is `null` when no repair was needed.

## Non-Stopping Delivery Event Record

Required fields:

- `commit_sha`.
- `branch`.
- `pull_request_url`.
- `pull_request_state`.
- `chain_parent`.
- `gate_ids`.
- `proof_artifacts`.
- `validation_commands`.
- `validation_results`.
- `lint_commands`.
- `lint_scope`.
- `repo_wide_lint_required`.
- `repo_wide_lint_status`.
- `lint_rewrite_paths`.
- `pre_push_lint_complete`.
- `continue_after_delivery_event`.
- `delivery_event_is_nonterminal`.
- `ci_state`.
- `proof_visibility`.
- `canonical_demo_url`.
- `localhost_url`.
- `build_revision`.
- `next_target`.

`proof_visibility` valid values:

- `pr_linked`.
- `pr_described_local_path`.
- `local_only`.
- `not_browser_visible`.

`chain_parent` may be `null` when the PR is not stacked.
`canonical_demo_url` and `localhost_url` may be `null` for
non-browser-facing non-stopping delivery events. For
browser-visible work with a durable demo domain,
`canonical_demo_url` is the reviewer-facing link and
`localhost_url` is proof-only or fallback evidence.

`lint_commands` records the local lint/static/syntax
commands run before commit or push. `lint_scope` is
`scoped`, `broad`, `scoped_and_broad`, or `not_applicable`.
Set `repo_wide_lint_required` to true when the change
involved a rebase, conflict resolution, BUILD/tooling edits,
generated-output changes, ambiguous affected paths, or other
repo-wide formatting risk. `repo_wide_lint_status` is
`not_required`, `passed`, `failed`, or `blocked`. Use
`lint_rewrite_paths` for files modified by formatter/lint
commands, and set `pre_push_lint_complete` only after the
post-rewrite local lint state is clean.

`continue_after_delivery_event` must be `true` unless the
same tick records a terminal state, explicit human pause or
stop, or a formal blocker that prevents every safe next
packet from moving. `delivery_event_is_nonterminal` must be
`true` for every budgeted-run delivery event.

## FanOut Codegen Event Record

Required fields:

- `fanout_event_id`.
- `attempt_reason`.
- `source_m1`.
- `gate_ids`.
- `requested_workers`.
- `resolved_workers`.
- `worker_model`.
- `owned_scopes`.
- `launched_agent_ids`.
- `no_launch_blocker`.
- `integration_status`.
- `validation_status`.
- `lint_status`.
- `source_delivery_event_id`.
- `delivery_event_id`.
- `next_packet`.

`attempt_reason` records why the fanOut scan happened, such
as `run_startup`, `post_delivery_event`, `idle_m1_capacity`,
or `manual_request`. `source_m1` names the manager lane that
requested the worker burst. `gate_ids` ties the burst to
product or delivery gates. `requested_workers` is the raw
request, such as `auto`, while `resolved_workers` is the
number actually launched after lease and capacity checks.
`worker_model` defaults to `gpt-5.3-codex-spark` for
code-editing workers.

`owned_scopes` records the files, modules, functions,
validators, browser flows, or evidence artifacts assigned to
each worker. `launched_agent_ids` may be empty only when the
event records an explicit no-launch blocker.
`no_launch_blocker` is `null` when one or more workers
launch. `source_delivery_event_id` links a post-delivery
fanOut scan to the event that triggered it.
`delivery_event_id` is `null` until output is integrated and
pushed; once a fanOut result lands in a non-stopping
delivery event, link that event here.

Valid `no_launch_blocker` values:

- `file_lease_conflict`.
- `shared_hot_file`.
- `missing_context`.
- `validation_dependency`.
- `risk_boundary`.
- `tool_capacity`.
- `no_safe_packet`.
- `not_applicable`.

Valid `integration_status` values:

- `not_integrated`.
- `integrated`.
- `rejected`.
- `superseded`.
- `blocked`.

Valid `validation_status` values:

- `not_run`.
- `passed`.
- `failed`.
- `blocked`.
- `partial`.

Valid `lint_status` values:

- `not_run`.
- `passed`.
- `failed`.
- `blocked`.
- `not_applicable`.

## Autonomy Health Event Record

Required fields:

- `autonomy_event_id`.
- `tick_id`.
- `source`.
- `active_m1_lanes`.
- `idle_m1_lanes`.
- `active_agents`.
- `active_worktrees`.
- `active_exec_sessions`.
- `process_pressure_status`.
- `git_state`.
- `pull_request_state`.
- `ci_state`.
- `localhost_state`.
- `local_only_artifact_state`.
- `safe_packet_candidates`.
- `fanout_attempt_ids`.
- `blocked_lane_reasons`.
- `next_action`.
- `continue_required`.

`source` records why the pulse ran, such as `startup`,
`resume`, `post_delivery_event`, `pre_final_gate`,
`process_pressure`, or `scheduled_tick`.
`active_exec_sessions` may be `null` when the environment
cannot report the count. `safe_packet_candidates` records
the concrete packets, validation tasks, review tasks,
evidence tasks, PR-stack tasks, or blocker-removal actions
still available. `fanout_attempt_ids` may be empty only when
`blocked_lane_reasons` explains why no fanOut scan or launch
was safe.

Valid `process_pressure_status` values:

- `normal`.
- `elevated`.
- `high`.
- `blocking`.
- `unknown`.

`continue_required` must be true whenever any safe packet
candidate exists and the Final Response Gate has not
returned a non-continue status.

## Final Response Gate Record

Required fields:

- `final_gate_id`.
- `tick_id`.
- `budgeted_invocation`.
- `elapsed_minutes`.
- `minimum_wall_clock_minutes`.
- `completed_increment_eligible_ticks`.
- `minimum_increment_eligible_ticks`.
- `aggregate_m1_ticks_completed`.
- `active_lanes`.
- `non_stopping_delivery_event_count`.
- `pull_request_check_deploy_state`.
- `budget_acceptance_met`.
- `lease_satisfied`.
- `unmet_acceptance_ids`.
- `next_safe_packet_candidates`.
- `status`.
- `early_stop_violation`.
- `resume_invocation`.

`minimum_wall_clock_minutes`,
`minimum_increment_eligible_ticks`, and
`aggregate_m1_ticks_completed` may be `null` when they do
not apply to the invocation. `resume_invocation` must be the
exact runnable `m2(...)` form a human can paste to continue
when the status is not terminal.

Valid `status` values:

- `continue_required`.
- `budget_acceptance_met`.
- `green_tick_handoff`.
- `human_paused`.
- `true_blocker`.
- `terminal`.
- `overrun_handoff`.

`early_stop_violation` must be true when a final response,
pause handoff, or compatibility stop is attempted while
`status` is `continue_required`.

`green_tick_handoff` must set `early_stop_violation` to
false. It is valid only when the invocation came from a
bounded green tick wrapper, exactly one durable conductor
tick completed or recorded a true all-packet blocker,
`next_safe_packet_candidates` and `resume_invocation` are
current, and the normal `green()`/`m2()` final-response
contract would otherwise require continuation.

## PR Stack Readiness Record

Required fields:

- `pr_stack_readiness_id`.
- `tick_id`.
- `branch`.
- `base_branch`.
- `head_sha`.
- `base_sha`.
- `pull_request_urls`.
- `commit_count_between_base_and_head`.
- `branch_sync_state`.
- `auto_generated_pr_query_clean`.
- `unresolved_conversation_count`.
- `required_checks_state`.
- `mergeability_state`.
- `supported_merge_strategy`.
- `server_side_merge_attempt_status`.
- `backup_branch`.
- `collapse_or_restack_action`.
- `force_push_with_lease_used`.
- `readiness_status`.
- `next_action`.

`backup_branch`, `collapse_or_restack_action`, and
`force_push_with_lease_used` are used only when Delivery
must recover an owned branch from server-side merge
backpressure. They are `null` or `false` when no recovery
was attempted.

Valid `branch_sync_state` values:

- `in_sync`.
- `ahead`.
- `behind`.
- `diverged`.
- `unknown`.

Valid `required_checks_state` values:

- `not_required`.
- `pending`.
- `passing`.
- `failing`.
- `blocked_service`.
- `unknown`.

Valid `mergeability_state` values:

- `mergeable`.
- `conflicted`.
- `blocked`.
- `unknown`.

Valid `supported_merge_strategy` values:

- `merge`.
- `squash`.
- `rebase`.
- `queue`.
- `unknown`.

Valid `server_side_merge_attempt_status` values:

- `not_attempted`.
- `succeeded`.
- `failed_large_stack`.
- `failed_conflict`.
- `failed_checks`.
- `failed_permissions`.
- `blocked_service`.

Valid `readiness_status` values:

- `not_ready`.
- `ready`.
- `waiting_on_checks`.
- `waiting_on_review`.
- `needs_restack`.
- `needs_collapse`.
- `blocked`.

## Demo Session Record

Required fields:

- `canonical_url`.
- `port`.
- `serving_worktree`.
- `build_revision`.
- `started_at_utc`.
- `stopped_at_utc`.
- `freshness_status`.

Valid `freshness_status` values:

- `fresh`.
- `stale`.
- `stopped`.
- `unknown`.

`stopped_at_utc` may be `null` while the demo is still the
canonical current demo. A browser-facing proof event must
set `build_revision` to the commit, content hash, or build
identifier being validated.

`canonical_url` may be a persistent route such as
`https://example.com/` or a localhost URL. When it
is a persistent route, `port` and `serving_worktree` may be
`null` or point to the fallback validation surface rather
than the human-facing route.

## Resume Prompt Record

Required fields:

- `schema_name`.
- `schema_version`.
- `run_id`.
- `plan_path`.
- `created_at_utc`.
- `owner`.
- `generated_at_utc`.
- `resume_prompt_path`.
- `resume_prompt_hash`.
- `effective_invocation`.
- `minimum_wall_clock_minutes`.
- `minimum_increment_eligible_ticks`.
- `aggregate_m1_ticks`.
- `per_lane_ticks`.
- `num_m1s`.
- `worktree_path`.
- `branch`.
- `pull_request_url`.
- `canonical_demo_url`.
- `localhost_url`.
- `last_commit_sha`.
- `validation_artifacts`.
- `local_only_excludes`.
- `current_focus`.
- `next_targets`.
- `stop_policy`.
- `prompt_text`.

`schema_name` must be `m2_resume_prompt_record`.

`run_id` may be a durable run id or a plan-level capsule id
when no canonical run artifact exists yet. Plan-level
capsule ids must be stable and must not be confused with
completed terminal runs.

`resume_prompt_hash` records the hash of `prompt_text`, or
the verbatim file at `resume_prompt_path` when the prompt is
stored there, in `sha256:<hex>` form. Readers must verify it
before hydrating bare `m2(plan_path)` from the record.

`effective_invocation` is the invocation the conductor
should act as though the human supplied after hydrating the
prompt. Explicit prompt modifiers supplied by the human
override only the matching saved fields for the current
invocation. It may include `iterations:N`, `duration:D`,
`numM1s:M`, or combinations when the saved continuation has
explicit tick, wall-clock, or M1 lane goals.

`num_m1s` is a positive integer. It records the saved
parallel M1 lane goal for the runnable prompt. Older resume
prompt records without this field must be interpreted as `1`
for compatibility.

`minimum_wall_clock_minutes` and
`minimum_increment_eligible_ticks` may be `null` only when
the saved prompt does not impose a minimum runtime or tick
goal. `minimum_wall_clock_minutes` stores the normalized
minute value for any saved `duration:D` invocation modifier.

`aggregate_m1_ticks` and `per_lane_ticks` are `null` unless
the saved prompt explicitly uses aggregate M1 lane
budgeting. When present, they preserve aggregate throughput
accounting separately from `minimum_wall_clock_minutes`.

`validation_artifacts`, `local_only_excludes`,
`current_focus`, and `next_targets` are arrays. Use empty
arrays when no values exist.

`prompt_text` may be a string or an array of lines. When it
is an array, readers join lines with `\n` to reconstruct the
exact prompt. It must be complete enough to run without chat
history. It should include worktree, branch, PR, canonical
demo URL, localhost proof URL when used, validation proof,
local-only artifact exclusions, current focus, next targets,
and stop policy whenever those facts are known.

## Adapter Operation Record

Required fields:

- `adapter_operation_id`.
- `operation`.
- `target_type`.
- `target_id`.
- `packet_id`.
- `manager`.
- `model`.
- `reasoning_effort`.
- `worktree_path`.
- `output_artifact`.
- `retry_count`.
- `started_at_utc`.
- `completed_at_utc`.
- `result`.
- `next_action`.

Valid `operation` values:

- `bootstrap_control_worktree`.
- `create_worktree`.
- `enter_devcontainer`.
- `re_invoke_conductor`.
- `same_thread_conductor_edit`.
- `start_manager`.
- `start_worker`.
- `start_tester`.
- `start_reviewer`.
- `wait`.
- `collect_output`.
- `capture_diff`.
- `run_review`.
- `integrate_patch`.
- `commit_changes`.
- `push_branch`.
- `open_pull_request`.
- `update_pull_request`.
- `poll_pull_request_checks`.
- `repair_derived_artifacts`.
- `record_ci_health`.
- `close_worker`.
- `retry_packet`.
- `resume_run`.

## Isolation Record

Required fields:

- `run_id`.
- `plan_path`.
- `plan_name`.
- `plan_slug`.
- `worktree_slug`.
- `execution_mode`.
- `active_repo_root`.
- `run_root`.
- `invocation_cwd`.
- `invocation_git_root`.
- `invocation_branch`.
- `invocation_head`.
- `plan_source_path`.
- `control_plan_path`.
- `project_root`.
- `project_source_root`.
- `control_project_root`.
- `control_worktree`.
- `control_branch`.
- `integration_worktree`.
- `worker_worktree_root`.
- `devcontainer_workspace_root`.
- `repo_root_inside_conductor`.
- `conductor_branch`.
- `conductor_head`.
- `x_available`.
- `run_artifact_dir`.
- `bootstrap_state`.
- `proof_artifacts`.
- `refusal_reason`.
- `recovery_action`.

Legacy compatibility note:

- Older records may include `main_worktree`. New runs should
  prefer `active_repo_root`.
- `control_worktree`, `integration_worktree`, and
  `devcontainer_workspace_root` may be the same path in
  `same_thread` mode.
- `devcontainer_workspace_root` may be `null` when the run
  is not using a devcontainer and the required commands were
  still available safely.

Valid `bootstrap_state` values:

- `bootstrap_only`.
- `same_thread_verified`.
- `relocated`.
- `verified`.
- `blocked`.

## Worker Output Record

Required fields:

- `worker_id`.
- `packet_id`.
- `worktree_path`.
- `branch`.
- `base_sha`.
- `head_sha`.
- `diff_artifact`.
- `diff_hash`.
- `changed_paths`.
- `commands`.
- `evidence_artifacts`.
- `review_id`.
- `validation_timestamp_utc`.
- `residual_risk`.
- `next_owner`.

## Review Record

Required fields:

- `review_id`.
- `reviewer_role`.
- `target_artifact_path`.
- `target_artifact_hash`.
- `target_diff_hash`.
- `scope`.
- `verdict`.
- `findings`.
- `finding_states`.
- `invalidation_conditions`.
- `created_at_utc`.
- `resolved_at_utc`.

Valid `verdict` values:

- `pass`.
- `revise`.
- `block`.

Valid finding states:

- `open`.
- `addressed`.
- `accepted_risk`.
- `superseded`.

## Evidence Row Record

Required fields:

- `evidence_id`.
- `packet_id`.
- `acceptance_row_id`.
- `command_or_browser_action`.
- `worktree_path`.
- `branch`.
- `commit_sha`.
- `artifact_path`.
- `artifact_hash`.
- `fixture_id`.
- `fixture_version`.
- `packet_version`.
- `timestamp_utc`.
- `invalidation_dependencies`.
- `status`.
- `owner`.
- `next_action`.

Valid `status` values:

- `pass`.
- `fail`.
- `blocked`.

`acceptance_row_id` must cite an active Acceptance Matrix
Row Record id. Evidence that predates a material
acceptance-matrix revision is stale until reproduced or
explicitly accepted by Delivery.

## Cockpit Artifact Record

Required fields:

- `artifact_name`.
- `artifact_path`.
- `source_events_path`.
- `latest_tick_id`.
- `source_event_hash`.
- `generated_at_utc`.
- `stale`.
- `repair_action`.

Cockpit artifact records describe optional derived markdown
views unless the protocol explicitly marks that artifact as
required for recovery.

## Delivery Record

Required fields:

- `delivery_id`.
- `run_id`.
- `terminal_state`.
- `completed_packets`.
- `blocked_packets`.
- `release_blocking_rows`.
- `accepted_blockers`.
- `fresh_evidence_ids`.
- `stale_evidence_ids`.
- `isolation_artifact`.
- `devcontainer_proof_artifact`.
- `final_signoffs`.
- `last_known_good_sha`.
- `handoff_artifact`.
- `resume_command`.
- `pull_request_chain`.
- `pending_checks`.

`isolation_artifact` and `devcontainer_proof_artifact` may
be `null` when the final run state used `same_thread` mode
and no separate proof markdown was required.

Valid `terminal_state` values:

- `terminal_completed`.
- `terminal_partial_handoff`.
- `terminal_blocked`.

## Non-Stopping Delivery Event Record

Required fields:

- `delivery_event_id`.
- `tick_id`.
- `kind`.
- `branch`.
- `base_branch`.
- `commit_sha`.
- `pull_request_url`.
- `pull_request_number`.
- `chain_parent_pull_request`.
- `check_state`.
- `ready_for_review`.
- `recorded_at_utc`.
- `lint_commands`.
- `lint_scope`.
- `repo_wide_lint_required`.
- `repo_wide_lint_status`.
- `lint_rewrite_paths`.
- `pre_push_lint_complete`.
- `continue_after_delivery_event`.
- `next_tick_intent`.

Valid `kind` values:

- `commit`.
- `push`.
- `open_pull_request`.
- `update_pull_request`.
- `mark_ready_for_review`.
- `poll_checks`.

`lint_scope` valid values:

- `scoped`.
- `broad`.
- `scoped_and_broad`.
- `not_applicable`.

`repo_wide_lint_status` valid values:

- `not_required`.
- `passed`.
- `failed`.
- `blocked`.

Valid `check_state` values:

- `not_applicable`.
- `pending`.
- `passing`.
- `failing`.
- `blocked_service`.

`continue_after_delivery_event` must be `true` unless the
same tick records a terminal state, explicit human pause or
stop, or a formal blocker that prevents every safe next
packet from moving.

`delivery_event_is_nonterminal` must be `true` for every
budgeted-run delivery event. A `false` value is valid only
when the same tick also records `terminal`, `human_paused`,
`true_blocker`, or `overrun_handoff`.

Legacy compatibility: older run logs may contain
`delivery_checkpoint`, `delivery_checkpoint_id`,
`delivery_checkpoint_count`, `post_checkpoint_next_packet`,
`delivery_checkpoint_is_nonterminal`, or
`continue_after_checkpoint`. Readers must map those fields
to the `delivery_event*` names above. These legacy fields
are invalid as stop criteria in budgeted runs; they describe
non-stopping delivery events only.
