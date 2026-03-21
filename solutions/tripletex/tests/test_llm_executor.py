"""Tests for the LLM executor pipeline: parsing, validation, variable substitution."""

from __future__ import annotations

import pytest

from tripletex_agent.api_validator import ApiCallValidator
from tripletex_agent.llm_executor import (
    _parse_steps,
    _resolve_value,
    _substitute_vars,
)

# ── _resolve_value ────────────────────────────────────────────


class TestResolveValue:
    def test_simple_path(self):
        assert _resolve_value({"value": {"id": 42}}, "value.id") == 42

    def test_nested_path(self):
        data = {"value": {"customer": {"id": 7}}}
        assert _resolve_value(data, "value.customer.id") == 7

    def test_missing_key(self):
        assert _resolve_value({"value": {}}, "value.id") is None

    def test_none_input(self):
        assert _resolve_value(None, "value.id") is None

    def test_top_level(self):
        assert _resolve_value({"id": 99}, "id") == 99


# ── _substitute_vars ─────────────────────────────────────────


class TestSubstituteVars:
    def test_string_replacement(self):
        assert _substitute_vars("$customer_id", {"customer_id": 42}) == 42

    def test_embedded_in_path(self):
        result = _substitute_vars("/customer/$cid/invoice", {"cid": 5})
        assert result == "/customer/5/invoice"

    def test_dict_replacement(self):
        body = {"customer": {"id": "$cid"}, "name": "Test"}
        result = _substitute_vars(body, {"cid": 10})
        assert result == {"customer": {"id": 10}, "name": "Test"}

    def test_list_replacement(self):
        items = [{"id": "$order_id"}, {"id": "$order_id2"}]
        result = _substitute_vars(items, {"order_id": 1, "order_id2": 2})
        assert result == [{"id": 1}, {"id": 2}]

    def test_no_vars(self):
        assert _substitute_vars("plain text", {}) == "plain text"

    def test_numeric_passthrough(self):
        assert _substitute_vars(42, {"x": 1}) == 42


# ── _parse_steps ─────────────────────────────────────────────


class TestParseSteps:
    def test_plain_json(self):
        raw = '[{"step_id": "1", "method": "GET", "path": "/customer"}]'
        steps = _parse_steps(raw)
        assert len(steps) == 1
        assert steps[0]["method"] == "GET"

    def test_with_markdown_fences(self):
        raw = '```json\n[{"step_id": "1", "method": "POST", "path": "/customer"}]\n```'
        steps = _parse_steps(raw)
        assert len(steps) == 1

    def test_embedded_in_text(self):
        raw = 'Here are the steps:\n[{"step_id": "1", "method": "GET", "path": "/product"}]\nDone.'
        steps = _parse_steps(raw)
        assert steps[0]["path"] == "/product"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Could not parse"):
            _parse_steps("this is not json at all")

    def test_non_array_raises(self):
        with pytest.raises(ValueError, match="Expected JSON array"):
            _parse_steps('{"not": "an array"}')


# ── ApiCallValidator ─────────────────────────────────────────


class TestApiCallValidator:
    def setup_method(self):
        self.validator = ApiCallValidator()

    def test_valid_get_customer(self):
        step = {"step_id": "1", "method": "GET", "path": "/customer"}
        result = self.validator.validate_step(step)
        assert result.valid

    def test_valid_post_customer(self):
        step = {
            "step_id": "1",
            "method": "POST",
            "path": "/customer",
            "json_body": {"name": "Test Customer"},
        }
        result = self.validator.validate_step(step)
        assert result.valid

    def test_invalid_method(self):
        step = {"step_id": "1", "method": "PATCH", "path": "/customer"}
        result = self.validator.validate_step(step)
        assert not result.valid
        assert any("invalid method" in e for e in result.errors)

    def test_unknown_endpoint(self):
        step = {"step_id": "1", "method": "GET", "path": "/nonexistent"}
        result = self.validator.validate_step(step)
        assert not result.valid
        assert any("not in catalog" in e for e in result.errors)

    def test_missing_required_field_warning(self):
        step = {
            "step_id": "1",
            "method": "POST",
            "path": "/customer",
            "json_body": {},  # missing "name"
        }
        result = self.validator.validate_step(step)
        # Warnings about missing fields, but step is still "valid" (not blocking)
        assert result.valid
        assert len(result.warnings) > 0

    def test_put_with_id_in_path(self):
        step = {
            "step_id": "1",
            "method": "PUT",
            "path": "/customer/123",
            "json_body": {"id": 123, "name": "Updated"},
        }
        result = self.validator.validate_step(step)
        assert result.valid

    def test_validate_plan_chains_vars(self):
        steps = [
            {
                "step_id": "1",
                "method": "POST",
                "path": "/customer",
                "json_body": {"name": "Test"},
                "save_response_fields_as": {"customer_id": "value.id"},
            },
            {
                "step_id": "2",
                "method": "GET",
                "path": "/invoice",
                "params": {"customerId": "$customer_id"},
            },
        ]
        result = self.validator.validate_plan(steps)
        assert result.valid

    def test_validate_plan_with_invalid_step(self):
        steps = [
            {"step_id": "1", "method": "PATCH", "path": "/customer"},
        ]
        result = self.validator.validate_plan(steps)
        assert not result.valid

    def test_delete_endpoint(self):
        step = {"step_id": "1", "method": "DELETE", "path": "/customer/42"}
        result = self.validator.validate_step(step)
        assert result.valid

    def test_travel_expense_post(self):
        step = {
            "step_id": "1",
            "method": "POST",
            "path": "/travelExpense",
            "json_body": {
                "employee": {"id": 1},
                "title": "Business trip",
                "departureDate": "2026-03-20",
                "returnDate": "2026-03-22",
            },
        }
        result = self.validator.validate_step(step)
        assert result.valid

    def test_ledger_voucher_reverse(self):
        step = {
            "step_id": "1",
            "method": "PUT",
            "path": "/ledger/voucher/5/:reverse",
            "json_body": {"date": "2026-03-20"},
        }
        result = self.validator.validate_step(step)
        assert result.valid
