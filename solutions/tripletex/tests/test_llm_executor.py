"""Tests for the LLM executor pipeline: parsing, validation, variable substitution."""

from __future__ import annotations

import asyncio

import pytest

from tripletex_agent.api_validator import ApiCallValidator
from tripletex_agent.llm_executor import (
    _maybe_rebuild_supplier_vat_voucher,
    _maybe_fix_supplier_invoice_account,
    _maybe_select_project_activity,
    _normalize_invoice_vat_types,
    _parse_steps,
    _recover_unresolved_step_vars,
    _resolve_value,
    _should_block_ledger_voucher,
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


class TestRecoverUnresolvedStepVars:
    def test_recovers_alias_drift(self):
        saved_vars = {"invoice_1001_id": 2147647069}

        path, params, json_body, notes, unresolved = _recover_unresolved_step_vars(
            "/invoice/$inv_1001_id/:payment",
            {"paidAmount": 1000},
            None,
            saved_vars,
        )

        assert path == "/invoice/2147647069/:payment"
        assert params == {"paidAmount": 1000}
        assert json_body is None
        assert unresolved == []
        assert saved_vars["inv_1001_id"] == 2147647069
        assert any("alias $invoice_1001_id" in note for note in notes)

    def test_derives_invoice_id_from_all_invoices(self):
        saved_vars = {
            "all_invoices": [
                {"id": 101, "invoiceNumber": 1},
                {"id": 102, "invoiceNumber": 2},
                {"id": 103, "invoiceNumber": 3},
            ]
        }

        path, _, _, notes, unresolved = _recover_unresolved_step_vars(
            "/invoice/$invoice_1002_id/:payment",
            None,
            None,
            saved_vars,
        )

        assert path == "/invoice/102/:payment"
        assert unresolved == []
        assert saved_vars["invoice_1002_id"] == 102
        assert any("all_invoices" in note for note in notes)

    def test_derives_overdue_customer_from_saved_invoice(self):
        saved_vars = {
            "overdue_invoice_id": 2147647085,
            "all_invoices": [
                {
                    "id": 2147647085,
                    "invoiceNumber": 5,
                    "customer": {"id": 108446256},
                }
            ],
        }

        _, _, json_body, notes, unresolved = _recover_unresolved_step_vars(
            "/ledger/voucher",
            None,
            {"postings": [{"customer": {"id": "$overdue_customer_id"}}]},
            saved_vars,
        )

        assert json_body == {"postings": [{"customer": {"id": 108446256}}]}
        assert unresolved == []
        assert saved_vars["overdue_customer_id"] == 108446256
        assert any("customer.id" in note for note in notes)

    def test_derives_supplier_invoice_from_supplier_cache(self):
        saved_vars = {
            "supplier_strand_id": 501,
            "all_supplier_invoices": [
                {"id": 7001, "supplier": {"id": 501}, "invoiceNumber": 1},
                {"id": 7002, "supplier": {"id": 999}, "invoiceNumber": 1},
            ],
        }

        path, _, _, notes, unresolved = _recover_unresolved_step_vars(
            "/supplierInvoice/$strand_invoice_id/:addPayment",
            None,
            None,
            saved_vars,
        )

        assert path == "/supplierInvoice/7001/:addPayment"
        assert unresolved == []
        assert saved_vars["strand_invoice_id"] == 7001
        assert any("all_supplier_invoices" in note for note in notes)


class _FakeTripletexClient:
    def __init__(self, values):
        self.values = values
        self.calls = []

    async def request(self, method, path, params=None, json_body=None, expected_status=None):
        self.calls.append((method, path, params))
        return {"values": self.values}


class TestFixSupplierInvoiceAccount:
    def test_reroutes_pdf_style_software_invoice(self):
        client = _FakeTripletexClient(
            [
                {
                    "id": 9001,
                    "number": 6420,
                    "name": "Leie datasystemer (software)",
                    "displayName": "6420 Leie datasystemer (software)",
                    "type": "OPERATING_EXPENSES",
                    "isInactive": False,
                },
                {
                    "id": 9002,
                    "number": 6300,
                    "name": "Leie lokaler",
                    "displayName": "6300 Leie lokaler",
                    "type": "OPERATING_EXPENSES",
                    "isInactive": False,
                },
            ]
        )
        saved_vars = {"account_6340_id": 493802732}
        json_body = {
            "description": "Leverandorfaktura Dalheim AS INV-2026-2252",
            "vendorInvoiceNumber": "INV-2026-2252",
            "postings": [
                {
                    "row": 1,
                    "account": {"id": 493802732},
                    "supplier": {"id": 108552697},
                    "description": "Programvarelisens",
                    "amount": 48300,
                    "amountCurrency": 48300,
                    "amountGross": 60375,
                    "amountGrossCurrency": 60375,
                    "vatType": {"id": 3},
                },
                {
                    "row": 2,
                    "account": {"id": 493802534},
                    "supplier": {"id": 108552697},
                    "description": "Leverandorgjeld Dalheim AS",
                    "amount": -60375,
                    "amountCurrency": -60375,
                    "amountGross": -60375,
                    "amountGrossCurrency": -60375,
                },
            ],
        }
        fixes = []

        asyncio.run(
            _maybe_fix_supplier_invoice_account(
                prompt="You received a supplier invoice (see attached PDF). Register it with the correct expense account and input VAT.",
                json_body=json_body,
                saved_vars=saved_vars,
                tripletex_client=client,
                step_fixes=fixes,
            )
        )

        assert json_body["postings"][0]["account"] == {"id": 9001}
        assert saved_vars["account_6420_id"] == 9001
        assert client.calls == [("GET", "/ledger/account", {"query": "programvare", "count": 10})]
        assert any("6340 -> 6420" in note for note in fixes)

    def test_keeps_explicit_prompt_account_number(self):
        client = _FakeTripletexClient([])
        saved_vars = {"account_6340_id": 493803262}
        json_body = {
            "description": "Facture fournisseur Prairie SARL - Services de bureau",
            "vendorInvoiceNumber": "INV-2026-6571",
            "postings": [
                {
                    "row": 1,
                    "account": {"id": 493803262},
                    "supplier": {"id": 108552609},
                    "description": "Services de bureau - Prairie SARL",
                    "amount": 24080,
                    "amountCurrency": 24080,
                    "amountGross": 30100,
                    "amountGrossCurrency": 30100,
                    "vatType": {"id": 3},
                },
                {
                    "row": 2,
                    "account": {"id": 493803064},
                    "supplier": {"id": 108552609},
                    "description": "Leverandorgjeld - Prairie SARL - INV-2026-6571",
                    "amount": -30100,
                    "amountCurrency": -30100,
                    "amountGross": -30100,
                    "amountGrossCurrency": -30100,
                },
            ],
        }

        asyncio.run(
            _maybe_fix_supplier_invoice_account(
                prompt="Nous avons recu la facture INV-2026-6571. Le montant concerne des services de bureau (compte 6340).",
                json_body=json_body,
                saved_vars=saved_vars,
                tripletex_client=client,
                step_fixes=[],
            )
        )

        assert json_body["postings"][0]["account"] == {"id": 493803262}
        assert client.calls == []


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

    def test_rejects_non_dict_items(self):
        with pytest.raises(ValueError, match="Expected JSON array of step objects"):
            _parse_steps('["bad step"]')


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

    def test_missing_required_field_is_invalid(self):
        step = {
            "step_id": "1",
            "method": "POST",
            "path": "/customer",
            "json_body": {},  # missing "name"
        }
        result = self.validator.validate_step(step)
        assert not result.valid
        assert any("missing from json_body" in e for e in result.errors)

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

    def test_validate_plan_rejects_non_dict_step(self):
        result = self.validator.validate_plan(["bad step"])
        assert not result.valid
        assert any("Step must be an object" in e for e in result.errors)

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


class TestSupplierVoucherRepair:
    def test_rebuilds_project_supplier_cost_with_explicit_input_vat(self):
        client = _FakeTripletexClient([{"id": 271001}])
        saved_vars = {}
        json_body = {
            "date": "2026-03-22",
            "description": "Leverandorkostnad Tindra AS - Systemoppgradering Brattli",
            "postings": [
                {
                    "row": 1,
                    "account": {"id": 496755318},
                    "project": {"id": 402071932},
                    "amount": 31160,
                    "amountCurrency": 31160,
                    "amountGross": 38950,
                    "amountGrossCurrency": 38950,
                    "vatType": {"id": 3},
                    "description": "Leverandorkostnad Tindra AS",
                },
                {
                    "row": 2,
                    "account": {"id": 496755107},
                    "supplier": {"id": 108568110},
                    "amount": -38950,
                    "amountCurrency": -38950,
                    "amountGross": -38950,
                    "amountGrossCurrency": -38950,
                    "description": "Leverandorgjeld Tindra AS",
                },
            ],
        }
        fixes = []

        asyncio.run(
            _maybe_rebuild_supplier_vat_voucher(
                json_body=json_body,
                saved_vars=saved_vars,
                tripletex_client=client,
                step_fixes=fixes,
            )
        )

        assert [posting["account"]["id"] for posting in json_body["postings"]] == [
            496755318,
            271001,
            496755107,
        ]
        assert json_body["postings"][0]["project"] == {"id": 402071932}
        assert json_body["postings"][1]["amount"] == pytest.approx(7790)
        assert sum(posting["amount"] for posting in json_body["postings"]) == pytest.approx(0)
        assert any("explicit input VAT" in note for note in fixes)
        assert client.calls == [("GET", "/ledger/account", {"number": "2710"})]


class TestProjectActivityRepair:
    def test_prefers_chargeable_project_activity_for_invoiced_project_timesheets(self):
        client = _FakeTripletexClient(
            [
                {
                    "id": 6150471,
                    "displayName": "Prosjektadministrasjon",
                    "isProjectActivity": True,
                    "isChargeable": False,
                    "isDisabled": False,
                    "rate": 0.0,
                },
                {
                    "id": 6150472,
                    "displayName": "Fakturerbart arbeid",
                    "isProjectActivity": True,
                    "isChargeable": True,
                    "isDisabled": False,
                    "rate": 1250.0,
                },
            ]
        )
        saved_vars = {}
        json_body = {
            "employee": {"id": 18774911},
            "project": {"id": 402071932},
            "activity": {"id": 6150471},
            "date": "2026-03-22",
            "hours": 75,
        }
        fixes = []

        asyncio.run(
            _maybe_select_project_activity(
                prompt="Registrer timer pa prosjektet og opprett kundefaktura etterpa.",
                json_body=json_body,
                saved_vars=saved_vars,
                tripletex_client=client,
                step_fixes=fixes,
            )
        )

        assert json_body["activity"] == {"id": 6150472}
        assert saved_vars["activity_id"] == 6150472
        assert any("Replaced activity 6150471" in note for note in fixes)
        assert client.calls == [("GET", "/activity", {"isProjectActivity": True, "count": 100})]


class TestLedgerVoucherBlocking:
    def test_blocks_unbalanced_ledger_voucher_errors(self):
        assert _should_block_ledger_voucher(
            "/ledger/voucher",
            ["Postings amount sum=-7790.00 does not balance to 0"],
        )
        assert not _should_block_ledger_voucher(
            "/supplierInvoice",
            ["Postings amount sum=-7790.00 does not balance to 0"],
        )


class TestInvoiceVatNormalization:
    def test_rewrites_input_and_invalid_vat_ids_to_sales_ids(self):
        json_body = {
            "invoiceDate": "2026-03-22",
            "invoiceDueDate": "2026-04-21",
            "orders": [
                {
                    "customer": {"id": 1},
                    "orderLines": [
                        {"product": {"id": 10}, "vatType": {"id": 1}},
                        {"product": {"id": 11}, "vatType": {"id": 33}},
                        {"product": {"id": 12}, "vatType": {"id": 7}},
                    ],
                }
            ],
        }
        fixes = []

        _normalize_invoice_vat_types(json_body, fixes)

        order_lines = json_body["orders"][0]["orderLines"]
        assert order_lines[0]["vatType"] == {"id": 3}
        assert order_lines[1]["vatType"] == {"id": 32}
        assert order_lines[2]["vatType"] == {"id": 6}
        assert len(fixes) == 3


class TestPlanPathNormalization:
    def test_accepts_variable_id_segments_in_catalog_paths(self):
        validator = ApiCallValidator()

        invoice_payment_step = {
            "step_id": "7",
            "method": "PUT",
            "path": "/invoice/$invoice_id/:payment",
            "params": {"paymentDate": "2026-03-22", "paymentTypeId": 1, "paidAmount": 100},
        }
        result = validator.validate_step(invoice_payment_step)
        assert result.valid

        project_update_step = {
            "step_id": "4",
            "method": "PUT",
            "path": "/project/$project_id",
            "json_body": {
                "id": "$project_id",
                "name": "CRM Integration",
                "isInternal": False,
                "projectManager": {"id": "$employee_id"},
                "startDate": "2026-03-22",
            },
        }
        result = validator.validate_step(project_update_step)
        assert result.valid
