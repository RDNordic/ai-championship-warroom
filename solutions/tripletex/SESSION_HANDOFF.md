# SESSION_HANDOFF.md

## Current State

Last known leaderboard snapshot from the prior confirmed scoring run:
- Score: `5.0`
- Rank: `#221`
- Solved: `11/30`

User-reported latest submission outcome on `2026-03-21` Oslo time:
- Returned as failed with `2/8`
- The local service log does **not** expose the judge's `2/8` score breakdown; it only shows endpoint traces and workflow outcomes

Branch: `feature/tripletex-multiline-invoice`
HEAD commit: `1429bb9`
Working tree: dirty, with local uncommitted Tripletex changes

Tripletex files changed in the current working tree:
- `solutions/tripletex/SESSION_HANDOFF.md`
- `solutions/tripletex/scripts/run_prompt.py`
- `solutions/tripletex/src/tripletex_agent/planner.py`
- `solutions/tripletex/src/tripletex_agent/service.py`
- `solutions/tripletex/src/tripletex_agent/workflows/__init__.py`
- `solutions/tripletex/src/tripletex_agent/workflows/live.py`
- `solutions/tripletex/tests/test_planner.py`
- `solutions/tripletex/tests/test_workflows.py`

Unrelated repo change still present:
- `solutions/astar-island/next-steps.md`

## Runtime Status

Live origin:
- Local health check on `http://127.0.0.1:8000/health` returned `200 {"status":"ok"}` on `2026-03-21` Oslo time
- Active Tripletex `uvicorn` worker is running from `solutions/tripletex/.venv/Scripts/python.exe`

Live public endpoint:
- `https://newspapers-reform-walking-embassy.trycloudflare.com/solve`
- Current tunnel process is still alive
- Public health check on `https://newspapers-reform-walking-embassy.trycloudflare.com/health` returned `200 {"status":"ok"}` on `2026-03-21` Oslo time

Practical meaning:
- The current public `/solve` URL is still the one above
- The live worker has been restarted after the latest planner/workflow patches
- Submit/log/debug can continue immediately without another tunnel refresh unless the quick tunnel dies
- Latest log event currently on disk is the failed voucher-reversal trace at `2026-03-21 00:20:17` Oslo time
- No newer request has hit the endpoint since that trace

Workspace residue:
- `solutions/tripletex/.tmp`
- `solutions/tripletex/.pytest-tmp`

Those temp folders still have broken/blocked Windows ACLs and can interfere with full local `pytest` runs.

## What Changed This Session

1. Fixed invoice-payment handling for prompts that specify amounts excluding VAT.
   - Planner now marks `paidAmountExcludingVat=true`
   - Payment workflow now reconciles net prompt amounts against invoice gross outstanding amount before `PUT /invoice/{id}/:payment`

2. Hardened multilingual payment intent extraction.
   - Added Portuguese and Spanish payment phrases to keyword fallback
   - Reused the existing excluding-VAT amount matcher for payment prompts

3. Contained supplier invoice prompts.
   - Incoming supplier invoice prompts are now tagged as `supplierInvoice=true`
   - Outgoing `InvoiceCreateWorkflow` refuses those plans so they do not misfire into `/customer` lookup
   - Current behavior for supplier invoices is containment via fallback/stub, not full implementation

4. Patched supplier registration prompts.
   - Supplier registration prompts now carry `isSupplier=true` and `isCustomer=false`
   - Customer creation workflow now forwards those flags to `/customer`
   - Keyword routing no longer gets polluted by email local-parts like `faktura@...`

5. Preserved and extended prior Tripletex improvements already in the dirty tree.
   - deterministic order -> invoice -> payment workflow
   - multi-line invoice with per-line VAT extraction
   - invoice send intent
   - durable `/solve` trace logging and inspection tooling

6. No new code changes were made during the final bedtime handoff pass.
   - This pass was log triage, submission triage, and handoff cleanup only

7. Reconfirmed runtime and narrow test readiness.
   - Local `/health`: `200`
   - Public `/health`: `200`
   - `pytest -q tests\test_planner.py tests\test_workflows.py`: `54 passed`

8. Captured two important new live observations after the prior handoff draft.
   - One invoice-create trace failed with `403 Invalid or expired proxy token` from `nmiai-proxy`
   - One voucher-reversal trace failed before any Tripletex API call because the planner/workflow path lost the customer lookup entirely

## What Is Proven

### Live-Proven `/solve` Paths

1. Invoice payment with amount stated excluding VAT.

Prompt:

```text
El cliente Solmar SL (org. nº 939332235) tiene una factura pendiente de 46700 NOK sin IVA por "Diseño web". Registre el pago completo de esta factura.
```

Observed live behavior:
- Planner selected `InvoicePaymentWorkflow`
- Planned `paidAmount=46700.0` and `paidAmountExcludingVat=true`
- Invoice lookup returned:
  - `amountExcludingVat=46700.0`
  - `amountOutstanding=58375.0`
