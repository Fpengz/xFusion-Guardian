# XFusion v0.2.2 Hardening Release Plan

## Release Framing

v0.2.2 is a **production-depth hardening release** for the existing v0.2
architecture. It does not open a new architecture track. The normative contract
remains:

- [docs/specs/xfusion-v0.2.md](specs/xfusion-v0.2.md)
- [docs/release-readiness-v0.2.md](release-readiness-v0.2.md)
- [docs/review-merge-readiness-v0.2.2.md](review-merge-readiness-v0.2.2.md)

Primary objective: reduce residual operational and assurance risk in known
follow-on areas while preserving deterministic authority boundaries.

## Backlog Tickets

### V022-WS1: Repair Policy And Library Hardening

**Why it matters**

Repair flow is now typed and auditable, but remains intentionally narrow and
simple-policy-gated. This is the highest leverage hardening area for safe
mutation reliability.

**Scope**

- Expand deterministic repair template library for known bounded failure classes
  (for example: retry-with-bounds, service restart fallback, scoped cleanup
  fallback, constrained signal escalation with explicit risk transition).
- Define and enforce deterministic equivalence classes for repair reuse
  decisions beyond a single `approval_summary` gate.
- Add explicit policy-table entries for equivalent-repair approval reuse
  decisions, including deny defaults and reason codes.
- Keep repair generation deterministic and registry-backed (no broad semantic
  planner).

**Non-goals**

- No autonomous broad semantic repair planner.
- No natural-language-only repair authorization.
- No relaxation of material-change invalidation rules.

**Acceptance criteria**

- Every reusable repair path has an explicit deterministic equivalence rule.
- Equivalent-repair reuse can only succeed through policy-table allow entries
  and fails closed otherwise.
- Materially changed repairs still re-enter full validation/policy/approval.
- Audit records clearly show equivalence evaluation inputs and final gate result.

**Risks**

- False equivalence if templates are too permissive.
- Policy-table drift from capability metadata.
- Over-hardening could reduce useful repair success rate.

**Suggested test strategy**

- Add table-driven unit tests for equivalence decisions and deny-by-default
  behavior.
- Add regression tests for non-equivalent repairs that must force reapproval.
- Expand scenario coverage in
  `tests/verification_dataset/scenarios/repair_role_hardening.yaml`.

---

### V022-WS2: Runtime/Process Containment Hardening

**Why it matters**

Role boundaries are runtime-enforced and containment is declarative; hardening
should improve real isolation guarantees without changing v0.2 trust model.

**Scope**

- Strengthen per-capability runtime profiles (environment variable allowlists,
  cwd constraints, timeout/IO ceilings, adapter-level privilege narrowing).
- Introduce enforceable process-level isolation controls where feasible in
  current runtime (for example: stricter subprocess launcher wrappers,
  deterministic network-disable assertions in adapter execution paths).
- Add deterministic guard checks proving containment flags are active at runtime.

**Non-goals**

- No full OS/container sandbox implementation in v0.2.2.
- No multi-runtime orchestration redesign for reasoning roles.
- No expansion of capability authority surface.

**Acceptance criteria**

- Runtime constraints are verifiably applied per execution and auditable.
- Any attempt to execute outside allowed runtime profile is fail-closed.
- Network-denied-by-default posture is test-asserted in runtime paths that do
  not explicitly require network.
- Role runtime records remain attributable and deterministic.

**Risks**

- Platform variance may cause flaky containment assertions.
- Tighter limits may break legitimate adapter behavior.
- Hardening may expose hidden dependency on broad process privileges.

**Suggested test strategy**

- Add runtime contract tests for constraint activation and violation handling.
- Add fault-injection tests for attempted containment bypass.
- Add smoke tests to ensure legitimate capabilities still execute under narrowed
  profiles.

---

### V022-WS3: Verification Dataset Expansion And Coverage Reporting

**Why it matters**

Current dataset is strong for repair/role invariants, but breadth across
adversarial/fault classes remains a declared follow-on risk.

**Scope**

- Expand corpus breadth across scenario, invariant, adversarial, and
  fault-injection classes per
  [docs/verification-dataset-strategy.md](verification-dataset-strategy.md).
- Convert all historical hardening bugs and newly discovered v0.2.2 issues into
  permanent regression cases.
- Add CI-visible coverage summary for dataset dimensions (fail-closed classes,
  approval invalidation triggers, redaction assertions, audit field assertions).

**Non-goals**

