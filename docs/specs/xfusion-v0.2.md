# XFusion v0.2 Spec: Capability-Governed Linux Operations Agent

## Summary

XFusion v0.2 is a capability-based, policy-governed Linux operations agent. It
lets model-assisted reasoning help with request understanding, observation,
diagnosis, workflow planning, verification, repair suggestions, and explanation,
while keeping all authority in deterministic infrastructure.

v0.2 replaces the v0.1 `tool + parameters` execution surface with typed
capability proposals, schema validation, explicit output references, policy
decisions, approval records, controlled adapters, deterministic redaction,
verification strategies, and full-pipeline audit instrumentation.

The model may propose. The system authorizes and executes.

## Normative Terms

These terms are used consistently throughout the v0.2 specification:

- **Authorized upstream output:** an output from a prior step that completed
  successfully, was policy-allowed, was approved when approval was required, and
  still belongs to the currently valid plan context.
- **Material change:** any change that can alter what is touched, what authority
  is needed, what risk tier applies, what evidence is consumed, or what outcome
  an operator approved. This includes changes to normalized arguments,
  referenced outputs, argument provenance, target context, scope, environment
  profile, capability version, adapter id, approval mode, risk tier, or grouped
  mutation membership.
- **Equivalence:** a deterministic policy declaration that two invocations
  differ only in ways that do not change target, scope, risk, authority,
  referenced evidence, or operator-visible impact. Agents must not infer
  equivalence from natural-language similarity.
- **General-purpose audit/log exposure:** any audit, log, trace, message,
  response, or stored record that may be visible to models, users, routine
  operators, developer tooling, or non-privileged support workflows. This does
  not include a future restricted privileged execution trace, which is outside
  the minimum v0.2 logging surface.

## Core Architecture

### Reasoning Roles

v0.2 defines a multi-role reasoning layer:

- Supervisor
- Observation
- Diagnosis
- Planning
- Verification
- Explanation

These are separate reasoning roles with distinct contracts, budgets, and allowed
proposal types. Their boundaries are normative and must be explicit enough to
permit future runtime separation, although an initial implementation may execute
multiple roles within one process, graph, or runtime agent.

No reasoning role is authoritative. Reasoning roles must not execute, approve
mutations, bypass policy, fabricate prior step outputs, consume unredacted secret
material, or alter authoritative execution records.

### Authoritative Pipeline

The deterministic pipeline is mandatory:

```text
agent proposal
  -> plan schema validation
  -> dependency/DAG validation
  -> reference validation/resolution
  -> capability schema validation
  -> policy decision
  -> approval gate
  -> controlled adapter execution
  -> output normalization
  -> redaction
  -> verification
  -> explanation
```

Capability schema validation may occur both before and after reference
resolution. Pre-resolution validation checks shape, capability existence, legal
argument sources, declared references, and static constraints. Post-resolution
validation checks resolved values against the capability input schema.

Audit instrumentation is required throughout the pipeline. User-visible
explanations must be derived from authoritative audited state and must not depend
on non-recorded agent memory or hidden reasoning.

### Trust Boundary

Untrusted or partially trusted inputs:

- user natural-language requests
- model-generated interpretations
- model-generated workflow drafts
- model-generated justifications
- raw command-like text in any agent output

Trusted deterministic components:

- capability registry
- schemas
- static validator
- dependency graph checker
- reference resolver
- policy engine
- approval gate
- execution adapters
- runtime containment controls
- output normalizer
- redaction pipeline
- audit logger

No untrusted component may directly cause state-changing execution.

## Reasoning Role Contracts

### Supervisor

The Supervisor interprets user intent, identifies whether the request needs
observation, diagnosis, remediation, explanation, or clarification, and
coordinates the other roles. It may assemble a draft workflow from role outputs.
It must not execute, authorize, or approve.

### Observation

The Observation role proposes read-only capabilities for logs, service status,
process state, disk state, file metadata, and similar evidence gathering. It may
only propose Tier 0 capabilities and must not request unrestricted paths,
unbounded outputs, or mutation.

### Diagnosis

The Diagnosis role consumes typed observations and produces advisory hypotheses.
It may rank hypotheses, cite observations, identify missing evidence, and
estimate confidence. It must not change authorization, policy outcome, or risk
classification.

### Planning

The Planning role converts a goal and evidence into a typed workflow DAG. It
must propose only registered capabilities, define dependencies, reference prior
outputs explicitly, attach verification strategy, and avoid unresolved or
fabricated references.

### Verification

