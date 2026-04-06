"""Minimal JSON schema parsing and validation helpers."""

from __future__ import annotations

import json


def parse_and_validate_json_output(
    output_text: str,
    output_schema: dict[str, object],
) -> object:
    """Parse a JSON object and validate it against a minimal schema subset."""

    candidate = _strip_json_code_fence(output_text).strip()
    if not candidate:
        raise RuntimeError("Structured output was empty.")

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Structured output was not valid JSON.") from exc

    _validate_schema(payload, output_schema, path="$")
    return payload


def _strip_json_code_fence(output_text: str) -> str:
    """Strip one surrounding markdown code fence when present."""

    stripped = output_text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped

    opening = lines[0].strip().lower()
    closing = lines[-1].strip()
    if closing != "```":
        return stripped
    if opening not in {"```", "```json"}:
        return stripped
    return "\n".join(lines[1:-1])


def _validate_schema(payload: object, schema: dict[str, object], *, path: str) -> None:
    """Validate a payload against the schema subset used by the bench."""

    schema_type = schema.get("type")
    if schema_type == "object":
        _validate_object(payload, schema, path=path)
        return
    if schema_type == "array":
        _validate_array(payload, schema, path=path)
        return
    if schema_type == "string":
        if not isinstance(payload, str):
            raise RuntimeError(f"{path} must be a string.")
        _validate_enum(payload, schema, path=path)
        return
    if schema_type == "boolean":
        if not isinstance(payload, bool):
            raise RuntimeError(f"{path} must be a boolean.")
        return
    if schema_type == "integer":
        if isinstance(payload, bool) or not isinstance(payload, int):
            raise RuntimeError(f"{path} must be an integer.")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int) and payload < minimum:
            raise RuntimeError(f"{path} must be >= {minimum}.")
        if isinstance(maximum, int) and payload > maximum:
            raise RuntimeError(f"{path} must be <= {maximum}.")
        return

    raise RuntimeError(f"{path} uses unsupported schema type: {schema_type!r}.")


def _validate_object(payload: object, schema: dict[str, object], *, path: str) -> None:
    """Validate an object payload."""

    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must be an object.")

    properties = schema.get("properties")
    required = schema.get("required", [])
    additional_properties = schema.get("additionalProperties", True)

    if not isinstance(properties, dict):
        raise RuntimeError(f"{path} object schema is missing properties.")
    if not isinstance(required, list):
        raise RuntimeError(f"{path} object schema has invalid required list.")

    for key in required:
        if not isinstance(key, str):
            raise RuntimeError(f"{path} object schema has non-string required key.")
        if key not in payload:
            raise RuntimeError(f"{path}.{key} is required.")

    if additional_properties is False:
        extra_keys = sorted(set(payload) - set(properties))
        if extra_keys:
            raise RuntimeError(f"{path} has unexpected properties: {', '.join(extra_keys)}.")

    for key, value in payload.items():
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            if additional_properties is False:
                raise RuntimeError(f"{path}.{key} is not allowed.")
            continue
        _validate_schema(value, property_schema, path=f"{path}.{key}")


def _validate_array(payload: object, schema: dict[str, object], *, path: str) -> None:
    """Validate an array payload."""

    if not isinstance(payload, list):
        raise RuntimeError(f"{path} must be an array.")

    item_schema = schema.get("items")
    if not isinstance(item_schema, dict):
        raise RuntimeError(f"{path} array schema is missing items.")

    for index, item in enumerate(payload):
        _validate_schema(item, item_schema, path=f"{path}[{index}]")


def _validate_enum(payload: str, schema: dict[str, object], *, path: str) -> None:
    """Validate enum constraints when present."""

    enum = schema.get("enum")
    if enum is None:
        return
    if not isinstance(enum, list) or not all(isinstance(item, str) for item in enum):
        raise RuntimeError(f"{path} schema has invalid enum.")
    if payload not in enum:
        raise RuntimeError(f"{path} must be one of: {', '.join(enum)}.")
