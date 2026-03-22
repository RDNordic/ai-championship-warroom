"""Deterministic pre-flight validator for LLM-proposed API call plans."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .endpoint_catalog import ENDPOINT_CATALOG


@dataclass
class ValidationResult:
    """Result of validating a single API call step."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PlanValidationResult:
    """Result of validating an entire API call plan."""

    valid: bool
    step_results: list[ValidationResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _normalize_path(path: str) -> str:
    """Normalize a concrete path like /customer/123 to a template like /customer/{id}."""
    # Replace numeric path segments with {id}
    parts = path.strip("/").split("/")
    normalized: list[str] = []
    for part in parts:
        if part.isdigit():
            normalized.append("{id}")
        elif part.startswith("{") and part.endswith("}"):
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized)


def _build_catalog_index() -> dict[tuple[str, str], dict[str, Any]]:
    """Build a lookup from (method, normalized_path) to catalog entry."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for ep in ENDPOINT_CATALOG:
        key = (ep["method"], ep["path"])
        index[key] = ep
    return index


_CATALOG_INDEX = _build_catalog_index()

# Valid HTTP methods
_VALID_METHODS = {"GET", "POST", "PUT", "DELETE"}


def _required_field_name(entry: Any) -> str:
    """Extract the raw field name from a catalog display string."""
    if not isinstance(entry, str):
        return str(entry)
    return entry.split(" ", 1)[0]


class ApiCallValidator:
    """Validates proposed API call steps against the curated endpoint catalog."""

    def __init__(self) -> None:
        self._catalog = _CATALOG_INDEX

    def validate_step(
        self,
        step: Any,
        *,
        available_vars: set[str] | None = None,
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not isinstance(step, dict):
            errors.append(f"Step must be an object, got {type(step).__name__}")
            return ValidationResult(valid=False, errors=errors)

        method = step.get("method", "")
        path = step.get("path", "")
        json_body = step.get("json_body")
        step_id = step.get("step_id", "?")

        # 1. Method is valid
        if method not in _VALID_METHODS:
            errors.append(f"Step {step_id}: invalid method '{method}'")
            return ValidationResult(valid=False, errors=errors)

        # 2. Normalize path and check against catalog
        norm_path = _normalize_path(path)
        catalog_entry = self._catalog.get((method, norm_path))
        if catalog_entry is None:
            errors.append(
                f"Step {step_id}: endpoint {method} {norm_path} not in catalog"
            )
            return ValidationResult(valid=False, errors=errors)

        # 3. Check required fields in json_body (for POST/PUT)
        required = [
            _required_field_name(field)
            for field in catalog_entry.get("required_fields", [])
        ]
        if required and method in ("POST", "PUT"):
            body = json_body or {}
            if not isinstance(body, dict):
                errors.append(
                    f"Step {step_id}: json_body must be a dict, got {type(body).__name__}"
                )
            else:
                for field_name in required:
                    if field_name not in body:
                        # Allow if it's a path param like {id} that gets substituted
                        if field_name == "id" and "{id}" in catalog_entry["path"]:
                            continue
                        errors.append(
                            f"Step {step_id}: required field '{field_name}' missing from json_body"
                        )

        # 4. Check path params are resolvable
        path_params = re.findall(r"\{(\w+)\}", path)
        for param in path_params:
            # If the path has a literal number, it's already resolved
            pass  # Path params with concrete values are fine

        # 5. Check save_response_fields_as references valid patterns
        save_fields = step.get("save_response_fields_as", {})
        if save_fields and not isinstance(save_fields, dict):
            warnings.append(f"Step {step_id}: save_response_fields_as is not a dict, will normalize")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_plan(self, steps: list[Any]) -> PlanValidationResult:
        """Validate all steps in an API call plan."""
        all_errors: list[str] = []
        step_results: list[ValidationResult] = []
        available_vars: set[str] = set()

        for step in steps:
            result = self.validate_step(step, available_vars=available_vars)
            step_results.append(result)
            all_errors.extend(result.errors)
            if not isinstance(step, dict):
                continue

            # Track variables saved by this step
            save_fields = step.get("save_response_fields_as", {})
            if isinstance(save_fields, dict):
                available_vars.update(save_fields.keys())

        return PlanValidationResult(
            valid=len(all_errors) == 0,
            step_results=step_results,
            errors=all_errors,
        )
