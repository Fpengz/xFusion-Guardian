"""Deterministic validator for XFusion Capability Schema dictionaries.

XFusion Capability Schema is an explicit, frozen v0.2 contract inspired by JSON
Schema. It is not a general JSON Schema implementation. Unsupported or malformed
schema features fail closed before capability registration succeeds.
See docs/architecture/capability-schema.md before extending the contract.
"""

from __future__ import annotations

import re
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

SUPPORTED_SCHEMA_KEYWORDS = {
    "type",
    "enum",
    "const",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "uniqueItems",
    "contains",
    "minContains",
    "maxContains",
    "minLength",
    "maxLength",
    "pattern",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minProperties",
    "maxProperties",
    "allOf",
    "anyOf",
    "oneOf",
    "not",
    "description",
    "title",
    "$comment",
}

SUPPORTED_SCHEMA_TYPES = {
    "object",
    "array",
    "string",
    "integer",
    "number",
    "boolean",
    "null",
}


class SchemaValidationResult(BaseModel):
    """Deterministic validation result for the XFusion Capability Schema contract."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)


def validate_schema_contract(
    schema: dict[str, Any],
    *,
    path: str = "$",
) -> SchemaValidationResult:
    """Validate a code-defined schema against the XFusion Capability Schema contract."""
    errors = _schema_contract_errors(schema, path)
    return SchemaValidationResult(valid=not errors, errors=errors)


def validate_schema_value(
    value: Any,
    schema: dict[str, Any],
    *,
    path: str = "$",
) -> SchemaValidationResult:
    """Validate runtime values against the XFusion Capability Schema contract.

    Unsupported or malformed schemas are deterministic failures so code-defined
    schemas cannot silently claim coverage for constraints this validator does
    not enforce.
    """
    errors: list[str] = []
    errors.extend(validate_schema_contract(schema, path=path).errors)
    if errors:
        return SchemaValidationResult(valid=False, errors=errors)

    for keyword in ("allOf", "anyOf", "oneOf"):
        nested_errors = _validate_combiner(value, schema, keyword, path)
        if nested_errors:
            errors.extend(nested_errors)

    not_schema = schema.get("not")
    if isinstance(not_schema, dict):
        result = validate_schema_value(value, not_schema, path=path)
        if result.valid:
            errors.append(f"{path}: value matched forbidden not schema")

    expected_type = schema.get("type")

    if expected_type and not _type_matches(value, expected_type):
        errors.append(f"{path}: expected {expected_type}, got {_value_type(value)}")
        return SchemaValidationResult(valid=False, errors=errors)

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        errors.append(f"{path}: value {value!r} is not one of {enum_values!r}")

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value {value!r} does not match const {schema['const']!r}")

    if isinstance(value, int | float) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        exclusive_minimum = schema.get("exclusiveMinimum")
        exclusive_maximum = schema.get("exclusiveMaximum")
        multiple_of = schema.get("multipleOf")
        if isinstance(minimum, int | float) and value < minimum:
            errors.append(f"{path}: value {value!r} is below minimum {minimum!r}")
        if isinstance(maximum, int | float) and value > maximum:
            errors.append(f"{path}: value {value!r} is above maximum {maximum!r}")
        if isinstance(exclusive_minimum, int | float) and value <= exclusive_minimum:
            errors.append(
                f"{path}: value {value!r} is not above exclusiveMinimum {exclusive_minimum!r}"
            )
        if isinstance(exclusive_maximum, int | float) and value >= exclusive_maximum:
            errors.append(
                f"{path}: value {value!r} is not below exclusiveMaximum {exclusive_maximum!r}"
            )
        if isinstance(multiple_of, int | float) and multiple_of > 0:
            quotient = value / multiple_of
            if abs(quotient - round(quotient)) > 1e-9:
                errors.append(f"{path}: value {value!r} is not a multipleOf {multiple_of!r}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        pattern = schema.get("pattern")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{path}: string is shorter than minLength {min_length}")
        if isinstance(max_length, int) and len(value) > max_length:
            errors.append(f"{path}: string is longer than maxLength {max_length}")
        if isinstance(pattern, str):
            try:
                if re.search(pattern, value) is None:
                    errors.append(f"{path}: string does not match pattern {pattern!r}")
            except re.error as exc:
                errors.append(f"{path}: invalid pattern {pattern!r}: {exc}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path}: array has fewer than minItems {min_items}")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path}: array has more than maxItems {max_items}")
        if schema.get("uniqueItems") is True and not _items_are_unique(value):
            errors.append(f"{path}: array items are not uniqueItems")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                nested = validate_schema_value(item, item_schema, path=f"{path}[{index}]")
                errors.extend(nested.errors)
        contains_schema = schema.get("contains")
        if isinstance(contains_schema, dict):
            match_count = 0
            contains_errors: list[str] = []
            for index, item in enumerate(value):
                nested = validate_schema_value(item, contains_schema, path=f"{path}[{index}]")
                if nested.valid:
                    match_count += 1
                else:
                    contains_errors.extend(nested.errors)
            min_contains = schema.get("minContains", 1)
            max_contains = schema.get("maxContains")
            if isinstance(min_contains, int) and match_count < min_contains:
                errors.append(
                    f"{path}: array contains {match_count} matching item(s), below {min_contains}"
                )
            if isinstance(max_contains, int) and match_count > max_contains:
                errors.append(
                    f"{path}: array contains {match_count} matching item(s), above {max_contains}"
                )

    if isinstance(value, dict):
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, dict):
            properties = {}
        if not isinstance(required, list):
            required = []

        min_properties = schema.get("minProperties")
        max_properties = schema.get("maxProperties")
        if isinstance(min_properties, int) and len(value) < min_properties:
            errors.append(f"{path}: object has fewer than minProperties {min_properties}")
        if isinstance(max_properties, int) and len(value) > max_properties:
            errors.append(f"{path}: object has more than maxProperties {max_properties}")

        for required_name in required:
            if str(required_name) not in value:
                errors.append(f"{path}.{required_name}: missing required field")

        additional_properties = schema.get("additionalProperties")
        if additional_properties is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: additional properties are forbidden")
        elif isinstance(additional_properties, dict):
            for key, item in value.items():
                if key in properties:
                    continue
                nested = validate_schema_value(item, additional_properties, path=f"{path}.{key}")
                errors.extend(nested.errors)

        for key, nested_schema in properties.items():
            if key not in value or not isinstance(nested_schema, dict):
                continue
            nested = validate_schema_value(value[key], nested_schema, path=f"{path}.{key}")
            errors.extend(nested.errors)

    return SchemaValidationResult(valid=not errors, errors=errors)


def _validate_combiner(value: Any, schema: dict[str, Any], keyword: str, path: str) -> list[str]:
    candidates = schema.get(keyword)
    if candidates is None:
        return []
    if not isinstance(candidates, list) or not all(isinstance(item, dict) for item in candidates):
        return [f"{path}: {keyword} must be a list of schemas"]

    results = [
        validate_schema_value(value, candidate, path=path)
        for candidate in candidates
        if isinstance(candidate, dict)
    ]
    valid_count = sum(1 for result in results if result.valid)
    if keyword == "allOf" and valid_count != len(results):
        detail = "; ".join(error for result in results for error in result.errors)
        return [f"{path}: value failed allOf ({detail})"]
    if keyword == "anyOf" and valid_count < 1:
        return [f"{path}: value failed anyOf"]
    if keyword == "oneOf" and valid_count != 1:
        return [f"{path}: value matched {valid_count} oneOf schemas"]
    return []


def _schema_contract_errors(schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = [
        f"{path}: unsupported schema keyword {key!r}"
        for key in schema
        if key not in SUPPORTED_SCHEMA_KEYWORDS
    ]

    expected_type = schema.get("type")
    if expected_type is not None:
        errors.extend(_type_contract_errors(expected_type, path))

    properties = schema.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            errors.append(f"{path}.properties: properties must be an object")
        else:
            for key, nested in properties.items():
                if not isinstance(key, str):
                    errors.append(f"{path}.properties: property names must be strings")
                    continue
                if not isinstance(nested, dict):
                    errors.append(f"{path}.{key}: property schema must be an object")
                    continue
                errors.extend(_schema_contract_errors(nested, f"{path}.{key}"))

    required = schema.get("required")
    if required is not None and (
        not isinstance(required, list) or not all(isinstance(item, str) for item in required)
    ):
        errors.append(f"{path}.required: required must be a list of strings")

    enum_values = schema.get("enum")
    if enum_values is not None and not isinstance(enum_values, list):
        errors.append(f"{path}.enum: enum must be a list")

    pattern = schema.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            errors.append(f"{path}.pattern: pattern must be a string")
        else:
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"{path}.pattern: invalid pattern {pattern!r}: {exc}")

    additional_properties = schema.get("additionalProperties")
    if additional_properties is not None and not isinstance(additional_properties, bool | dict):
        errors.append(
            f"{path}.additionalProperties: additionalProperties must be a boolean or schema"
        )

    for keyword in (
        "minItems",
        "maxItems",
        "minContains",
        "maxContains",
        "minLength",
        "maxLength",
        "minProperties",
        "maxProperties",
    ):
        value = schema.get(keyword)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            errors.append(f"{path}.{keyword}: {keyword} must be a non-negative integer")

    unique_items = schema.get("uniqueItems")
    if unique_items is not None and not isinstance(unique_items, bool):
        errors.append(f"{path}.uniqueItems: uniqueItems must be a boolean")

    for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"):
        value = schema.get(keyword)
        if value is not None and (not isinstance(value, int | float) or isinstance(value, bool)):
            errors.append(f"{path}.{keyword}: {keyword} must be a number")
    multiple_of = schema.get("multipleOf")
    if (
        isinstance(multiple_of, int | float)
        and not isinstance(multiple_of, bool)
        and multiple_of <= 0
    ):
        errors.append(f"{path}.multipleOf: multipleOf must be greater than zero")

    for keyword in ("items", "additionalProperties", "contains", "not"):
        nested = schema.get(keyword)
        if isinstance(nested, dict):
            errors.extend(_schema_contract_errors(nested, f"{path}.{keyword}"))
        elif keyword in schema and keyword in {"items", "contains", "not"}:
            errors.append(f"{path}.{keyword}: {keyword} must be a schema object")

    for keyword in ("allOf", "anyOf", "oneOf"):
        nested_list = schema.get(keyword)
        if nested_list is None:
            continue
        if not isinstance(nested_list, list) or not nested_list:
            errors.append(f"{path}.{keyword}: {keyword} must be a non-empty list of schemas")
            continue
        for index, nested in enumerate(nested_list):
            if not isinstance(nested, dict):
                errors.append(f"{path}.{keyword}[{index}]: schema must be an object")
                continue
            nested_schema = cast(dict[str, Any], nested)
            errors.extend(_schema_contract_errors(nested_schema, f"{path}.{keyword}[{index}]"))

    errors.extend(_bound_order_errors(schema, path))
    return errors


def _type_contract_errors(expected_type: object, path: str) -> list[str]:
    if isinstance(expected_type, str):
        if expected_type not in SUPPORTED_SCHEMA_TYPES:
            return [f"{path}.type: unsupported type {expected_type!r}"]
        return []
    if isinstance(expected_type, list) and expected_type:
        errors: list[str] = []
        for index, item in enumerate(expected_type):
            if not isinstance(item, str) or item not in SUPPORTED_SCHEMA_TYPES:
                errors.append(f"{path}.type[{index}]: unsupported type {item!r}")
        return errors
    return [f"{path}.type: type must be a string or non-empty list of strings"]


def _bound_order_errors(schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    bound_pairs = (
        ("minItems", "maxItems"),
        ("minLength", "maxLength"),
        ("minProperties", "maxProperties"),
        ("minimum", "maximum"),
        ("exclusiveMinimum", "exclusiveMaximum"),
        ("minContains", "maxContains"),
    )
    for lower_name, upper_name in bound_pairs:
        lower = schema.get(lower_name)
        upper = schema.get(upper_name)
        if (
            isinstance(lower, int | float)
            and isinstance(upper, int | float)
            and not isinstance(lower, bool)
            and not isinstance(upper, bool)
            and lower > upper
        ):
            errors.append(f"{path}: {lower_name} must be less than or equal to {upper_name}")
    return errors


def _type_matches(value: Any, expected_type: object) -> bool:
    if isinstance(expected_type, list):
        return any(isinstance(item, str) and _type_matches(value, item) for item in expected_type)
    if not isinstance(expected_type, str):
        return True
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return False


def _items_are_unique(value: list[Any]) -> bool:
    seen: list[Any] = []
    for item in value:
        if item in seen:
            return False
        seen.append(item)
    return True


def _value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__