The Verification role evaluates execution results against the plan's verification
strategy. Model-assisted verification may operate only on redacted inputs.
Trusted deterministic verifiers may inspect richer structured outputs when
secret-handling policy permits. Verification must not automatically re-run
mutations unless a new or equivalent authorization path permits it.

### Explanation

The Explanation role summarizes intent, evidence, policy decisions, approval
requirements, denials, execution results, verification results, and safe next
steps. It must derive user-visible explanations from authoritative audited state
and must not obscure blocked or denied actions.

## Capability Model

### Capability Definition

Every executable operation must map to a registered capability. Unknown
capabilities are denied by default.

Each capability definition must include:

- `name`
- `version`
- `verb`
- `object`
- `risk_tier`
- `approval_mode`
- `allowed_environments`
- `allowed_actor_types`
- `scope_model`
- `input_schema`
- `output_schema`
- `runtime_constraints`
- `adapter_id`
- `is_read_only`
- `preview_builder`
- `verification_recommendation`
- `redaction_policy`

Capability definitions are the executable surface. Free-form command strings are
not a capability surface.

Capability definitions are code-defined. Environment policy may constrain where
and how a capability may run, but it must not redefine canonical capability
schemas or adapter contracts.

### Capability Examples

Tier 0 read-only examples:

- `get_service_status`
- `get_service_logs`
- `find_process_on_port`
- `verify_port_free`
- `read_file`
- `list_directory`
- `search_logs`
- `get_disk_usage`
- `get_memory_usage`
- `read_config_snippet`

Tier 1 bounded mutation examples:

- `terminate_process`
- `restart_service`
- `rotate_logs`
- `clear_temp_cache`
- `run_approved_script`

Tier 2 high-risk mutation examples:

- `delete_files`
- `modify_config_file`
- `run_db_migration`
- `rollout_restart`
- `package_install`

Tier 3 prohibited or broad-impact examples:

- unrestricted shell
- unrestricted sudo
- arbitrary SSH or SCP
- arbitrary `docker`, `kubectl`, `git`, `python`, `bash`, or `sh`
- unrestricted package installation
- unrestricted network fetch-and-run

## Plan Model

### Plan Contract

Every request that reaches planning becomes a typed workflow plan, even when the
workflow has one step.

Required plan fields:

- `plan_id`
- `goal`
- `intent_class`
- `target_context`
- `created_by`
- `created_at`
- `steps`
- `assumptions`
- `safety_notes`
- `approval_summary`
- `verification_strategy`

### Step Contract

Each step invokes exactly one registered capability.

Required step fields:

- `id`
- `capability`
- `depends_on`
- `args`
- `expected_outputs`
- `justification`
- `risk_hint`
- `approval_required_hint`
- `preview_summary`
- `on_failure`
- `verification_step_ids`
- `state`

The authoritative execution surface is `capability + args`, not
`tool + parameters`.

### Allowed Argument Sources

A step argument may come from:

- a literal
- validated user-provided input
- a prior successful step output reference
- policy-injected trusted context

A step argument must not come from:

- unresolved model text
- free-form shell fragments
- outputs from failed steps
- outputs from skipped steps
- implicit default fabrication

### Reference Syntax

References use this syntax:

```text
$steps.<step_id>.outputs.<field>
```

Example:

```json
{
  "pid": "$steps.locate.outputs.pid",
  "signal": "TERM"
}
```

The validator and resolver must reject:

- unknown step ids
- references to steps that are not declared dependencies when dependency
  compatibility is required
- missing output fields
- type mismatches
- references to non-success states
- references across disallowed trust boundaries
- references whose provenance is not acceptable for the target capability

## Static Validation

Before policy evaluation or execution, every plan must undergo static
validation.

The validator must check:

- plan schema validity
- unique step ids
- every capability exists in the registry
- dependency graph is acyclic
- dependency references point to known steps
- reference syntax is valid
- referenced outputs are declared by upstream output contracts
- step arguments match capability input schemas after resolution
- forbidden fields are absent
- mutation is not hidden behind misleading metadata
- every mutating workflow defines a verification strategy

If validation fails, the plan must not proceed to policy evaluation or execution.
The system must produce structured validation errors and preserve the invalid
draft and validation failure in audit records.

## Policy Model

### Policy Authority

The policy engine is the sole authority that converts a normalized capability
invocation into:

- `allow`
- `require_confirmation`
- `deny`

Policy inputs include:

- capability metadata
- resolved arguments
- argument provenance
- environment profile
- actor type
- host class
- target scope
- request intent
- prior approval state
- time and quota context where applicable