- Payment call used `paidAmount=58375.0`
- Updated invoice returned `amountOutstanding=0.0`

Status:
- Fully live-proven through public `/solve`
- This closes the net-vs-gross VAT payment bug
- Reconfirmed on a second later trace for `Río Verde SL` where `22500.0` excluding VAT was correctly grossed up to `28125.0`

2. Invoice create-and-send.

Prompt:

```text
Opprett og send ein faktura til kunden Fjelltopp AS (org.nr 845696993) på 38150 kr eksklusiv MVA. Fakturaen gjeld Programvarelisens.
```

Observed live behavior:
- Planner selected `InvoiceCreateWorkflow`
- Detected `sendToCustomer=true`
- Ensured invoice bank account on ledger account `364268212`
- Updated bank account number to `12345678903`
- Created invoice `2147554115` via `POST /invoice?sendToCustomer=true`

Status:
- Fully live-proven through public `/solve`

3. Travel expense creation.

Prompt:

```text
Register a travel expense for William Wilson (william.wilson@example.org) for "Client visit Trondheim". The trip lasted 2 days with per diem (daily rate 800 NOK). Expenses: flight ticket 7600 NOK and taxi 700 NOK.
```

Observed live behavior:
- Planner selected `TravelExpenseCreateWorkflow`
- Resolved employee `William Wilson`
- Created travel expense `11146210`
- Added three cost rows:
  - per diem `1600.0`
  - flight `7600.0`
  - taxi `700.0`

Status:
- Fully live-proven through public `/solve`

4. Basic customer and product creation.

Examples live-proven this session:
- customer create for `Havbris AS`
- product create for `Data Advisory`
- product create for `Havregryn`

Status:
- Stable and still working live

## What Is Only Partially Proven

1. Supplier registration patch.

Local dry-run now produces:
- `task_family=customers_products`
- `workflow=CustomerCreateWorkflow`
- `isSupplier=true`
- `isCustomer=false`
- clean supplier name extraction

But:
- the only live supplier registration trace in logs is the pre-patch bad run:
  - `Registe o fornecedor Luz do Sol Lda ...`
  - created object returned `isSupplier=false`, `isCustomer=true`

Status:
- Patched locally
- Not yet live-proven after the patch restart

2. Supplier invoice containment patch.

Local dry-run now routes the known failed Spanish supplier invoice prompt to `StubWorkflow` rather than outgoing invoice creation.

But:
- the only live supplier invoice trace in logs is still the old pre-patch failure:
  - routed to `InvoiceCreateWorkflow`
  - `GET /customer` returned no match
  - failed with `No customer matched lookup {'organizationNumber': '933305228'}`

Status:
- Containment patched locally
- Not yet live-proven after the patch restart
- Still not a real supplier-bill implementation

3. Order -> invoice -> payment.

Prompt family already patched in code:

```text
Opprett ein ordre for kunden Strandvik AS (org.nr 911845016) med produkta Skylagring (7865) til 38500 kr og Datarådgjeving (3949) til 18500 kr. Konverter ordren til faktura og registrer full betaling.
```

Status:
- Mock-tested / dry-run covered
- Not yet live-proven through public `/solve`

## Latest Known Failures / Gaps

1. Voucher reversal by customer/invoice description is currently broken on at least one real live prompt.
   - Latest trace: `44e888d3-38c8-4b46-94d9-352b2280b179`
   - Prompt family: returned payment / reverse payment so invoice becomes unpaid again
   - Planner selected `VoucherReverseWorkflow`
   - Plan contained `entities_to_find=[{"entity_type":"voucher","lookup":{}}]`
   - Workflow then failed with `Voucher lookup requires id, voucherNumber, or customer name`
   - This is a real code bug and should be fixed before the next submission

2. Transient proxy-token `403` can still sink an otherwise valid run.
   - Latest trace: `77082f85-b480-4b25-907b-65d10d318194`
   - `InvoiceCreateWorkflow` reached the first `GET /customer`
   - Proxy returned `Invalid or expired proxy token. Each submission receives a unique token - do not reuse tokens from previous submissions.`
   - Same endpoint handled other requests successfully in the same submission window, so this currently looks upstream/transient rather than a proven tunnel bug

3. Supplier invoice / incoming bill handling is not implemented.
   - It is only contained so we avoid the wrong outgoing-invoice call path.

4. Supplier registration is not yet live-confirmed after the patch.
   - Expected fix is to create a supplier-typed `/customer` record.

5. Full local test suite remains blocked by temp-dir ACL issues.
   - Targeted planner/workflow tests pass, but `pytest -q` as a whole is still not a reliable gate locally.

## Verification

Targeted commands run across the current dirty-tree session and final handoff pass:

