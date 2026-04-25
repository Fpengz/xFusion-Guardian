# v0.2.4.2 Specification: Hybrid Execution Model with Progressive Hardening

## Executive Summary

This specification refactors the existing capability-only execution model (v0.2) into a **three-tier hybrid execution system** that balances security, flexibility, and operational practicality. The design introduces policy categorization, usage-driven capability evolution, and a restricted shell fallback mechanism while maintaining fail-closed security guarantees.

**Scope**: Complete implementation for hackathon demonstration. Backward compatibility is explicitly not required.

---

## 1. Hybrid Execution Model

### Architecture Overview

```
User Input
    ↓
Intent Classification
    ↓
Capability Resolver ─────────────────────────────┐
    ↓                                             │
┌─────────────────────────────────────────────┐   │
│  Tier 1: Registered Capabilities            │   │
│  - First-class, typed operations            │   │
│  - Reviewed before availability             │   │
│  - Risk-classified (TIER_0-TIER_3)          │   │
│  - Best for repeated/sensitive actions      │   │
└─────────────────────────────────────────────┘   │
    ↓ (no match)                                  │
┌─────────────────────────────────────────────┐   │
│  Tier 2: Structured Command Templates       │   │
│  - Predefined command structures            │   │
│  - Validated parameters                     │   │
│  - Semi-common shell workflows              │   │
│  - Lower overhead than full capabilities    │   │
└─────────────────────────────────────────────┘   │
    ↓ (no match)                                  │
┌─────────────────────────────────────────────┐   │
│  Tier 3: Restricted Dynamic Shell           │   │
│  - Last-resort fallback                     │   │
│  - Risk-classified + sandboxed              │   │
│  - Trace-logged + confirmation-gated        │   │
└─────────────────────────────────────────────┘   │
    ↓                                             │
┌─────────────────────────────────────────────┐   │
│         Shared Policy Engine                │ ←─┘
│  - Unified policy evaluation                │
│  - Category-based rules                     │
│  - Confirmation gating                      │
└─────────────────────────────────────────────┘
    ↓
Confirmation / Rejection / Execution
    ↓
Trace + Audit Log
```

### Tier Definitions

#### Tier 1: Registered Capabilities (Current System Enhanced)

**Characteristics:**
- Code-defined `CapabilityDefinition` objects with full schema contracts
- Explicit risk tier (`TIER_0` through `TIER_3`) and approval mode (`AUTO`, `HUMAN`, `ADMIN`, `DENY`)
- Runtime constraints (timeout, output limits, network access, working directory)
- Verification recommendations for post-execution validation

**Implementation Status:** Already exists in `xfusion/capabilities/registry.py`. Enhanced with:
- Policy category metadata (`read_only`, `write_safe`, `destructive`, `privileged`, `forbidden`)
- Usage tracking for progressive hardening insights
- Template association for future Tier 2 promotion

**Known Limitations:**
- No runtime registration mechanism (capabilities are code-defined only)
- No versioning or lifecycle management beyond manual code changes
- No automated review workflow

---

#### Tier 2: Structured Command Templates (NEW)

**Purpose:** Bridge the gap between rigid capabilities and unrestricted shell access for semi-common workflows.

**Template Schema (YAML):**

```yaml
template_id: "filesystem.cleanup_log_files"
version: 1
description: "Remove log files older than N days from specified directories"
category: "write_safe"
risk_tier: "tier_1"
approval_mode: "human"

# Fixed command structure with parameterized arguments
command_pattern: "find {path} -type f -name '*.log' -mtime +{days} -delete"
argv_preferred: true  # Prefer argv-based execution over shell=True

# Parameter validation schema
parameters:
  path:
    type: string
    max_length: 4096
    validation_regex: "^/[^:*?\"<>|]+$"
    allowed_prefixes: ["/var/log", "/tmp", "/home"]
    forbidden_patterns: ["..", "/etc", "/root"]
  days:
    type: integer
    minimum: 1
    maximum: 365

# Safety constraints
constraints:
  timeout_sec: 60.0
  max_stdout_bytes: 10000
  max_stderr_bytes: 10000
  network_access: denied
  working_directory: "."
  environment_redaction: ["PASSWORD", "SECRET", "TOKEN", "KEY"]
  forbidden_flags: ["-rf", "--no-preserve-root"]

# Confirmation requirements
confirmation:
  required: true
  preview_template: "Will delete .log files older than {days} days from {path}"
  explicit_acknowledgment: ["I understand this will permanently delete files"]

# Verification recommendation
verification:
  method: "filesystem_metadata_recheck"
  post_condition: "No files matching pattern exist in path"

# Metadata for progressive hardening
metadata:
  created_at: "2025-01-15T00:00:00Z"
  author: "system"
  review_status: "approved"
  usage_count: 0
  promoted_from_fallback: false
```