If no rule matches exactly, the decision is `deny`.

### Policy Decision Contract

Every policy decision must produce an authoritative record:

- `decision`
- `matched_rule_id`
- `risk_tier`
- `approval_mode`
- `constraints_applied`
- `reason_codes`
- `explainability_record`

The explainability record must answer which capability matched, which rule
matched, which constraints applied, why approval was or was not required, and why
the action was denied if denied.

### Risk Tiers

Risk tiers are normative:

- Tier 0: read-only inspection within validated scope.
- Tier 1: bounded reversible mutation.
- Tier 2: high-risk mutation.
- Tier 3: prohibited or broad-impact operation.

Risk tier may be declared by capability metadata and tightened by environment
policy.

Production defaults are strict:

- Tier 0 auto allowed only within explicit scope.
- Tier 1 requires human approval.
- Tier 2 requires admin approval or denial.
- Tier 3 is denied.

## Approval Model

### Approval Modes

Supported approval modes:

- `auto`
- `human`
- `admin`
- `deny`

### Material Change And Equivalence

Material change and equivalence use the definitions in [Normative Terms](#normative-terms).
Approval code, policy code, and repair code must apply the same definitions.

### Approval Records

Approval-gated steps must produce a preview payload and bind the operator's exact
typed confirmation to:

- approval record id
- normalized capability set
- target context
- action fingerprint or hash
- expiry

Prior approval state may satisfy an approval requirement only when the approved
action fingerprint, target context, referenced outputs, approval mode, and TTL
still match.

### Preview Payload

Every approval-gated step must produce a preview object with:

- impacted target
- action summary
- reversibility estimate
- expected blast radius
- exact capability and normalized args
- argument provenance summary
- rollback notes if available
- approval mode
- expiry

### Approval Invalidation

Approval must be invalidated when:

- arguments change materially
- referenced upstream outputs change materially
- target host, service, process, file, or scope changes
- the plan is repaired or rewritten in a way that changes impact
- scope expands
- risk tier increases
- approval TTL expires

Multi-step approval is allowed only when every grouped mutation and target is
listed explicitly in the preview. Hidden follow-up mutations are not covered.

## Execution Runtime

### Runtime Invariants

All adapters must execute through controlled subprocess/runtime execution with:

- `shell=False`
- no model-originated command text
- no command interpolation
- no interactive TTY
- strict timeout limits
- stdout and stderr byte limits
- bounded environment variables
- bounded working directory
- outbound network denied by default unless the capability explicitly requires
  it and policy allows it
- least privilege
- capability-specific privilege rules
- output normalization before model or user exposure

The default execution identity is non-root. If elevated privileges are required,
they must be narrowly scoped to the capability and mediated through
capability-specific privilege rules. Unrestricted sudo is prohibited.

### Adapter Contract

Each adapter must:

- accept already validated typed input
- reject invalid inputs defensively
- avoid parsing model output
- avoid accepting free-form shell text
- construct process argument arrays safely
- enforce runtime constraints
- normalize raw operating-system results into the capability output schema
- emit structured failure information
- pass output through redaction before model-visible, user-visible, or
  general-purpose audit/log exposure

An adapter such as `run_command(command: str)` is prohibited. An adapter such as
`get_service_logs(service: str, lines: int)` is acceptable when backed by a
registered capability, validated scope, and controlled execution.

## Secret Handling And Redaction

Secrets are denied by default.

The system must deny known secret paths, including at least:

- SSH private keys
- kubeconfigs
- `.env` files containing credentials
- database credential files
- cloud credential files
- `/etc/shadow`
- root-only secret material
- secret mounts

The system must apply deterministic pattern redaction for common token, key,
credential, and secret shapes in adapter output before any model-visible,
user-visible, or general-purpose audit/log exposure.

Redaction policy is deterministic. Agents must not decide whether text "looks
secret enough."

Restricted privileged execution traces may exist in future implementations, but
they are outside the minimum v0.2 general-purpose logging surface.

## Observations And Diagnosis

### Observation Contract

Observations are typed records derived from read-only capability outputs.

Examples:

- service status
- port usage
- log summaries
- disk usage
- memory usage
- config snippets
- file metadata

Each observation must include:

- `observation_id`
- `type`
- `source_step_id`
- `source_capability`
- `timestamp`
- `normalized_payload`
- `provenance`
- `redaction_status`
- `confidence` or `fidelity`

### Diagnosis Contract

Diagnosis is advisory only. It may contain:

- `hypothesis_id`
- summary
- supporting observation ids
- counterevidence
- confidence
- missing evidence
- recommended observation steps

Diagnosis must not imply permission to mutate and must not replace policy.

## Verification And Repair

Every mutating workflow must define a verification strategy and must include at
least one explicit verification step unless the plan records that no meaningful
verifier exists. If no meaningful verifier exists, the workflow must state that
explicitly and classify the final outcome as unverified rather than silently
assuming success.

Verification outcomes:

- `success`
- `partial_success`
- `failed`
- `inconclusive`

Model-assisted verification may operate only on redacted inputs. Trusted
deterministic verifiers may inspect richer structured outputs when policy
permits.

If verification fails, v0.2 may propose a repair plan. Any materially changed
repair plan must re-enter static validation, reference checks, capability schema
validation, policy evaluation, and approval. Repairs that expand scope, increase
risk, change targets, or change referenced outputs must invalidate prior
approval unless policy explicitly allows equivalence as defined by the approval
model.

Example: if `terminate_process(signal=TERM)` fails and a repair suggests
`signal=KILL`, the repair is a new higher-risk action. Policy must be
re-evaluated, and prior approval must not be assumed to cover the escalation.

## Failure Handling

The system must distinguish these failure classes:

- validation failure
- policy denial
- approval pending
- approval denied
- approval expired
- adapter failure
- execution failure
- runtime timeout
- scope violation
- redaction failure
- verification failure
- internal system failure

User-visible responses must distinguish these plainly. "Needs approval",
"policy denied", "plan invalid", "execution failed", and "verification failed"
are different states and must not be collapsed into a generic failure.

If the system cannot confidently validate scope, arguments, target identity, or
secret-handling state, it must fail closed.

## Audit And Observability

Audit is pipeline-wide instrumentation, not an end-stage log.

For every request, the system must record:

- original user request
- interpreted intent
- role proposals
- plan drafts
- validation results and failures
- dependency checks
- reference validation and resolution
- normalized capability invocations
- policy decisions
- approval requests and responses
- controlled execution invocations
- adapter outcomes
- output normalization metadata
- redaction metadata
- verification outcomes
- final explanation snapshot

The final explanation snapshot is the exact authoritative record from which the
user-visible response was derived.

Each step log must include:

- step id
- capability
- normalized args
- argument provenance
- resolved references
- matched policy rule
- approval mode
- approval id if applicable
- action fingerprint if applicable
- adapter id
- start and end timestamps
- execution status
- normalized output
- redaction metadata
- verification status

An operator or reviewer must be able to reconstruct what the system thought the
user wanted, what it planned, why each step was allowed or blocked, what exactly
ran, what changed, what was verified, and what was explained to the user.

## Acceptance Criteria

A v0.2 implementation is acceptable only if it passes both scenario-based and
invariant-based acceptance tests.

### Required Scenarios

- Read-only service diagnosis.
- Safe "free port" remediation.
- Disk cleanup preview, approval, and verification.
- Blocked protected-path action.
- Blocked secret read.
- Invalid or fabricated reference rejection.
- Repair proposal after failed verification.
- Stale approval invalidation after target or upstream output change.
- Deny-by-default rejection of an unknown capability.

### Required Invariants

- Registered capability required for execution.
- Schema validation for every capability invocation.
- Unknown or extra step fields rejected unless explicitly allowed by schema.
- DAG and reference validation before execution.
- References resolve only from authorized upstream outputs.
- Policy deny-by-default when no exact rule matches.
- Approval invalidation on material change.
- Adapter runtime constraints enforced.
- Redaction before any model-visible, user-visible, or general-purpose logging
  surface.
- Verification strategy present for every mutating workflow.
- User-visible explanation reproducible from authoritative audit records.

## Migration From v0.1 (Complete)

This section is historical. The v0.1 to v0.2 migration is complete, and legacy
compatibility aliases (such as `tool`, `parameters`, `id`, and `dependencies`)
have been removed from the authoritative plan and policy models for architecture
hygiene.

The normative source of truth for all current behavior remains the sections
above.

## Non-Goals

v0.2 does not provide:

- arbitrary shell execution
- unrestricted sudo
- arbitrary SSH or SCP
- open-ended package installation
- raw `docker`, `kubectl`, `git`, `python`, `bash`, or `sh` execution
- autonomous self-approval
- secret access by default
- policy decisions delegated to the model
- model-originated raw command execution

These exclusions are intentional. XFusion v0.2 is agent-assisted, not
agent-governed.
