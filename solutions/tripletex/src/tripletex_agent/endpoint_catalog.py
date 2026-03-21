"""Endpoint catalog derived from the official Tripletex swagger.json.

This module parses the swagger spec at startup and produces:
  1. ENDPOINT_CATALOG — structured list of endpoints for the API validator.
  2. catalog_as_text() — LLM-readable text for the system prompt.

Only endpoints relevant to the competition's 30 task types are included.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SWAGGER_PATH = Path(__file__).parent / "swagger.json"

# Exact paths relevant to the competition's 30 task types.
# We whitelist specific paths rather than using prefix matching
# to avoid bloating the LLM prompt with irrelevant sub-resources.
_RELEVANT_PATHS: set[str] = {
    # Customer
    "/customer", "/customer/{id}",
    # Product
    "/product", "/product/{id}",
    # Employee
    "/employee", "/employee/{id}",
    "/employee/employment", "/employee/employment/{id}",
    # Department
    "/department", "/department/{id}",
    # Project
    "/project", "/project/{id}",
    # Invoice
    "/invoice", "/invoice/{id}",
    "/invoice/paymentType", "/invoice/paymentType/{id}",
    "/invoice/{id}/:createCreditNote",
    "/invoice/{id}/:payment",
    "/invoice/{id}/:send",
    # Order + order lines
    "/order", "/order/{id}",
    "/order/orderline", "/order/orderline/{id}",
    # Travel expense + sub-resources
    "/travelExpense", "/travelExpense/{id}",
    "/travelExpense/cost", "/travelExpense/cost/{id}",
    "/travelExpense/mileageAllowance", "/travelExpense/mileageAllowance/{id}",
    "/travelExpense/perDiemCompensation", "/travelExpense/perDiemCompensation/{id}",
    "/travelExpense/accommodationAllowance", "/travelExpense/accommodationAllowance/{id}",
    "/travelExpense/costCategory", "/travelExpense/costCategory/{id}",
    # Ledger
    "/ledger/account", "/ledger/account/{id}",
    "/ledger/voucher", "/ledger/voucher/{id}",
    "/ledger/voucher/{id}/:reverse",
    "/ledger/voucher/historical/:reverseHistoricalVouchers",
    "/ledger/vatType", "/ledger/vatType/{id}",
    "/ledger/paymentTypeOut", "/ledger/paymentTypeOut/{id}",
    # Company modules
    "/company/salesmodules",
}


def _load_swagger() -> dict[str, Any]:
    with open(_SWAGGER_PATH, encoding="utf-8") as f:
        return json.load(f)


def _is_relevant(path: str) -> bool:
    return path in _RELEVANT_PATHS


def _extract_writable_fields(
    schema: dict[str, Any],
    definitions: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """Return (required, optional, ref_hints) for a schema's writable fields.

    ref_hints are strings like 'customer -> nested {id} ref' to tell the LLM
    that entity references must use {"id": X} format.
    """
    required_names = set(schema.get("required", []))
    props = schema.get("properties", {})
    required: list[str] = []
    optional: list[str] = []
    ref_hints: list[str] = []

    for field_name, field_info in sorted(props.items()):
        if field_info.get("readOnly", False):
            continue
        # Skip internal/meta fields
        if field_name in ("id", "version", "url", "changes"):
            continue

        ftype = field_info.get("type", "")
        ref = field_info.get("$ref", "").replace("#/definitions/", "")

        # Build type hint
        if ref:
            type_hint = f"object {{id}} ref to {ref}"
            ref_hints.append(f"{field_name} -> nested {{\"id\": <id>}} reference")
        elif ftype == "array":
            items = field_info.get("items", {})
            items_ref = items.get("$ref", "").replace("#/definitions/", "")
            if items_ref:
                type_hint = f"array of {items_ref}"
            else:
                type_hint = "array"
        else:
            type_hint = ftype or "unknown"

        desc = field_info.get("description", "")
        # Strip HTML tags and truncate
        desc = desc.replace("<br>", " ").split(".")[0] if desc else ""
        if len(desc) > 60:
            desc = desc[:57] + "..."

        entry = f"{field_name} ({type_hint})"
        if desc:
            entry += f" — {desc}"

        if field_name in required_names:
            required.append(entry)
        else:
            optional.append(entry)

    return required, optional, ref_hints


def _resolve_body_schema(
    parameters: list[dict[str, Any]],
    definitions: dict[str, Any],
) -> dict[str, Any] | None:
    """Find the body parameter and resolve its $ref to a schema dict."""
    for param in parameters:
        if param.get("in") == "body":
            schema = param.get("schema", {})
            ref = schema.get("$ref", "").replace("#/definitions/", "")
            if ref and ref in definitions:
                return definitions[ref]
            return schema
    return None


def build_catalog(swagger: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build the structured endpoint catalog from swagger spec."""
    if swagger is None:
        swagger = _load_swagger()

    paths = swagger.get("paths", {})
    definitions = swagger.get("definitions", {})
    catalog: list[dict[str, Any]] = []

    for path in sorted(paths.keys()):
        if not _is_relevant(path):
            continue

        for method, spec in paths[path].items():
            method = method.upper()
            if method not in ("GET", "POST", "PUT", "DELETE"):
                continue

            summary = spec.get("summary", "")
            parameters = spec.get("parameters", [])

            entry: dict[str, Any] = {
                "method": method,
                "path": path,
                "description": summary,
            }

            # Query parameters (for GET, but also for some PUT like :payment)
            required_params = [
                p["name"] for p in parameters
                if p.get("in") == "query" and p.get("required", False)
            ]
            optional_params = [
                p["name"] for p in parameters
                if p.get("in") == "query" and not p.get("required", False)
            ]
            if required_params or optional_params:
                entry["params"] = required_params + optional_params
                if required_params:
                    entry["required_params"] = required_params
                if optional_params:
                    entry["optional_params"] = optional_params

            # Body fields (for POST/PUT)
            if method in ("POST", "PUT"):
                body_schema = _resolve_body_schema(parameters, definitions)
                if body_schema:
                    required, optional, ref_hints = _extract_writable_fields(
                        body_schema, definitions
                    )
                    if required:
                        entry["required_fields"] = required
                    if optional:
                        entry["optional_fields"] = optional
                    if ref_hints:
                        entry["ref_hints"] = ref_hints

            catalog.append(entry)

    return catalog


