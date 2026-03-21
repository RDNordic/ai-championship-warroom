#!/usr/bin/env python3
"""Configure the sandbox invoice bank account once, outside the invoice-send hot path."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tripletex_agent.client import TripletexClient  # noqa: E402
from tripletex_agent.config import AppSettings  # noqa: E402

DEFAULT_BANK_ACCOUNT_NUMBER = "12345678903"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bank-account-number",
        default=DEFAULT_BANK_ACCOUNT_NUMBER,
        help="Bank account number to configure on the invoice account",
    )
    args = parser.parse_args()

    settings = AppSettings.load()
    credentials = settings.tripletex_credentials()

    async with TripletexClient.from_credentials(credentials) as client:
        payload = await client.get(
            "/ledger/account",
            params={
                "isBankAccount": True,
                "count": 10,
                "sorting": "number",
                "fields": client.select_fields(
                    "id",
                    "number",
                    "name",
                    "isBankAccount",
                    "isInvoiceAccount",
                    "bankAccountNumber",
                ),
            },
        )
        accounts = client.unwrap_values(payload)
        invoice_accounts = [
            account
            for account in accounts
            if isinstance(account, dict) and account.get("isInvoiceAccount")
        ]
        if not invoice_accounts:
            print("No invoice bank account was available.", file=sys.stderr)
            return 1

        account = invoice_accounts[0]
        existing_number = account.get("bankAccountNumber")
        if isinstance(existing_number, str) and existing_number.strip():
            print(
                json.dumps(
                    {
                        "status": "already_configured",
                        "account_id": account.get("id"),
                        "bankAccountNumber": existing_number,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        account_id = account.get("id")
        if not isinstance(account_id, int):
            print("Invoice bank account did not include an id.", file=sys.stderr)
            return 1

        updated = await client.put(
            f"/ledger/account/{account_id}",
            json_body={"bankAccountNumber": args.bank_account_number},
        )
        print(json.dumps(client.unwrap_value(updated), indent=2, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
