# Capability Schema Subset

XFusion v0.2 uses code-defined JSON-Schema-like dictionaries for capability
`input_schema` and `output_schema` validation. The normative product behavior is
defined in [docs/specs/xfusion-v0.2.md](../specs/xfusion-v0.2.md); this note
documents the currently implemented validator subset for maintainers.

The canonical implementation is [xfusion/capabilities/schema.py](../../xfusion/capabilities/schema.py).
Extend that module and its tests when adding schema support. Do not add schema
keywords only in capability definitions and assume they are enforced.

## Supported Keywords

The central runtime validator currently recognizes these keywords:

| Keyword | Supported behavior |
| --- | --- |
| `$comment` | Allowed annotation; not used for validation. |
| `additionalProperties` | `false` forbids unknown object fields; a schema object validates extra fields. |
| `allOf` | Value must satisfy every listed schema. |
| `anyOf` | Value must satisfy at least one listed schema. |
| `const` | Value must equal the declared constant. |
| `contains` | Array must contain matching item(s), with `minContains`/`maxContains` when present. |
| `description` | Allowed annotation; not used for validation. |
| `enum` | Value must be one of the listed values. |
| `exclusiveMaximum` | Numeric value must be lower than this bound. |
| `exclusiveMinimum` | Numeric value must be higher than this bound. |
| `items` | A schema object validates every array item. Tuple validation is not implemented. |
| `maxContains` | Upper bound for array items matching `contains`. |
| `maxItems` | Maximum array length. |
| `maxLength` | Maximum string length. |
| `maxProperties` | Maximum object property count. |
| `maximum` | Inclusive numeric upper bound. |
| `minContains` | Lower bound for array items matching `contains`; defaults to `1` when `contains` is present. |
| `minItems` | Minimum array length. |
| `minLength` | Minimum string length. |
| `minProperties` | Minimum object property count. |
| `minimum` | Inclusive numeric lower bound. |
| `multipleOf` | Numeric value must be an integral multiple of a positive divisor. |
| `not` | Value must not satisfy the nested schema. |
| `oneOf` | Value must satisfy exactly one listed schema. |
| `pattern` | String must match the Python regular expression. Invalid regex patterns fail validation. |
| `properties` | Object fields are validated against nested schemas. |
| `required` | Object must include the listed fields. |
| `title` | Allowed annotation; not used for validation. |
| `type` | Supports `object`, `array`, `string`, `integer`, `number`, `boolean`, `null`, and lists of those names. |
| `uniqueItems` | `true` requires array items to be unique by Python equality. |

This is intentionally a subset, not a full JSON Schema implementation.

## Unsupported Keywords Fail Closed

Any keyword outside the supported set makes validation fail with an
`unsupported schema keyword` error. This applies recursively inside nested
`properties`, `items`, `additionalProperties`, `contains`, `not`, `allOf`,
`anyOf`, and `oneOf` schemas.

Common unsupported examples include:

- `$defs`
- `$id`
- `$ref`
- `$schema`
- `dependentRequired`
- `dependentSchemas`
- `else`
- `format`
- `if`
- `patternProperties`
- `prefixItems`
- `propertyNames`
- `then`
- `unevaluatedItems`
- `unevaluatedProperties`

The fail closed behavior is a safety boundary. Capability schemas are part of
the deterministic authority path: they gate adapter input and decide whether
adapter output can become authoritative state or referenceable evidence. If a
schema contains a keyword the validator does not implement, silently accepting
the schema would create a false assurance that a constraint was enforced. Failing
closed turns that mismatch into an explicit validation failure instead.

## Input And Output Validation

Capability outputs are validated centrally in
[xfusion/execution/runtime.py](../../xfusion/execution/runtime.py) before
redaction, audit exposure, final response generation, or downstream reference
use. Output schema validation failures are normalized as structured adapter
outcomes and do not become successful upstream outputs.

Capability inputs are checked during static plan validation and after reference
resolution. Input schemas should stay simple, closed objects where possible:
declare every accepted argument under `properties`, list required arguments in
`required`, and set `additionalProperties` to `false`.

## Extending The Subset

To add support for a new keyword:

1. Update `SUPPORTED_SCHEMA_KEYWORDS` and validation logic in
   [xfusion/capabilities/schema.py](../../xfusion/capabilities/schema.py).
2. Add tests that demonstrate both accepted and rejected values.
3. Add or update capability registry tests if registered capabilities start
   depending on the new keyword.
4. Update this document in the same change.
5. Keep unsupported or partially understood features failing closed until they
   have deterministic validation coverage.
