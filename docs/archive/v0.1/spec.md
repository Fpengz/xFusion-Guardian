> [!IMPORTANT]
> Historical, non-normative v0.1 material. This document is archived for
> historical reference only. For all current behavior, use the normative
> [docs/specs/xfusion-v0.2.md](../../specs/xfusion-v0.2.md).

# XFusion v0.1 Spec: Safety-Aware Linux Admin Agent

## Summary

Build a **Python CLI chat agent** for the AI Hackathon preliminary problem: an "操作系统智能代理" that manages a real Linux server through natural language. v0.1 is demo-first and rubric-shaped: real Linux execution, explicit planning, mandatory verification, continuous state updates, environment-aware safety reasoning, bounded multi-step workflows, bilingual English/Chinese interaction, audit logs, and contest-ready validation materials.

Use a **local Lima Ubuntu 24.04 VM** as the official demo sandbox on Apple Silicon macOS. Multipass is the fallback. Docker is development-only, not the official demo environment.

Post-v0.1 architecture note: the historical Pydantic v2 + LangGraph blueprint is archived at [docs/archive/v0.1/pydantic-langgraph-blueprint.md.archived](pydantic-langgraph-blueprint.md.archived). It is retained for historical context and does not change the v0.1 baseline described here.

## Core Architecture

### Agent Loop

1. Parse user request.
2. Detect ambiguity; ask clarification if underspecified.
3. Build an `ExecutionPlan`.
4. Evaluate environment and policy for the next executable step.
5. Ask confirmation when required.
6. Execute one step.
7. Verify the step result.
8. Update environment model, memory, and audit log.
9. Re-evaluate remaining steps before continuing.
10. Stop on completion, clarification, refusal, timeout, unsafe state change, or unrecoverable failure.

### LLM Boundary

The LLM is used for language understanding, ambiguity-detection support, plan drafting, and response wording. Policy classification, dependency enforcement, confirmation rules, execution permission, and final tool authorization remain deterministic.

### Execution Plan

Every request becomes an `ExecutionPlan`, even if it has one step.

Plan fields:

- `plan_id`
- `goal`
- `language`
- `interaction_state`
- `steps[]`
- `max_steps`
- `current_step`
- `status`

Step fields:

- `step_id`
- `intent`
- `tool`
- `parameters`
- `dependencies`
- `risk_level`
- `requires_confirmation`
- `confirmation_phrase`
- `expected_output`
- `verification_method`
- `success_condition`
- `failure_condition`
- `fallback_action`
- `status`

A step may execute only when all dependencies have `success` status.

### Interaction States

- `awaiting_disambiguation`
- `awaiting_confirmation`
- `executing`
- `completed`
- `refused`
- `aborted`
- `failed`

### Memory Boundaries

Memory is short-lived and scoped to the active session and active plan. It may store recent references such as a process, port, file result set, cleanup candidates, pending confirmation, and current plan state.

Memory never persists privileged authorization or confirmation across plans. It is cleared or downgraded after plan completion, refusal, failure, or abort.

### Tool Guarantees

Tools accept validated structured input and return structured output. They are scoped, non-interactive, and do not expose arbitrary shell passthrough. Read-only tools should be idempotent. Mutating tools require policy approval and confirmation when classified as medium or high risk.

## Implementation Changes

### Agent Core

- Python CLI chat loop.
- OpenAI-compatible LLM for language understanding and response wording.
- Deterministic environment model, planning layer, policy engine, tool router, executor, verifier, confirmation manager, memory store, and audit logger.
- No OpenHarness or other agent framework in v0.1.

### Environment Model

Detect distro family/version, current user, sudo availability, systemd availability, package manager, disk pressure, shell/session locality, protected path categories, active process/port facts, and cleanup candidate state.

### Verification Taxonomy

- State re-read.
- Existence/non-existence check.
- Port/process re-check.
- Filesystem metadata re-check.
- Command exit status plus state confirmation.

### Context-Aware Safety

- Classify risk as `low`, `medium`, `high`, or `forbidden`.
- Include a reason grounded in current environment.
- Low-risk read-only operations execute directly.
- Medium-risk operations require exact typed confirmation.
- High-risk operations require typed confirmation or refusal based on scope.
- Forbidden operations are always refused.

### Tool Surface

- `system.detect_os`
- `system.current_user`
- `system.check_sudo`
- `system.service_status`
- `disk.check_usage`
- `disk.find_large_directories`
- `file.search`
- `file.preview_metadata`
- `process.list`
- `process.find_by_port`
- `process.kill`
- `user.create`
- `user.delete`
- `cleanup.safe_disk_cleanup`
- `plan.explain_action`

### Audit Trace Schema

Each execution record includes:

- `plan_id`
- `step_id`
- `interaction_state`
- `before_state`
- `action_taken`
- `after_state`
- `verification_result`
- `status`
- `summary`

### Performance and Stability

