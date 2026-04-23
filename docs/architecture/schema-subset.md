# XFusion Schema Subset

XFusion's authoritative schema subset definition lives in
[capability-schema.md](capability-schema.md).

For reviewers and maintainers:

1. Treat [../specs/xfusion-v0.2.md](../specs/xfusion-v0.2.md) as normative behavior.
2. Treat [capability-schema.md](capability-schema.md) as the executable schema
   contract implemented by
   [../../xfusion/capabilities/schema.py](../../xfusion/capabilities/schema.py).
3. Do not assume unsupported JSON Schema features are silently accepted;
   unsupported or malformed keywords fail closed.
