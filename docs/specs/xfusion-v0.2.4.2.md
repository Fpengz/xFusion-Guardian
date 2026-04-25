# XFusion v0.2.4.2 Spec: Agent-Led Hybrid Execution

## Summary

XFusion v0.2.4.2 introduces an agent-led hybrid execution model. Agents perform
intent interpretation, execution-surface selection, risk and impact assessment,
and progressive-hardening recommendations. The system remains authoritative for
validation, structural risk ceilings, approval, execution constraints, integrity
binding, redaction, verification, and audit.

The guiding rule is:

```text
Agents decide how to act; the system decides whether the action is allowed.
```

This version intentionally expands beyond the v0.2 registered-capability-only
surface while preserving deterministic enforcement at the trust boundary.

## Execution Surfaces

Every executable step uses exactly one execution surface:

- `capability`: first-class typed operations from the reviewed capability
  registry.
- `template`: reviewed structured command templates with validated parameters.
- `restricted_shell`: last-resort fallback when no capability or template
  applies.

The deterministic surface ordering is mandatory:

```text
capability > template > restricted_shell
```

If an applicable capability exists, it must be used. If no applicable capability
exists but an applicable template exists, the template must be used. Restricted
shell fallback requires a structured fallback reason and must not be used to
bypass safer abstractions.

## Agent Roles

v0.2.4.2 defines four agent roles:

- `Intent_Agent`: parses natural language into structured intent, target, and
  scope.
- `Planner_Resolver_Agent`: proposes the execution surface and action shape.
- `Risk_Impact_Agent`: classifies risk and describes consequences.
- `Review_Agent`: proposes template or capability scaffolds from repeated
  fallback patterns.

Agent outputs are proposals. They are never execution authority and cannot
self-approve actions.

## Risk And Impact

The `Risk_Impact_Agent` produces an `AgentRiskAssessment`:

- `category`: `read_only`, `write_safe`, `destructive`, `privileged`, or
  `forbidden`.
- `confidence`
- `impact_scope`
- `expected_side_effects`
- `reversibility`
- `privilege_needed`
- `confirmation_recommendation`
- `rationale`

`impact_scope` describes affected filesystem paths, process targets, network
impact, privilege impact, and global/system impact.

Policy categories mean:

- `read_only`: inspect state only.
- `write_safe`: bounded non-critical mutation.
- `destructive`: deletes, kills, overwrites, or stops service/process state.
- `privileged`: sudo/root/system-level/network-sensitive action.
- `forbidden`: absolute deny under normal flow.

If a human or admin override is valid, the action is `privileged`, not
`forbidden`. `forbidden` cannot be bypassed by normal user or standard admin
confirmation.

## SystemRiskEnvelope

The `SystemRiskEnvelope` is a deterministic structural guardrail around the
agent assessment. It can preserve, escalate, or deny risk, but it must never
downgrade the agent classification.

Mandatory invariant:

```text
system_risk >= agent_risk
```

Structural escalation includes, at minimum:

- protected filesystem targets such as `/`, `/etc`, `/usr`, `/bin`, `/sbin`,
  `/boot`, and `/var/lib`
- critical process targets such as PID 1 or kernel processes
- wildcard destructive operations
- implicit privilege escalation
- global or network-sensitive impact

The system risk envelope is not a broad command policy table. It is a structural
ceiling and denial layer used to prevent under-classified catastrophic actions.

## Plan And Policy Contracts

`PlanStep` includes v0.2.4.2 execution metadata:

- `execution_surface`
- `policy_category`
- `impact_scope`
- `agent_risk_assessment`
- `system_risk_envelope`
- `final_risk_category`
- `resolution_record`
- `fallback_reason`
- `intent_hash`
- `planned_action_hash`
- `approved_action_hash`
- `executed_action_hash`

`PolicyDecision` includes:

- `execution_surface`
- `policy_category`
- existing risk tier, approval mode, reason codes, risk contract, and
  explainability fields

Execution integrity is mandatory:

```text
approved_action_hash == executed_action_hash
```

If the approved action and executable action differ, execution must fail closed
before adapter or shell execution.

## Restricted Shell

Restricted shell is a fallback only. It requires:

- structured fallback reason
- argv-based execution
- no unrestricted sudo
- bounded timeout
- bounded stdout/stderr
- working-directory restrictions
- environment sanitization/redaction
- trace logging
- policy and confirmation gating

Restricted shell may be useful for novel read-only inspection, but repeated
usage should become a template or capability through progressive hardening.

The current template registry is intentionally argv-only. Enabled templates must
not depend on shell pipes, redirects, command substitution, glob expansion, or
other shell metacharacters. Unsupported template-like abilities remain disabled
until they are backed by a reviewed adapter, capability, or argv-safe template.

## Progressive Hardening

Tier 3 fallback usage is tracked by normalized command fingerprint, not raw
command text. For example:

```text
kill -9 1234 -> kill -9 {pid}
kill -9 5678 -> kill -9 {pid}
```

Repeated fallback patterns may generate template scaffolds. A developer or
administrator must review and approve scaffolds before they enter the template
or capability registry. Promotion must attach tests, policy metadata, review
status, usage statistics, and revocation support.

Runtime registration APIs and automated promotion are out of scope for
v0.2.4.2.

## Audit Requirements

Every execution or non-execution record must include:

- execution surface
- policy category and final risk category
- impact scope
- agent risk assessment
- system risk envelope
- resolution record and fallback reason
- confirmation state
- integrity hashes
- normalized action or command fingerprint
- execution trace where available

Audit records must remain redacted before general-purpose exposure.

## Tests

Required tests:

- System risk envelope escalates under-classified agent assessments.
- Capability is enforced over template or shell when available.
- Template is enforced over shell when available.
- Shell fallback fails without a structured fallback reason.
- Forbidden actions cannot be bypassed by normal confirmation.
- Approved and executed action hashes must match.
- Fallback usage normalizes command fingerprints.
- Audit records include hybrid execution and integrity fields.

## Current Implementation Notes

v0.2.4.2 adds the domain contracts and guardrails needed for agent-led hybrid
execution while keeping existing capability graph workflows operational. Full
runtime routing of every graph step through all three surfaces remains an
incremental follow-on; the implemented resolver and contracts define the
required semantics for that integration.