```powershell
.venv\Scripts\pytest -q tests\test_planner.py tests\test_workflows.py
.venv\Scripts\python scripts\run_prompt.py "El cliente Solmar SL ... sin IVA ..."
.venv\Scripts\python scripts\run_prompt.py "Hemos recibido la factura INV-2026-8702 del proveedor Sierra SL ..."
.venv\Scripts\python scripts\run_prompt.py "Registe o fornecedor Luz do Sol Lda ..."
Invoke-WebRequest http://127.0.0.1:8000/health
Invoke-WebRequest https://newspapers-reform-walking-embassy.trycloudflare.com/health
Get-Process python,cloudflared
Get-Content logs\solve-events.jsonl -Tail 80
```

Results:
- targeted test suite: `54 passed`
- local health: `200`
- public health: `200`
- payment gross-up bug: live-proven fixed
- payment gross-up bug: later re-confirmed on the `Río Verde SL` live trace
- latest live failure: voucher reversal prompt lost customer lookup and failed before first Tripletex call
- latest transient live failure: invoice create prompt hit proxy `403 Invalid or expired proxy token`
- supplier registration: local dry-run fixed, live proof still pending
- supplier invoice containment: local dry-run fixed, live proof still pending
- latest user-reported judge outcome: failed with `2/8` on `2026-03-21` Oslo time

## Current Objective

Keep the public `/solve` endpoint running, but do **not** make the next submission blind.

Immediate priority is to fix the voucher-reversal extraction/lookup bug, then resubmit once and inspect logs immediately. Secondary priorities remain supplier registration, supplier invoice containment, and the still-unproven order -> invoice -> payment path.

## What Is Assumed

- The public quick tunnel URL remains valid until the current `cloudflared` process dies
- Tripletex accepts `isSupplier` / `isCustomer` on `/customer` create the way local tests assume
- Supplier invoice tasks will continue to appear often enough that a containment-only path is still materially better than the old wrong outgoing-invoice behavior
- The latest proxy-token `403` was transient/upstream, not a deterministic credential-reuse bug in the current service wiring
- The user-reported `2/8` result came from the same submission window as the newest traces, but the service log cannot map judge scoring to exact trace IDs

## Next Highest-Priority Task

1. Fix voucher reversal extraction before the next submission.
   - Preserve `customerName` and/or `organizationNumber` for returned-payment prompts
   - Target the live-broken trace family represented by `44e888d3-38c8-4b46-94d9-352b2280b179`
   - Goal: let `VoucherReverseWorkflow` reach its customer -> invoice -> voucher fallback path instead of dying on empty lookup

2. Re-run the narrow local gate and keep the current worker + tunnel alive.
   - `.\.venv\Scripts\pytest -q tests\test_planner.py tests\test_workflows.py`
   - `Invoke-WebRequest` local/public health
   - Avoid unnecessary restarts unless the worker or tunnel actually dies

3. Submit once after the voucher-reversal fix and inspect logs immediately.
   - Watch first for the reversal prompt family
   - If the same proxy-token `403` repeats, investigate latency/credential handling before spending more submissions

4. After that, continue the previous validation queue.
   - supplier registration after the patch
   - supplier invoice containment after the patch
   - order -> invoice -> payment

## Key Files

- Planner: `src/tripletex_agent/planner.py`
- Live workflows: `src/tripletex_agent/workflows/live.py`
- Workflow registry export: `src/tripletex_agent/workflows/__init__.py`
- Service wiring: `src/tripletex_agent/service.py`
- Local prompt runner: `scripts/run_prompt.py`
- Solve logs: `logs/solve-events.jsonl`
- Tests: `tests/test_planner.py`, `tests/test_workflows.py`

## Restart Prompt

```text
Branch: feature/tripletex-multiline-invoice
HEAD: 1429bb9
There are uncommitted Tripletex changes in planner/workflows/tests and the handoff file.

Read solutions/tripletex/SESSION_HANDOFF.md first.

Public endpoint at handoff time:
https://newspapers-reform-walking-embassy.trycloudflare.com/solve

Priority:
1. Keep the current uvicorn + cloudflared pair alive if possible
2. Fix voucher reversal extraction before the next submission
3. Re-run the narrow local test gate
4. Submit once and inspect logs immediately
5. Specifically validate:
   - supplier registration after the patch
   - supplier invoice containment after the patch
   - order -> invoice -> payment

Important:
- payment excluding VAT -> gross outstanding is now live-proven fixed
- payment excluding VAT -> gross outstanding was re-confirmed on a second later live trace
- invoice create-and-send is live-proven
- travel expense create is live-proven
- latest real live bug is voucher reversal with empty lookup (`44e888d3-38c8-4b46-94d9-352b2280b179`)
- latest transient live failure is proxy-token `403` on invoice create (`77082f85-b480-4b25-907b-65d10d318194`)
- user reported the latest submission came back failed with `2/8`
- supplier registration is only locally proven after the patch
- supplier invoice handling is only contained, not implemented
- full pytest is still blocked by the local Windows temp ACL issue
```