- Set command timeouts per tool.
- Limit workflow length with `max_steps`.
- Retry only safe read-only commands once.
- Do not retry destructive or privileged commands automatically.
- Abort safely if environment state changes invalidate the plan.
- Limit search result volume and ask for clarification when scope is too broad.

## Required Behaviors

### Response Contract

Each response includes:

- Intent understood.
- Relevant environment facts.
- Execution plan summary.
- Current step and risk reasoning.
- Confirmation or clarification requirement.
- Execution result or refusal reason.
- Verification result.
- Updated state and next safe recommendation.

### Ambiguity Handling

If the target, scope, action, or risk boundary is unclear, the agent must not execute. It must ask a specific clarification question and move to `awaiting_disambiguation`.

### Canonical Workflows

- **Port workflow:** find process on port 8080, explain it, ask whether to stop it, kill after confirmation, update state, verify the port is free.
- **Disk cleanup workflow:** check disk pressure, find large directories, propose bounded cleanup candidates, ask confirmation, clean selected safe targets, update state, verify reclaimed space.
- **User workflow:** create a normal user with sudo confirmation, verify creation, optionally handle a non-dangerous group request, then summarize final state.

### Judge "Wow" Scenario

User says disk feels full. The agent detects disk pressure, identifies major contributors, proposes safe cleanup, explains why candidates are safe in this environment, asks confirmation, executes cleanup, verifies reclaimed space, and suggests preventive monitoring.

### Safe Cleanup Boundaries

Cleanup candidates are limited to approved paths such as temp directories, package cache, and old logs. The agent previews candidate metadata before deletion. Cleanup is scoped by path, age, and/or size. Vague destructive requests like "clean everything" are refused.

## Problem Statement Coverage

- Runnable CLI tool.
- Natural-language disk, file, process/port, and user management.
- Intent parsing, OS-level execution, natural-language feedback.
- High-risk recognition, context-aware warning, typed confirmation, bounded execution, refusal, and explainable policy decisions.
- Explicit planning, multi-turn context, continuous state update, adaptive multi-step workflows, and a partial "no command line" Linux admin experience.
- First-class environment model for environment information sensing.
- Context-aware policy reasoning for environment-based safety judgment.
- Adaptive loop after every step for continuous state update and decision.
- Explicit plans, dependencies, verification, and canonical workflows for complex continuous task handling.
- Timeouts, retries, step limits, and safe aborts for stability.
- Structured explanations, clarification states, and proactive recommendations for UX and innovation.
- Source code, prompt text, tool definitions, agent config, architecture docs, demo script, self-test cases, JSONL audit logs, and execution-path explanations.
- The system is not a passthrough proxy: it performs ambiguity detection, intent parsing, plan construction, dependency enforcement, environment sensing, deterministic policy evaluation, tool selection, bounded execution, verification, state update, and audited summarization.

## Test Plan

### Unit Tests

- English and Chinese intent parsing.
- Execution plan schema, dependency validation, and step contract validation.
- Ambiguity detection for underspecified requests.
- Environment model parsing.
- Context-aware risk classification.
- Verification taxonomy handling.
- Tool router rejects unknown tools and shell passthrough.
- Confirmation phrase exact matching.
- Memory references resolve only within safe pending context.
- Memory does not carry privileged authorization across plans.
- JSONL audit entries include plan, step, before/after state, and verification result.

### Integration Tests in Lima VM

- OS/user/sudo/systemd/package-manager detection.
- Disk usage and large-directory inspection.
- File search with result limiting and metadata preview.
- Port/process lookup using a known test process.
- User create/delete with sudo and typed confirmation.
- Forbidden deletion such as `/etc` is refused.
- State update after each step in port and cleanup workflows.
- Dependency enforcement prevents later steps after failed prerequisites.
- Timeout, retry, and safe-abort behavior.

### Acceptance Demo

Seven-scenario video script passes:

1. Detect and explain Linux environment.
2. Check disk usage.
3. Search and preview a file/directory.
4. Resolve and safely stop a process by port.
5. Create/delete a normal user with confirmation and verification.
6. Refuse a dangerous or ambiguous deletion with clarification/refusal.
7. Run the disk-pressure wow scenario with planning, cleanup, verification, preventive recommendation, and audit logs.

## Assumptions

- v0.1 targets Ubuntu 24.04 in Lima on Apple Silicon macOS.
- Python is the only implementation language.
- CLI is the only required UI.
- User-facing responses mirror the user's English or Chinese.
- Privileged operations use explicit `sudo`.
- Logs are append-only JSONL via `XFUSION_AUDIT_LOG_PATH`.
- LLM config uses `XFUSION_LLM_BASE_URL`, `XFUSION_LLM_API_KEY`, and `XFUSION_LLM_MODEL`.
- Future versions may add SSH remote execution, web UI, voice input, openEuler/CentOS validation, persistent memory, and richer multi-agent orchestration.
