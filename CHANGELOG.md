# Changelog

## v0.2.5 - 2026-04-25

- Implemented Controlled Execution Platform with hybrid manifest capability engine.
- Introduced Prompt OS for structured, deterministic system prompts with
  context-aware module selection.
- Enhanced audit records with prompt explainability and record tracking.
- Added comprehensive YAML-based capability catalog and manifest system.

## v0.2.4.4 - 2026-04-25

- Implemented Conversation Gateway for intent-based classification and
  operational safety routing.
- Overhauled TUI with modular widget architecture, theme support, and compact
  cockpit layout.
- Migrated codebase to standard `src/` layout with improved packaging.
- Added comprehensive integration tests for Gateway routing and TUI components.

## v0.2.4.3 - 2026-04-25

- Added spec for Agent-Led Hybrid Execution and Conversation Gateway.
- Synchronized domain contracts with gateway-enforced trust boundaries.

## v0.2.4.2 - 2026-04-24

- Replaced hardcoded planning chains with LLM-driven capability resolution and
  automatic parameter extraction.
- Simplified execution graph by delegating intent matching to a dedicated
  Capability Resolver with keyword fallback.

## v0.2.4.1 - 2026-04-24

- Added deterministic per-step command trace capture to the execution pipeline
  with planned argv, executed argv, exit code, bounded output excerpts, and
  timing metadata.
- Exposed command trace through tool registry/runtime flow and attached it to
  authoritative step/audit records as execution metadata, without changing
  capability input/output schema contracts.
- Redesigned normal-mode user responses for completed read-only steps to show a
  command-transparent transcript (`About to run`, `Ran`, `Output`, `What this
  means`) while keeping debug mode as the full internal metadata view.
- Updated response and command-trace tests to validate the new normal-mode
  contract, debug separation, and trace recording behavior for single/multi
  command tool paths.

## v0.2.4 - 2026-04-24

- Added normalized machine-readable policy outputs and reason codes:
  `decision` (`allow|require_confirmation|deny`), `confirmation_type`
  (`none|user|admin`), `deny_code`, and separate `reason_text`.
- Added normalized non-execution reason codes/text on steps and audit records
  (`non_execution.code`, `non_execution.reason_text`) while keeping legacy
  compatibility fields.
- Made `high` risk explicit and enforced: destructive/process-control actions
  now require admin confirmation (`ADMIN_APPROVE ...`), medium risk remains user
  confirmation, critical stays default deny.
- Introduced execute-time policy integrity snapshots and hash verification for
  every step; stale or drifted policy/state now fail closed with
  `policy_integrity_mismatch`.
- Hardened approval fingerprint binding with policy snapshot hash and
  deterministic step binding (plan id, step id/index, dependencies), preventing
  replay across mutated/reordered plans.
- Expanded adversarial tests for stale policy metadata, changed risk after
  approval, changed arguments after confirmation, plan reorder tampering, and
  normalized audit decision-chain fields.

## v0.2.3 - 2026-04-24

- Added deterministic per-step risk classification and policy-table execution
  gating on top of the registered capability model.
- Introduced a normalized risk contract (`risk_level`, confirmation
  requirement, side effects, reversibility, privilege requirement, deny reason)
  attached to each planned step before execution.
- Tightened execution safety so steps cannot run without policy metadata, and
  confirmation-gated steps fail closed when approval state is missing or
  invalidated.
- Extended approval binding so action fingerprints include risk-contract
  metadata, preventing silent reuse across materially different invocations.
- Expanded audit records with structured decision trail fields for request,
  normalized step, risk classification, policy decision, confirmation state, and
  non-execution reason.
- Added comprehensive v0.2.3 tests for allow/confirm/deny outcomes, risky
  pattern fail-closed behavior, confirmation reuse hardening, dependency-safe
  gating, and audit trail completeness.

## v0.2.2 - 2026-04-23

- Expanded deterministic verification-repair hardening with explicit
  equivalence/reapproval behavior and stricter fail-closed tests for escalation,
  non-equivalence, and inconclusive outcomes.
- Clarified runtime containment boundary expectations (deterministic guardrails,
  not OS sandboxing) and hardened verification dispatch mappings used for
  bounded filesystem-style operations.
- Expanded verification and regression coverage across repair, role-boundary,
  and workflow invariants with canonical `step_id`/`args` contracts.
- Completed hygiene sweep for reviewer clarity: fixed archive broken links,
  removed stale compatibility normalization codepaths, updated CLI/reviewer
  wording, and preserved historical materials with explicit archive marking.
- Preserved v0.2 architecture authority and fail-closed posture; no new
  execution surface or policy model was introduced.

## v0.2.1 - 2026-04-23

- Hardened verification and repair lifecycle with explicit typed artifacts,
  verification-to-repair lineage, and deterministic re-entry behavior.
- Added runtime-attributed role-boundary enforcement records and audit
  provenance visibility for accepted/rejected/downgraded role proposals.
- Added focused verification-dataset scenarios and tests for repair and role
  boundary invariants.
- Performed architecture hygiene sweep: removed legacy v0.1 compatibility
  aliases (`tool`, `parameters`, `id`, `dependencies`) from authoritative models
  and transitioned execution runtime to canonical `args` and `step_id`.
- Improved reviewer/merge readiness documentation and start-here pointers.

## v0.2.0

- Introduced capability-governed deterministic pipeline aligned to
  [docs/specs/xfusion-v0.2.md](docs/specs/xfusion-v0.2.md).
