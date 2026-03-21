"""Pydantic-based schema validation derived from swagger.json.

Builds dynamic Pydantic models for each POST/PUT endpoint body schema.
Validates and auto-fixes LLM-generated json_body before sending to Tripletex.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

logger = logging.getLogger(__name__)

_SWAGGER_PATH = Path(__file__).parent / "swagger.json"


@dataclass
class SchemaValidationResult:
    """Result of validating and cleaning a json_body."""

    cleaned_body: dict[str, Any]
    valid: bool
    errors: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    fields_removed: list[str] = field(default_factory=list)


def _load_swagger() -> dict[str, Any]:
    with open(_SWAGGER_PATH, encoding="utf-8") as f:
        return json.load(f)


def _normalize_path(path: str) -> str:
    """Normalize /customer/123 to /customer/{id}."""
    parts = path.strip("/").split("/")
    return "/" + "/".join(
        "{id}" if part.isdigit() or (part.startswith("{") and part.endswith("}"))
        else part
        for part in parts
    )


def _resolve_schema(ref_or_schema: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    """Resolve a $ref to the actual schema definition."""
    ref = ref_or_schema.get("$ref", "")
    if ref:
        def_name = ref.replace("#/definitions/", "")
        return definitions.get(def_name, {})
    return ref_or_schema


def _build_field_info(
    schema: dict[str, Any],
    definitions: dict[str, Any],
) -> dict[str, _FieldSpec]:
    """Extract field specs from a swagger schema definition."""
    props = schema.get("properties", {})
    required_names = set(schema.get("required", []))
    fields: dict[str, _FieldSpec] = {}

    for name, prop in props.items():
        # Skip meta fields that are never sent by users
        if name in ("url", "changes"):
            continue

        read_only = prop.get("readOnly", False)
        ftype = prop.get("type", "")
        ref = prop.get("$ref", "")
        is_required = name in required_names
        is_ref = bool(ref)

        # Determine the python type for validation
        if ref:
            python_type = "ref"  # expects {"id": int}
        elif ftype == "string":
            python_type = "string"
        elif ftype == "integer":
            python_type = "integer"
        elif ftype == "number":
            python_type = "number"
        elif ftype == "boolean":
            python_type = "boolean"
        elif ftype == "array":
            python_type = "array"
        elif ftype == "object":
            python_type = "object"
        else:
            python_type = "unknown"

        fields[name] = _FieldSpec(
            name=name,
            python_type=python_type,
            required=is_required,
            read_only=read_only,
            is_ref=is_ref,
        )

    return fields


@dataclass(frozen=True)
class _FieldSpec:
    """Metadata about a single field in a schema."""

    name: str
    python_type: str  # string, integer, number, boolean, array, ref, object
    required: bool
    read_only: bool
    is_ref: bool


@dataclass(frozen=True)
class _EndpointSchema:
    """Schema for a specific method+path combination."""

    method: str
    path: str
    fields: dict[str, _FieldSpec]


class SchemaValidator:
    """Validates json_body against swagger-derived schemas.

    Performs three levels of validation:
    1. Remove read-only fields (auto-fix)
    2. Remove unknown fields (auto-fix)
    3. Check required fields and types (report errors)
    """

    def __init__(self, swagger: dict[str, Any] | None = None) -> None:
        if swagger is None:
            swagger = _load_swagger()
        self._schemas = self._build_schemas(swagger)

    def _build_schemas(self, swagger: dict[str, Any]) -> dict[tuple[str, str], _EndpointSchema]:
        """Build endpoint schemas from swagger spec."""
        paths = swagger.get("paths", {})
        definitions = swagger.get("definitions", {})
        schemas: dict[tuple[str, str], _EndpointSchema] = {}

        for path, methods in paths.items():
            for method, spec in methods.items():
                method = method.upper()
                if method not in ("POST", "PUT"):
                    continue

                # Find body parameter
                parameters = spec.get("parameters", [])
                body_param = next(
                    (p for p in parameters if p.get("in") == "body"),
                    None,
                )
                if body_param is None:
                    continue

                body_schema = body_param.get("schema", {})
                resolved = _resolve_schema(body_schema, definitions)
                if not resolved.get("properties"):
                    continue

                fields = _build_field_info(resolved, definitions)
                schemas[(method, path)] = _EndpointSchema(
                    method=method,
                    path=path,
                    fields=fields,
                )

        return schemas

    def validate_and_clean(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None,
    ) -> SchemaValidationResult:
        """Validate json_body and auto-fix what we can.

        Returns a SchemaValidationResult with:
        - cleaned_body: the body with fixes applied
        - valid: True if no blocking errors remain
        - errors: list of issues that couldn't be auto-fixed
        - fixes_applied: list of auto-fixes that were applied
        - fields_removed: list of field names removed
        """
        if json_body is None:
            return SchemaValidationResult(cleaned_body={}, valid=True)

        norm_path = _normalize_path(path)
        schema = self._schemas.get((method, norm_path))

        if schema is None:
            # No schema found — can't validate, pass through
            return SchemaValidationResult(cleaned_body=dict(json_body), valid=True)

        cleaned = dict(json_body)
        errors: list[str] = []
        fixes: list[str] = []
        removed: list[str] = []

        # 1. Remove read-only fields
        for field_name, spec in schema.fields.items():
            if spec.read_only and field_name in cleaned:
                del cleaned[field_name]
                removed.append(field_name)
                fixes.append(f"Removed read-only field '{field_name}'")

        # 2. Remove unknown fields (not in schema)
        known_fields = set(schema.fields.keys())
        # Always allow 'id' and 'version' — they're used for updates
        known_fields.add("id")
        known_fields.add("version")
        unknown = [k for k in cleaned if k not in known_fields]
        for field_name in unknown:
            del cleaned[field_name]
            removed.append(field_name)
            fixes.append(f"Removed unknown field '{field_name}'")

        # 3. Check required fields
        for field_name, spec in schema.fields.items():
            if spec.required and field_name not in cleaned:
                # id is often in the path, not the body
                if field_name == "id":
                    continue
                errors.append(f"Missing required field '{field_name}'")

        # 4. Type coercion and validation
        for field_name in list(cleaned.keys()):
            if field_name not in schema.fields:
                continue
            spec = schema.fields[field_name]
            value = cleaned[field_name]

            # Skip None values
            if value is None:
                continue

            # Skip $variable references — they'll be substituted later
            if isinstance(value, str) and value.startswith("$"):
                continue

            coerced = self._coerce_type(field_name, value, spec)
            if coerced is not _COERCE_FAILED:
                if coerced is not value:
                    cleaned[field_name] = coerced
                    fixes.append(
                        f"Coerced '{field_name}' from {type(value).__name__} to {spec.python_type}"
                    )
            else:
                errors.append(
                    f"Field '{field_name}' has wrong type: expected {spec.python_type}, "
                    f"got {type(value).__name__}"
                )

        valid = len(errors) == 0
        if fixes:
            logger.info("Auto-fixed json_body for %s %s: %s", method, path, fixes)
        if errors:
            logger.warning("Validation errors for %s %s: %s", method, path, errors)

        return SchemaValidationResult(
            cleaned_body=cleaned,
            valid=valid,
            errors=errors,
            fixes_applied=fixes,
            fields_removed=removed,
        )

    def _coerce_type(
        self, field_name: str, value: Any, spec: _FieldSpec
    ) -> Any:
        """Try to coerce a value to the expected type. Returns _COERCE_FAILED on failure."""
        if spec.python_type == "string":
            if isinstance(value, str):
                return value
            if isinstance(value, (int, float)):
                return str(value)
            return _COERCE_FAILED

        if spec.python_type == "integer":
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, float) and value == int(value):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    return _COERCE_FAILED
            return _COERCE_FAILED

        if spec.python_type == "number":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return _COERCE_FAILED
            return _COERCE_FAILED

        if spec.python_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                if value.lower() in ("true", "1", "yes"):
                    return True
                if value.lower() in ("false", "0", "no"):
                    return False
            return _COERCE_FAILED

        if spec.python_type == "ref":
            # Expect {"id": int_or_$var}
            if isinstance(value, dict) and "id" in value:
                return value
            # Common LLM mistake: flat integer instead of {"id": X}
            if isinstance(value, int):
                return {"id": value}
            return _COERCE_FAILED

        if spec.python_type == "array":
            if isinstance(value, list):
                return value
            return _COERCE_FAILED

        if spec.python_type == "object":
            if isinstance(value, dict):
                return value
            return _COERCE_FAILED

        # Unknown type — pass through
        return value


    def describe_endpoint_fields(self, method: str, path: str) -> str:
        """Return a human-readable description of accepted fields for an endpoint."""
        norm_path = _normalize_path(path)
        schema = self._schemas.get((method, norm_path))
        if schema is None:
            return f"No schema found for {method} {norm_path}"

        lines: list[str] = []
        required = []
        optional = []
        for spec in sorted(schema.fields.values(), key=lambda s: s.name):
            if spec.read_only:
                continue
            marker = "REQUIRED" if spec.required else "optional"
            type_desc = spec.python_type
            if spec.is_ref:
                type_desc = 'nested {"id": <int>}'
            entry = f"  - {spec.name} ({type_desc}) [{marker}]"
            if spec.required:
                required.append(entry)
            else:
                optional.append(entry)

        if required:
            lines.append("Required:")
            lines.extend(required)
        if optional:
            lines.append("Optional:")
            lines.extend(optional)
        return "\n".join(lines) if lines else "No writable fields found"


# Sentinel for failed coercion
_COERCE_FAILED = object()
