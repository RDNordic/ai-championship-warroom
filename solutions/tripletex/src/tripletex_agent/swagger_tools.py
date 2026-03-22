"""Swagger query tools for LLM function calling.

Provides structured lookups into the full swagger.json spec,
so the LLM can query endpoint details on demand without
needing the entire catalog in the system prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SWAGGER_PATH = Path(__file__).parent / "swagger.json"


def _load_swagger() -> dict[str, Any]:
    with open(_SWAGGER_PATH, encoding="utf-8") as f:
        return json.load(f)


def _normalize_path(path: str) -> str:
    """Normalize /customer/123 to /customer/{id}."""
    parts = path.strip("/").split("/")
    return "/" + "/".join(
        "{id}" if part.isdigit() else part
        for part in parts
    )


def _resolve_ref(ref: str, definitions: dict[str, Any]) -> dict[str, Any]:
    """Resolve a $ref string to its definition."""
    name = ref.replace("#/definitions/", "")
    return definitions.get(name, {})


def _format_field(name: str, info: dict[str, Any]) -> dict[str, Any]:
    """Format a single field into a readable dict."""
    result: dict[str, Any] = {"name": name}

    if info.get("readOnly"):
        result["read_only"] = True

    ftype = info.get("type", "")
    ref = info.get("$ref", "")
    if ref:
        ref_name = ref.replace("#/definitions/", "")
        result["type"] = f"object ref → {ref_name}"
        result["format_hint"] = f'Use nested object: {{"{name}": {{"id": <int>}}}}'
    elif ftype == "array":
        items = info.get("items", {})
        items_ref = items.get("$ref", "")
        if items_ref:
            result["type"] = f"array of {items_ref.replace('#/definitions/', '')}"
        else:
            result["type"] = "array"
    else:
        result["type"] = ftype or "unknown"

    desc = info.get("description", "")
    if desc:
        result["description"] = desc[:120]

    return result


class SwaggerQueryService:
    """Provides tool implementations for querying the swagger spec."""

    def __init__(self, swagger: dict[str, Any] | None = None) -> None:
        if swagger is None:
            swagger = _load_swagger()
        self._paths = swagger.get("paths", {})
        self._definitions = swagger.get("definitions", {})

    def lookup_endpoint(self, method: str, path: str) -> dict[str, Any]:
        """Return full schema for a specific method + path.

        Returns all query params (with required flag), body fields
        (with types, required/optional, read-only), and description.
        """
        norm_path = _normalize_path(path)
        method_lower = method.lower()

        # Try exact match first, then normalized
        path_entry = self._paths.get(path) or self._paths.get(norm_path)
        if path_entry is None:
            return {"error": f"Endpoint {method} {path} not found in swagger spec"}

        spec = path_entry.get(method_lower)
        if spec is None:
            available = [m.upper() for m in path_entry.keys() if m != "parameters"]
            return {
                "error": f"Method {method} not available for {path}. Available: {available}"
            }

        result: dict[str, Any] = {
            "method": method.upper(),
            "path": path,
            "summary": spec.get("summary", ""),
        }

        # Query parameters
        parameters = spec.get("parameters", [])
        query_params = []
        for p in parameters:
            if p.get("in") == "query":
                query_params.append({
                    "name": p["name"],
                    "required": p.get("required", False),
                    "type": p.get("type", "string"),
                    "description": p.get("description", "")[:80],
                })
        if query_params:
            result["query_params"] = query_params

        # Body schema (for POST/PUT)
        for p in parameters:
            if p.get("in") == "body":
                schema = p.get("schema", {})
                ref = schema.get("$ref", "")
                if ref:
                    resolved = _resolve_ref(ref, self._definitions)
                    result["body_schema"] = self._format_schema(
                        ref.replace("#/definitions/", ""), resolved
                    )
                break

        return result

    def search_endpoints(self, keyword: str) -> list[dict[str, str]]:
        """Search for endpoints matching a keyword in path or summary."""
        keyword_lower = keyword.lower()
        results = []
        for path, methods in self._paths.items():
            for method, spec in methods.items():
                if method == "parameters":
                    continue
                summary = spec.get("summary", "")
                if (keyword_lower in path.lower()
                        or keyword_lower in summary.lower()):
                    results.append({
                        "method": method.upper(),
                        "path": path,
                        "summary": summary[:100],
                    })
        return results[:20]  # Cap at 20 results

    def get_model_schema(self, model_name: str) -> dict[str, Any]:
        """Return full schema for a swagger model definition."""
        # Try exact match
        schema = self._definitions.get(model_name)
        if schema is None:
            # Try case-insensitive
            for name, defn in self._definitions.items():
                if name.lower() == model_name.lower():
                    schema = defn
                    model_name = name
                    break
        if schema is None:
            # Fuzzy match
            matches = [n for n in self._definitions if model_name.lower() in n.lower()]
            return {
                "error": f"Model '{model_name}' not found.",
                "similar": matches[:10],
            }

        return self._format_schema(model_name, schema)

    def _format_schema(self, name: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Format a schema definition into a readable structure."""
        required_names = set(schema.get("required", []))
        props = schema.get("properties", {})

        required_fields = []
        optional_fields = []
        read_only_fields = []

        for field_name, field_info in sorted(props.items()):
            formatted = _format_field(field_name, field_info)

            if field_info.get("readOnly"):
                read_only_fields.append(formatted)
            elif field_name in required_names:
                formatted["required"] = True
                required_fields.append(formatted)
            else:
                optional_fields.append(formatted)

        result: dict[str, Any] = {"model": name}
        if required_names:
            result["required_field_names"] = sorted(required_names)
        if required_fields:
            result["required_fields"] = required_fields
        if optional_fields:
            result["optional_writable_fields"] = optional_fields
        if read_only_fields:
            result["read_only_fields_do_not_send"] = [f["name"] for f in read_only_fields]

        return result


# Tool definitions for the Anthropic API
SWAGGER_TOOLS = [
    {
        "name": "lookup_endpoint",
        "description": (
            "Look up the full schema for a specific Tripletex API endpoint. "
            "Returns all query parameters (with required/optional), "
            "body fields (with types, required/optional, read-only), "
            "and description. Call this BEFORE generating API steps "
            "to ensure you use the correct fields."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE"],
                    "description": "HTTP method",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "API path template, e.g. '/customer', '/invoice/{id}/:payment', "
                        "'/ledger/voucher'"
                    ),
                },
            },
            "required": ["method", "path"],
        },
    },
    {
        "name": "search_endpoints",
        "description": (
            "Search for Tripletex API endpoints by keyword. "
            "Returns matching endpoints with method, path, and summary. "
            "Use this when you're not sure which endpoint to use for a task."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": (
                        "Search keyword, e.g. 'payment', 'credit note', "
                        "'travel expense', 'voucher'"
                    ),
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_model_schema",
        "description": (
            "Get the full field schema for a Tripletex data model. "
            "Returns all fields with types, required/optional, and read-only status. "
            "Use this to understand nested objects like Posting, OrderLine, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model_name": {
                    "type": "string",
                    "description": (
                        "Model name, e.g. 'Posting', 'OrderLine', 'Customer', "
                        "'TravelExpense', 'Order'"
                    ),
                },
            },
            "required": ["model_name"],
        },
    },
]