**Resolver Logic:**
1. Parse user intent to identify command family (e.g., "cleanup logs", "list processes")
2. Match against template registry using intent keywords and parameter patterns
3. Validate user-provided parameters against template schema
4. Generate concrete command with validated parameters
5. Pass to shared policy engine for evaluation

**Implementation Files:**
- `xfusion/templates/registry.py` - Template registry and resolver
- `xfusion/templates/schema.py` - Template validation and schema contract
- `xfusion/templates/loader.py` - YAML template loading from filesystem
- `docs/specs/template-schema.md` - Full schema specification

**Known Limitations:**
- Templates are still code/filesystem-defined, not runtime-registered
- No automated template generation from repeated commands (requires ML/pattern detection)
- Limited to predefined command families; cannot handle arbitrary novel commands
- Parameter validation is syntactic, not semantic (e.g., can't verify path actually exists)

---

#### Tier 3: Restricted Dynamic Shell Fallback (NEW)

**Purpose:** Provide last-resort execution capability when no registered capability or template matches, while maintaining strict security controls.

**Critical Security Constraints:**

| Constraint | Implementation | Enforcement Level |
|------------|----------------|-------------------|
| No unrestricted sudo | Block `sudo` unless explicitly whitelisted in policy | Hard block |
| Bounded timeout | Max 30 seconds (configurable per policy) | Runtime enforcement |
| Bounded output | Max 100KB stdout/stderr | Runtime truncation |
| Working directory restrictions | Confined to `/tmp`, `/home/*`, or explicitly allowed paths | Pre-execution validation |
| Environment variable redaction | Strip `*PASSWORD*`, `*SECRET*`, `*TOKEN*`, `*KEY*` patterns | Pre-execution filtering |
| Network restrictions | Block outbound connections via namespace or firewall rules | OS-level (if available) |
| No shell expansion | Disable globbing, command substitution, variable expansion | Shell flag configuration |
| argv-based execution | Prefer `subprocess.run([...])` over `shell=True` | Code-level enforcement |

**Execution Flow:**

```python
def execute_restricted_shell(
    command: str,
    context: ExecutionContext
) -> RestrictedShellResult:
    # 1. Intent classification and risk scoring
    risk_score = classify_command_risk(command, context)
    
    if risk_score.category == "forbidden":
        raise PolicyDenial("Command matches forbidden pattern")
    
    # 2. Syntax validation and normalization
    normalized = normalize_command(command)
    if not validate_syntax(normalized):
        raise ValidationError("Invalid command syntax")
    
    # 3. Safety checks
    checks = [
        check_no_sudo(normalized),
        check_working_directory(context.working_dir),
        check_no_shell_expansion(normalized),
        check_timeout_within_limits(context.timeout),
        check_output_limits(context.max_output),
    ]
    for check_result in checks:
        if not check_result.passed:
            raise SafetyViolation(check_result.reason)
    
    # 4. Environment sanitization
    sanitized_env = sanitize_environment(os.environ.copy())
    
    # 5. Confirmation gating (if required by risk level)
    if risk_score.requires_confirmation:
        await request_confirmation(
            preview=build_command_preview(normalized),
            risk_explanation=risk_score.explanation,
        )
    
    # 6. Execution with runtime constraints
    result = subprocess.run(
        shlex.split(normalized),  # argv-based, no shell=True
        timeout=context.timeout,
        capture_output=True,
        env=sanitized_env,
        cwd=context.working_dir,
    )
    
    # 7. Output truncation and redaction
    truncated_stdout = truncate_and_redact(result.stdout, context.max_output)
    truncated_stderr = truncate_and_redact(result.stderr, context.max_output)
    
    # 8. Audit logging
    log_restricted_shell_execution(
        command=normalized,
        risk_score=risk_score,
        exit_code=result.returncode,
        output_size=len(truncated_stdout) + len(truncated_stderr),
    )
    
    return RestrictedShellResult(
        exit_code=result.returncode,
        stdout=truncated_stdout,
        stderr=truncated_stderr,
        risk_score=risk_score,
    )
```

**Risk Classification for Shell Commands:**

```python
class ShellRiskClassifier:
    FORBIDDEN_PATTERNS = [
        r"\brm\s+-rf\s+/",  # Recursive delete from root
        r"\bmkfs\b",  # Filesystem creation
        r"\bdd\s+",  # Disk dump
        r">\s*/dev/sd",  # Raw disk write
        r"\bchmod\s+-R\s+777\s+/",  # Recursive world-writable from root
        r"\bchown\s+-R\s+.*\s+/",  # Recursive ownership change from root
        r"\b:\(\)\{\s*:\|\:&\s*\};:",  # Fork bomb
    ]
    
    PRIVILEGED_PATTERNS = [
        r"\bsudo\b",
        r"\bmount\b",
        r"\bumount\b",
        r"\biptables\b",
        r"\bsystemctl\b.*\b(restart|stop|disable)\b",
        r"\buser(mod|add|del)\b",
    ]
    
    DESTRUCTIVE_PATTERNS = [
        r"\brm\b",
        r"\bkill\b",
        r"\bpkill\b",
        r"\btruncate\b",
        r">\s*",  # Redirect/truncate
    ]
    
    WRITE_SAFE_PATTERNS = [
        r"\bmkdir\b",
        r"\btouch\b",
        r"\bcp\b",
        r"\bmv\b",
        r"\becho\b.*>>",
    ]
    
    READ_ONLY_PATTERNS = [
        r"\bls\b",
        r"\bcat\b",
        r"\bhead\b",
        r"\btail\b",
        r"\bgrep\b",
        r"\bfind\b.*-type\s+f",
        r"\bps\b",
        r"\bdf\b",
        r"\bdu\b",
        r"\bfree\b",
    ]
```

**Implementation Files:**
- `xfusion/execution/restricted_shell.py` - Core restricted shell executor
- `xfusion/security/shell_classifier.py` - Command risk classification
- `xfusion/security/sanitizers.py` - Environment and command sanitization
- `xfusion/policy/shell_policy.py` - Shell-specific policy rules

**Known Limitations & Challenges:**

1. **Sandboxing is Declarative, Not Isolated:**
   - Current implementation relies on process-level restrictions, not OS-level isolation (containers, namespaces, seccomp)
   - A determined attacker could potentially escape restrictions if they find vulnerabilities in the restriction logic
   - **Mitigation:** Document this limitation clearly; recommend deployment in containerized environments for production use

2. **Network Restrictions Require OS Support:**
   - True network isolation requires firewall rules, network namespaces, or container networking
   - Pure Python implementation cannot reliably block all network access
   - **Mitigation:** Use `firejail`, `bubblewrap`, or container runtimes where available; fall back to best-effort blocking otherwise

3. **Shell Expansion Detection is Imperfect:**
   - Detecting all forms of shell expansion (globbing, command substitution, variable expansion) requires parsing shell syntax
   - Complex nested expansions may evade detection
   - **Mitigation:** Always prefer argv-based execution; reject commands with suspicious patterns; log all fallback executions for audit

4. **Timeout Enforcement is Cooperative:**
   - Python's `subprocess.run(timeout=...)` sends SIGKILL but child processes may spawn grandchildren that survive
   - **Mitigation:** Use process groups (`preexec_fn=os.setsid`) and kill entire group on timeout

5. **Environment Redaction is Pattern-Based:**
   - Cannot detect semantically sensitive variables without explicit naming conventions
   - **Mitigation:** Default-deny approach: pass only explicitly whitelisted variables instead of blacklisting sensitive ones

6. **No Real Sandboxing Without Infrastructure:**
   - True sandboxing requires kernel features (seccomp-bpf, AppArmor, SELinux) or containerization
   - This implementation provides defense-in-depth, not security boundaries
   - **Mitigation:** Clearly document as "restricted" not "sandboxed"; recommend containerized deployment

---

## 2. Policy Categories

### New Policy Category Enum

Add parallel classification layer to existing `RiskTier` and `ApprovalMode`:

```python
class PolicyCategory(StrEnum):
    """Semantic policy categories for human-readable risk communication."""
    
    READ_ONLY = "read_only"
    """Inspect state only. No confirmation usually required."""
    
    WRITE_SAFE = "write_safe"
    """Modifies non-critical state. Confirmation usually required."""
    
    DESTRUCTIVE = "destructive"
    """Deletes, kills, overwrites, stops services. Explicit confirmation required."""
    
    PRIVILEGED = "privileged"
    """Sudo/root/system-level/network-sensitive actions. Admin permission required."""
    
    FORBIDDEN = "forbidden"
    """Never allowed through the agent. Cannot be bypassed by normal user confirmation."""
```

### Mapping to Existing Enums

| PolicyCategory | Typical RiskTier | Typical ApprovalMode | Confirmation Required |
|----------------|------------------|---------------------|----------------------|
| `read_only` | `TIER_0` | `AUTO` | No |
| `write_safe` | `TIER_0` - `TIER_1` | `AUTO` - `HUMAN` | Sometimes |
| `destructive` | `TIER_1` - `TIER_2` | `HUMAN` | Yes (explicit) |
| `privileged` | `TIER_2` - `TIER_3` | `ADMIN` | Yes (admin only) |
| `forbidden` | `TIER_3` | `DENY` | N/A (always denied) |

### Policy Category Assignment Rules

**For Capabilities:**
- Assigned at definition time based on verb and object semantics
- Stored in `CapabilityDefinition.policy_category` field
- Used for human-readable explanations and UI display

**For Templates:**
- Assigned in template YAML metadata
- Must align with risk assessment of command pattern
- Validated during template loading

**For Restricted Shell:**
- Dynamically classified by `ShellRiskClassifier`
- Based on pattern matching against command text
- Conservative classification (prefer higher risk category on ambiguity)

### Implementation Files

- `xfusion/domain/enums.py` - Add `PolicyCategory` enum
- `xfusion/domain/models/capability.py` - Add `policy_category` field to `CapabilityDefinition`
- `xfusion/policy/categories.py` - Category assignment logic and mapping tables
- `xfusion/policy/rules.py` - Integrate category checks into `evaluate_policy()`

---

## 3. Capability Registration & Lifecycle

### Current State (Code-Defined)

Capabilities are currently defined in code at `xfusion/capabilities/registry.py::build_default_capability_registry()`. This approach provides:
- Strong typing and schema validation
- Version control integration
- Atomic updates with code deployments

**Limitations:**
- No runtime registration (requires code change + redeployment)
- No approval workflow (all capabilities in code are implicitly approved)
- No usage analytics (can't track which capabilities are most used)
- No automated promotion from observed patterns

### Enhanced Registration Model (Hackathon Scope)

For v0.2.4.2, implement **metadata scaffolding** for future runtime registration without full workflow implementation:

```python
class CapabilityRegistrationMetadata(BaseModel):
    """Metadata for capability registration and lifecycle tracking."""
    
    registration_id: str  # UUID
    capability_name: str
    version: int
    author: str  # Developer or system identifier
    submitted_at: datetime
    review_status: Literal["pending", "approved", "rejected", "revoked"]
    reviewer: str | None  # Admin who approved/rejected
    reviewed_at: datetime | None
    risk_assessment: dict[str, Any]  # Structured risk analysis
    intended_use_cases: list[str]
    usage_count: int = 0  # Incremented on each execution
    last_used_at: datetime | None
    promotion_source: Literal["manual", "template_promotion", "fallback_pattern"] | None
    revocation_reason: str | None
```

### Usage Tracking for Progressive Hardening

**Data Collection:**
- Log every capability invocation with timestamp, arguments (redacted), outcome
- Track failure rates, confirmation rejection rates, verification failures
- Identify frequently-used command patterns in Tier 3 fallback

**Analytics Pipeline (Simplified for Hackathon):**
```python
class CapabilityUsageTracker:
    def record_invocation(
        self,
        capability_name: str,
        tier: ExecutionTier,
        args_hash: str,  # Hash for privacy
        success: bool,
        confirmation_required: bool,
        confirmation_granted: bool | None,
        verification_passed: bool | None,
    ):
        # Append to JSONL audit log
        record = {
            "timestamp": datetime.now().isoformat(),
            "capability": capability_name,
            "tier": tier.value,
            "args_hash": args_hash,
            "success": success,
            "confirmation_required": confirmation_required,
            "confirmation_granted": confirmation_granted,
            "verification_passed": verification_passed,
        }
        self.sink.write(record)
    
    def get_usage_statistics(self, capability_name: str) -> UsageStats:
        # Aggregate from audit log
        ...
    
    def identify_promotion_candidates(self) -> list[PromotionCandidate]:
        """Find repeated fallback commands that could become templates/capabilities."""
        # Query audit log for frequent Tier 3 commands with similar patterns
        # Return candidates for manual review
        ...
```

### Implementation Files

- `xfusion/capabilities/metadata.py` - Registration metadata models
- `xfusion/capabilities/lifecycle.py` - Lifecycle state machine (stub for hackathon)
- `xfusion/audit/usage_tracker.py` - Usage tracking and analytics
- `xfusion/tools/capability_admin.py` - CLI for viewing/managing capabilities (read-only for hackathon)

**Known Limitations:**
- No actual runtime registration API (capabilities still code-defined)
- No automated template generation from usage patterns (requires ML/clustering)
- No approval workflow UI (CLI-only visibility)
- Usage analytics are append-only logs without real-time aggregation

---

## 4. Progressive Hardening Workflow

### Conceptual Flow

```
Raw Command (Tier 3 Fallback)
    ↓ (used repeatedly, e.g., 10+ times)
System Flags Pattern
    ↓
Developer/Admin Reviews Command Pattern
    ↓
Create Structured Template (Tier 2)
    ↓
Generate Tests + Policy Metadata
    ↓
Security Review + Approval
    ↓
Template Enters Registry
    ↓ (used extensively, becomes critical)
Promote to Full Capability (Tier 1)
    ↓
Code Review + Schema Definition
    ↓
Deployed as First-Class Capability
```

### Implementation for Hackathon

**Phase 1: Detection (Stub)**
```python
class ProgressiveHardeningAnalyzer:
    def __init__(self, audit_sink: JsonlAuditSink):
        self.audit_sink = audit_sink
    
    def find_repeated_fallback_commands(
        self,
        min_occurrences: int = 10,
        time_window_days: int = 7,
    ) -> list[RepeatedPattern]:
        """Identify Tier 3 commands used repeatedly that could become templates."""
        # Parse audit log for Tier 3 executions
        # Cluster by command pattern (normalize variables, paths, etc.)
        # Return patterns exceeding threshold
        # HACKATHON SCOPE: Return empty list with documentation
        return []
    
    def generate_template_scaffold(self, command_pattern: str) -> str:
        """Generate YAML template scaffold from observed command pattern."""
        # HACKATHON SCOPE: Return example scaffold as string
        return EXAMPLE_TEMPLATE_YAML
```

**Phase 2: Scaffolding (Implemented)**
- Provide CLI command to generate template YAML from example command
- Include pre-filled safety constraints based on command analysis
- Generate test cases for verification

**Phase 3: Review Workflow (Documented Only)**
- Document the review process without implementing workflow engine
- Provide checklist for security reviewers
- Define approval criteria and sign-off requirements

### Implementation Files

- `xfusion/verification/hardening.py` - Progressive hardening analyzer (stub)
- `scripts/generate-template-scaffold.py` - CLI tool for template generation
- `docs/specs/progressive-hardening-workflow.md` - Detailed workflow documentation

**Known Limitations:**
- No automated pattern detection (manual identification only)
- No automated test generation (manual test writing required)
- No workflow automation (manual review process)
- No metrics dashboard (raw log queries only)

---

## 5. Shared Policy Engine

### Unified Policy Evaluation

All three tiers route through the same policy engine with tier-specific considerations:

```python
def evaluate_unified_policy(
    intent: UserIntent,
    tier: ExecutionTier,
    target: CapabilityDefinition | CommandTemplate | ShellCommand,
    context: ExecutionContext,
) -> PolicyDecision:
    # Common checks for all tiers
    common_checks = [
        check_actor_permissions(context.actor),
        check_environment_restrictions(context.environment),
        check_protected_paths(intent.paths),
        check_secret_access(intent.paths),
        check_time_quotas(context.actor),
    ]
    
    for check in common_checks:
        if not check.passed:
            return PolicyDecision(
                decision=PolicyDecisionValue.DENY,
                reason=check.failure_reason,
                deny_code=check.code,
            )
    
    # Tier-specific evaluation
    if tier == ExecutionTier.TIER_1_CAPABILITY:
        return evaluate_capability_policy(target, context)
    elif tier == ExecutionTier.TIER_2_TEMPLATE:
        return evaluate_template_policy(target, context)
    elif tier == ExecutionTier.TIER_3_SHELL:
        return evaluate_shell_policy(target, context)
    
    raise ValueError(f"Unknown execution tier: {tier}")
```

### Policy Decision Contract

All policy evaluations return consistent `PolicyDecision` structure:

```python
class PolicyDecision(BaseModel):
    decision: PolicyDecisionValue  # ALLOW, REQUIRE_CONFIRMATION, DENY
    matched_rule_id: str
    risk_tier: RiskTier
    approval_mode: ApprovalMode
    policy_category: PolicyCategory  # NEW
    execution_tier: ExecutionTier  # NEW
    constraints_applied: list[str]
    reason_codes: list[str]
    confirmation_type: str  # "none", "user", "admin"
    deny_code: str | None
    reason_text: str
    risk_contract: StepRiskContract | None
    explainability_record: dict[str, Any]
```

### Implementation Files

- `xfusion/policy/engine.py` - Unified policy engine orchestrator
- `xfusion/policy/capability_policy.py` - Tier 1 policy rules
- `xfusion/policy/template_policy.py` - Tier 2 policy rules
- `xfusion/policy/shell_policy.py` - Tier 3 policy rules
- Update `xfusion/policy/rules.py` - Integrate tier routing

---

## 6. Audit & Trace Logging

### Enhanced Audit Record Structure

Extend existing `AuditRecord` to capture tier-specific information:

```python
class AuditRecord(BaseModel):
    # Existing fields
    timestamp: datetime
    plan_id: str
    step_id: str
    interaction_state: str
    before_state: dict[str, object]
    action_taken: dict[str, object]
    after_state: dict[str, object]
    verification_result: dict[str, object]
    step_started_at: datetime | None
    step_ended_at: datetime | None
    status: str
    summary: str
    
    # NEW fields for v0.2.4.2
    execution_tier: str  # "tier_1_capability", "tier_2_template", "tier_3_shell"
    policy_category: str | None  # "read_only", "write_safe", etc.
    capability_name: str | None
    template_id: str | None
    raw_command: str | None  # For Tier 3 only
    risk_score: dict[str, Any] | None  # For Tier 3 classification
    confirmation_details: dict[str, Any] | None
    usage_tracking_id: str  # For progressive hardening analytics
```

### Audit Log Queries for Progressive Hardening

```sql
-- Example queries (pseudo-SQL for JSONL log analysis)

-- Find most-used Tier 3 commands
SELECT 
    raw_command_pattern,
    COUNT(*) as usage_count,
    AVG(risk_score.value) as avg_risk
FROM audit_log
WHERE execution_tier = 'tier_3_shell'
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY raw_command_pattern
HAVING COUNT(*) >= 10
ORDER BY usage_count DESC;

-- Find capabilities with high confirmation rejection rates
SELECT 
    capability_name,
    COUNT(*) as total_invocations,
    SUM(CASE WHEN confirmation_granted = false THEN 1 ELSE 0 END) as rejections,
    rejections * 1.0 / total_invocations as rejection_rate
FROM audit_log
WHERE execution_tier = 'tier_1_capability'
  AND confirmation_required = true
GROUP BY capability_name
HAVING rejection_rate > 0.5;

-- Track policy category distribution
SELECT 
    policy_category,
    COUNT(*) as count,
    COUNT(DISTINCT plan_id) as unique_plans
FROM audit_log
GROUP BY policy_category;
```

### Implementation Files

- Update `xfusion/domain/models/audit.py` - Extended audit record schema
- Update `xfusion/audit/logger.py` - Capture new fields
- `scripts/analyze-usage.py` - CLI tool for querying audit logs
- `docs/specs/audit-schema-v0.2.4.2.md` - Schema documentation

---

## 7. Execution Flow: End-to-End

### Detailed Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        User Request                               │
│  "Clean up old log files in /var/log/myapp"                      │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                    Intent Classification                          │
│  - Extract action: "cleanup"                                     │
│  - Extract target: "/var/log/myapp"                              │
│  - Extract constraints: "old files"                              │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                   Capability Resolver                             │
│  1. Check Tier 1: Is there a registered capability?              │
│     → Search: "cleanup.*log", "file.*delete.*old"                │
│     → Result: No exact match                                     │
│                                                                  │
│  2. Check Tier 2: Is there a matching template?                  │
│     → Search template registry                                   │
│     → Match: "filesystem.cleanup_log_files"                      │
│     → Validate parameters: path="/var/log/myapp", days=30        │
│     → Result: MATCH FOUND                                        │
│                                                                  │
│  3. (Skip Tier 3: Template matched)                              │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                    Policy Engine                                  │
│  - Evaluate template against policy rules                        │
│  - Check actor permissions                                       │
│  - Verify path not protected/secret                              │
│  - Classify risk: WRITE_SAFE → TIER_1 → HUMAN confirmation       │
│  - Apply constraints: timeout=60s, network=denied                │
│  - Decision: REQUIRE_CONFIRMATION                                │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                  Confirmation Gateway                             │
│  Preview: "Will delete .log files older than 30 days from        │
│            /var/log/myapp"                                       │
│  Risk explanation: "This will permanently delete files. Action   │
│                     is reversible only from backup."             │
│  User response: CONFIRM                                          │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                    Execution                                      │
│  - Generate command: find /var/log/myapp -type f -name '*.log'   │
│                        -mtime +30 -delete                        │
│  - Execute with constraints (timeout, output limits)             │
│  - Capture stdout/stderr                                         │
│  - Verify exit code                                              │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                   Verification                                    │
│  Method: filesystem_metadata_recheck                             │
│  - Re-scan directory for matching files                          │
│  - Confirm files older than 30 days no longer exist              │
│  - Result: SUCCESS                                               │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                   Audit Logging                                   │
│  - Record execution details                                      │
│  - Update usage statistics                                       │
│  - Log for progressive hardening analysis                        │
└──────────────────────────────────────────────────────────────────┘
```

### Error Handling Paths

```
Any Step Failure
        ↓
┌──────────────────────────────────────────────────────────────────┐
│                 Error Classification                              │
│  - Validation error → Return to user with correction guidance    │
│  - Policy denial → Explain reason, suggest alternatives          │
│  - Confirmation timeout/failure → Abort, log attempt             │
│  - Execution failure → Retry? Escalate? Rollback?                │
│  - Verification failure → Alert, rollback if possible            │
└──────────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────────┐
│                   Recovery Actions                                │
│  - Log failure with full context                                 │
│  - Notify appropriate stakeholders                               │
│  - Trigger incident workflow if severe                           │
│  - Update capability/template health metrics                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. Known Limitations & Future Work

### v0.2.4.2 Limitations (Hackathon Scope)

1. **No True Runtime Registration:**
   - Capabilities and templates still defined in code/filesystem
   - No API for dynamic registration without redeployment
   - **Future:** Build registration API with approval workflow engine

2. **Limited Sandboxing:**
   - Tier 3 uses process-level restrictions, not OS isolation
   - Production deployment should use containers/firejail/bubblewrap
   - **Future:** Integrate with container runtimes or sandboxing tools

3. **Manual Progressive Hardening:**
   - Pattern detection is manual (query audit logs)
   - Template scaffolding is semi-automated (CLI tool)
   - Review workflow is manual (no workflow engine)
   - **Future:** ML-based pattern clustering, automated test generation

4. **No Network Isolation:**
   - Network restrictions are best-effort without OS support
   - **Future:** Integrate with firewall APIs or network namespaces

5. **No Real-Time Analytics:**
   - Usage stats require log parsing
   - No dashboard or alerting
   - **Future:** Time-series database + visualization layer

6. **Backward Compatibility Broken:**
   - Audit record schema changes
   - Policy decision structure extended
   - **Mitigation:** Explicitly not required for hackathon

### Post-Hackathon Roadmap

**v0.2.5: Runtime Registration & Workflow**
- Capability registration API
- Template submission workflow
- Approval/review UI
- Versioning and lifecycle management

**v0.2.6: Enhanced Sandboxing**
- Container integration (Docker/Podman)
- Firejail/bubblewrap wrappers
- Seccomp profiles for syscall filtering
- Network namespace isolation

**v0.2.7: Automated Progressive Hardening**
- ML-based pattern detection
- Automated template generation
- Test case synthesis
- Anomaly detection for risky patterns

**v0.3.0: Full Hybrid Model Maturity**
- All three tiers fully operational
- Seamless promotion between tiers
- Comprehensive analytics dashboard
- Production-ready security posture

---

## 9. Implementation Checklist

### Phase 1: Foundation (Days 1-2)
- [ ] Add `PolicyCategory` enum to `xfusion/domain/enums.py`
- [ ] Extend `CapabilityDefinition` with `policy_category` field
- [ ] Create `xfusion/policy/categories.py` with mapping logic
- [ ] Update default capabilities with category assignments

### Phase 2: Tier 2 Templates (Days 3-4)
- [ ] Create `xfusion/templates/` package structure
- [ ] Implement template schema validation (`schema.py`)
- [ ] Build template registry and resolver (`registry.py`)
- [ ] Create YAML loader (`loader.py`)
- [ ] Write 5-10 example templates for common workflows
- [ ] Integrate template resolution into execution flow

### Phase 3: Tier 3 Restricted Shell (Days 5-7)
- [ ] Implement `ShellRiskClassifier` (`security/shell_classifier.py`)
- [ ] Build restricted shell executor (`execution/restricted_shell.py`)
- [ ] Create environment/command sanitizers (`security/sanitizers.py`)
- [ ] Write shell-specific policy rules (`policy/shell_policy.py`)
- [ ] Add comprehensive test suite for security constraints
- [ ] Document all known limitations prominently

### Phase 4: Policy Engine Unification (Day 8)
- [ ] Create unified policy engine (`policy/engine.py`)
- [ ] Refactor existing `evaluate_policy()` to route by tier
- [ ] Ensure consistent `PolicyDecision` structure across tiers
- [ ] Update tests for all three tiers

### Phase 5: Audit & Usage Tracking (Day 9)
- [ ] Extend `AuditRecord` model with new fields
- [ ] Update audit logger to capture tier-specific data
- [ ] Build usage tracker (`audit/usage_tracker.py`)
- [ ] Create CLI tool for log analysis (`scripts/analyze-usage.py`)

### Phase 6: Progressive Hardening Scaffolding (Day 10)
- [ ] Implement stub analyzer (`verification/hardening.py`)
- [ ] Create template scaffold generator CLI
- [ ] Write workflow documentation
- [ ] Document future automation opportunities

### Phase 7: Integration Testing & Documentation (Days 11-12)
- [ ] End-to-end tests for all three tiers
- [ ] Security constraint validation tests
- [ ] Policy decision correctness tests
- [ ] Update architecture documentation
- [ ] Write migration guide (breaking changes)
- [ ] Prepare demo scenarios for hackathon presentation

---

## 10. Demo Scenarios for Hackathon

### Scenario 1: Tier 1 Capability (Existing Flow Enhanced)
**Task:** "Check disk usage on /var/log"
- Routes to `disk.check_usage` capability
- Policy category: `read_only`
- Auto-approved (no confirmation)
- Demonstrates enhanced audit logging with category

### Scenario 2: Tier 2 Template (New)
**Task:** "Clean up old log files in /tmp/myapp"
- No matching capability
- Matches `filesystem.cleanup_log_files` template
- Policy category: `write_safe`
- Requires user confirmation
- Shows template parameter validation
- Demonstrates preview generation

### Scenario 3: Tier 3 Restricted Shell (New)
**Task:** "Find all files larger than 100MB in /home"
- No matching capability or template
- Falls back to restricted shell
- Command: `find /home -type f -size +100M -ls`
- Classified as `read_only` (low risk)
- Auto-approved but logged extensively
- Shows security constraints in action

### Scenario 4: Policy Denial (All Tiers)
**Task:** "Delete everything in /etc"
- Attempted via Tier 3 shell
- Matches forbidden pattern: `rm -rf /etc`
- Blocked by `ShellRiskClassifier`
- Policy category: `forbidden`
- Decision: `DENY` with clear explanation
- Logged as security event

### Scenario 5: Progressive Hardening Insight
**Demo:** Show audit log analysis
- Query: "Most frequent Tier 3 commands this week"
- Result: `find /var/log -name '*.log' -mtime +30 -delete` (used 47 times)
- Recommendation: "Promote to template"
- Show generated template scaffold
- Demonstrate manual review workflow (documented)

---

## 11. Security Considerations

### Defense in Depth Strategy

1. **Layer 1: Intent Classification**
   - Reject obviously malicious requests early
   - Rate limiting on repeated failures

2. **Layer 2: Tier Selection**
   - Prefer Tier 1 (most constrained) over Tier 2 over Tier 3
   - Each tier has progressively weaker guarantees

3. **Layer 3: Policy Evaluation**
   - Unified policy engine with tier-specific rules
   - Protected paths, secrets, actor permissions

4. **Layer 4: Execution Constraints**
   - Timeouts, output limits, network restrictions
   - Environment sanitization

5. **Layer 5: Confirmation Gating**
   - Human/admin confirmation for risky operations
   - Clear preview of consequences

6. **Layer 6: Verification**
   - Post-execution state validation
   - Rollback triggers on verification failure

7. **Layer 7: Audit & Monitoring**
   - Comprehensive logging
   - Anomaly detection (future)
   - Incident response integration (future)

### Threat Model

**Assumptions:**
- LLM may be prompt-injected or produce unexpected outputs
- Users may attempt to bypass restrictions
- Malicious actors may gain access to agent interface

**Mitigations:**
- Fail-closed default (deny unknown)
- Multiple independent security layers
- Comprehensive audit trail for forensics
- Clear separation between tiers (escalation requires explicit action)

**Residual Risks:**
- Tier 3 shell escape (mitigated by containerization recommendation)
- Prompt injection causing unintended Tier 3 usage (mitigated by logging/analytics)
- Insider threat with admin credentials (out of scope, requires organizational controls)

---

## 12. Conclusion

This specification transforms the v0.2 capability-only system into a flexible three-tier hybrid execution model while maintaining strong security guarantees. The design acknowledges practical constraints (hackathon timeline, no backward compatibility requirements) and clearly documents limitations for future improvement.

**Key Achievements for v0.2.4.2:**
- ✅ Three-tier execution model (capabilities, templates, restricted shell)
- ✅ Policy category system for human-readable risk communication
- ✅ Unified policy engine across all tiers
- ✅ Enhanced audit logging for usage analytics
- ✅ Progressive hardening scaffolding (manual workflow documented)
- ✅ Comprehensive security constraints for Tier 3
- ✅ Full demo scenarios showcasing all tiers

**Explicitly Out of Scope (Future Versions):**
- ❌ Runtime capability registration API
- ❌ OS-level sandboxing (containers, seccomp, namespaces)
- ❌ Automated pattern detection and template generation
- ❌ Real-time analytics dashboard
- ❌ Approval workflow engine

This foundation enables iterative enhancement toward a mature, production-ready hybrid execution system while delivering immediate value through increased flexibility and operational insight.