- No brittle snapshot-heavy NLP answer scoring track.
- No replacement of existing deterministic contract/unit tests.
- No speculative corpus expansion outside current capability surface.

**Acceptance criteria**

- Coverage report generated in CI for agreed dataset dimensions.
- All known historical hardening bugs are represented in regression corpus.
- New v0.2.2 hardening behaviors have both positive and fail-closed coverage.
- Verification cases assert authoritative state transitions, not only final text.

**Risks**

- High maintenance overhead if case schema/governance is loose.
- False confidence if coverage metrics are counted but not meaningful.
- CI runtime growth.

**Suggested test strategy**

- Add schema-validated dataset cases and strict parser checks.
- Add metamorphic case variants for key policy/approval transitions.
- Gate merges on dataset schema validity plus targeted coverage thresholds.

---

### V022-WS4: Compatibility And Debt Cleanup (Hardening-Supporting Only)

**Why it matters**

v0.2.1 removed major legacy aliases; residual compatibility/debt cleanup should
prevent accidental authority-surface regression and improve maintainability.

**Scope**

- Sweep for residual legacy invocation assumptions in tests, docs, fixtures, and
  internal helper code.
- Tighten fail-closed validation/error messaging where behavior is already
  normative but currently under-specified in implementation detail.
- Ensure docs and tests remain synchronized on canonical fields (`capability`,
  `args`, `step_id`, `depends_on`).

**Non-goals**

- No reintroduction of compatibility aliases.
- No broad refactor unrelated to hardening risk.
- No user-facing architecture change.

**Acceptance criteria**

- No remaining legacy-only execution field usage in authoritative path or
  sanctioned fixtures unless explicitly marked archival/non-normative.
- Validation failures for legacy/deprecated forms remain explicit and
  deterministic.
- Doc/spec/readiness links are internally consistent and current.

**Risks**

- Overreach into non-hardening cleanup scope.
- Accidental breaking changes in test harness utilities.
- Reviewer fatigue from low-signal cleanup churn.

**Suggested test strategy**

- Add targeted regression tests that assert legacy fields fail closed.
- Add docs consistency checks for authoritative path references.
- Keep changeset small and contract-focused.

---

### V022-WS5: Release Readiness Gate For v0.2.2

**Why it matters**

Hardening value is only real if validated, auditable, and reviewer-legible at
release time.

**Scope**

- Produce v0.2.2 review/merge readiness note summarizing deltas and unchanged
  architecture.
- Require green gates:
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run ty check`
- Add a residual-risk section explicitly listing what remains deferred past
  v0.2.2.

**Non-goals**

- No weakening of quality gates for schedule.
- No release without updated reviewer-facing hardening summary.

**Acceptance criteria**

- All quality gates pass on release candidate branch.
- v0.2.2 readiness document is complete, accurate, and cross-linked.
- Residual-risk narrative matches actual implementation boundaries.

**Risks**

- Last-mile churn from late hardening merges.
- Incomplete risk communication despite passing tests.

**Suggested test strategy**

- Full gate execution on clean environment.
- Optional opt-in live rehearsal remains green where enabled.
- Manual reviewer checklist run-through before merge.

## Recommended Sequencing

1. **WS1 + WS2 start first** (core hardening of repair authorization and runtime
   controls).
2. **WS3 starts in parallel** once WS1/WS2 interfaces are stable enough to add
   high-value coverage.
3. **WS4 runs continuously in small slices** but only where it directly supports
   hardening correctness.
4. **WS5 runs last** as an integration/release gate, with one pre-RC dry run.

## Parallelization Plan

Safe to parallelize:

- WS1 policy/equivalence tests and WS2 runtime containment tests (different
  modules with minimal overlap if ownership is explicit).
- WS3 dataset authoring and CI coverage report scaffolding while WS1/WS2 coding
  proceeds.
- WS4 docs/fixture cleanup in small PRs that avoid touching active WS1/WS2 core
  logic.

Should not parallelize heavily:

- Final WS1 equivalence-rule semantics freeze and WS3 assertions depending on
  those semantics (sequence these with clear handoff).
- Final release-note wording before WS1–WS4 behavior is settled.

## Explicitly Deferred Until After v0.2.2

- Broad semantic/autonomous repair planning beyond deterministic templates.
- Full policy-engine redesign beyond targeted equivalent-repair hardening.
- Physical per-role runtime/process isolation architecture.
- Full OS-level sandbox/network containment implementation.
- Major capability-surface expansion or new interaction channels (SSH/web/voice/
  persistent memory/multi-agent orchestration).