def catalog_as_text(swagger: dict[str, Any] | None = None) -> str:
    """Render the catalog as LLM-readable text for the system prompt."""
    catalog = build_catalog(swagger)
    lines: list[str] = []
    current_group = ""

    for entry in catalog:
        # Group by resource
        path = entry["path"]
        group = path.split("/")[1] if "/" in path.lstrip("/") else path
        if group != current_group:
            current_group = group
            lines.append(f"\n--- {group.upper()} ---")

        method = entry["method"]
        desc = entry.get("description", "")
        lines.append(f"\n{method} {path}")
        if desc:
            lines.append(f"  {desc}")

        if "required_params" in entry:
            lines.append(f"  Required query params: {', '.join(entry['required_params'])}")
        if "optional_params" in entry:
            lines.append(f"  Optional query params: {', '.join(entry['optional_params'])}")
        elif "params" in entry and "required_params" not in entry:
            lines.append(f"  Query params: {', '.join(entry['params'])}")

        if "required_fields" in entry:
            lines.append("  Required fields:")
            for f in entry["required_fields"]:
                lines.append(f"    - {f}")

        if "optional_fields" in entry:
            lines.append("  Optional fields:")
            for f in entry["optional_fields"]:
                lines.append(f"    - {f}")

        # ref_hints omitted from text — already encoded in field type annotations

    return "\n".join(lines)


def catalog_index_text(swagger: dict[str, Any] | None = None) -> str:
    """Render a compact endpoint index (method + path + summary) for the system prompt.

    This is lightweight (~2K tokens) and gives the LLM awareness of all
    available endpoints without field-level detail. The LLM should then
    use lookup_endpoint() to get full schemas for the endpoints it needs.
    """
    catalog = build_catalog(swagger)
    lines: list[str] = []
    for entry in catalog:
        desc = entry.get("description", "")
        desc = desc.split(".")[0] if desc else ""
        if len(desc) > 60:
            desc = desc[:57] + "..."
        lines.append(f"{entry['method']:6s} {entry['path']:50s} {desc}")
    return "\n".join(lines)


# Pre-built catalog for the validator
ENDPOINT_CATALOG = build_catalog()
