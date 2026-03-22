# SESSION_HANDOFF.md

## Checkpoint (2026-03-22 ~08:00 CET)

**Total score: ~53.2 (leaderboard). 30/30 tasks attempted, 234+ submissions.**

All code fixes deployed. Farming mode — submitting runs to maximize best-per-task scores. API key issue (credits ran out ~01:00) resolved by switching to AD's key on Cloud Run via GCP console.

**Branch: `tripletex/complex-multi-step-project`** (NOT main — needs merge before final submission)

## Deployment

- **Service:** `captains-tripletex` on Cloud Run
- **Project:** `nmiai-490717`, region `europe-north1`
- **URL:** `https://captains-tripletex-339414168231.europe-north1.run.app`
- **Submission:** `https://app.ainm.no/submit/tripletex`
- **ANTHROPIC_API_KEY:** set via GCP Cloud Run console (Edit & Deploy New Revision → Variables & Secrets). Currently AD's key (nm-i-ai workspace).
- **CLOUDSDK_CONFIG:** local `.gcloud-config/` dir (gitignored) to avoid Windows NTUSER.DAT permission issue
- **IMPORTANT:** After each `deploy-ko.ps1`, you must re-set the API key via GCP console or `gcloud run services update` — the deploy creates a new revision that may lose the env var.

## Iteration Cycle

1. **Deploy:** `.\scripts\deploy-ko.ps1` (from `solutions\tripletex\`)
2. **Re-set API key** if deploy overwrites it (check via GCP console)
3. **Submit:** click on app.ainm.no (max 3 concurrent), check score
4. **Post-score:** `.\scripts\post-score.ps1` (captures Cloud Run logs + git pull)
5. **Handoff:** paste score + log file path to Claude
6. **Claude fixes:** review logs, edit code
7. **Claude commits + pushes** → back to step 1

## Per-Task Leaderboard Breakdown

| Tasks | Best Score | Status |
|-------|-----------|--------|
| 01-08 (simple) | 2.00 each | Maxed out |
| 09 | 4.00 | Strong |
| 10 | 2.67 | OK |
| 11 | 0 (4 tries) | Never scored — unknown task type |
| 12 | 0 (11 tries) | Never scored — likely custom dimensions |
| 13 | 2.50 | OK |
| 14 | 4.00 | Strong |
| 15 | 3.33 | Good |
| 16 | 4.00 | Strong |
| 17 | 0 (10 tries) | Never scored — likely cost analysis |
| 18 | 1.00 | Low |
| 19 | 2.45 | OK |
| 20 | 0.60 | Low |
| 21 | 0 (6 tries) | Never scored |
| 22 | 0 (10 tries) | Never scored — likely bank recon supplier side |
| 23 | 0.60 | Low |
| 24 | 2.25 | OK |
| 25 | 1.50 | OK |
| 26 | 3.75 | Strong |
| 27 | 2.10 | OK |
| 28 | 0.60 | Low |
| 29 | 1.09 | Low |
| 30 | 1.80 | OK |

## What Works Well (consistently scoring)

- Departments, employees, customers, products, suppliers — simple creation tasks (8/8)
- Invoice creation and send (7-8/8)
- Credit notes (6/6)
- Project creation (7/7)
- Agio/currency tasks (7/10)
- Monthly close / ledger vouchers (10/10 after account lookup fix)
- Payroll (8/8 after recipe added)
- Multi-step tasks with variable extraction
- Self-correction on 422 errors (1 retry)
- Overdue invoice + surcharge + partial payment (up to 11/14)
- Employee creation from PDF contracts (18/22)
- Travel expenses (partial — travelDetails fix works, per diem/cost still flaky)

## What Still Fails (zero-score task types)

- **Custom dimensions** — No API endpoint in swagger for creating free dimensions
- **Cost analysis** — LLM can't see posting amounts (fields param stripped from GETs)
- **Bank reconciliation (supplier side)** — Supplier invoices don't exist in sandbox
- **Full project lifecycle** — Activity linkage fails at timesheet entry

## Fixes Applied (23 total)

1. `.gcloudignore` excluding prompt templates — fixed
2. `NameError` on unresolved variables — fixed
3. Variable extraction hardened — bracket notation, value.X fallback
4. JSON parsing robustness — bracket-depth matching
5. Better error logging — `repr(exc)` fallback
6. Non-dict correction steps — skip gracefully
7. Field name renames — `voucherDate→date`, `address→postalAddress`
8. Strip `fields` param from GETs — prevents hallucinated field names
9. Retry on proxy timeouts — 3 attempts with backoff
10. Pre-flight bank account setup — auto-configures bank account on sandbox
11. Auto-inject orderDate/deliveryDate on invoices
12. Auto-inject voucher date
13. Expense voucher recipe in system prompt
14. Block unbalanced vouchers
15. Auto-fallback on empty entity lookups
16. Account lookup recipe in system prompt
17. Auto-inject employee refs into voucher postings
18. VAT auto-correction on voucher postings
19. **Account lookup query→number conversion** — fixes all account lookups returning wrong ID
20. **Bank reconciliation recipe** — list all invoices, match by name/amount
21. **Payroll recipe** — 5-posting pattern with tax, AGA, net pay
22. **Travel expense recipe** — travelDetails required for reiseregning type
23. **Nested path fallback** — collapse deep variable extraction paths

## Key Files

- `src/tripletex_agent/app.py` — FastAPI entrypoint (`/health`, `/solve`, `/logs`)
- `src/tripletex_agent/llm_executor.py` — main executor + system prompt with 13 recipes
- `src/tripletex_agent/client.py` — Tripletex API client (with retry logic)
- `src/tripletex_agent/schema_validator.py` — validates/fixes LLM-generated request bodies
- `src/tripletex_agent/service.py` — `build_default_service()` requires `ANTHROPIC_API_KEY`
- `src/tripletex_agent/prompts/retry_correction.md` — self-correction prompt template
- `scripts/deploy-ko.ps1` — build + deploy to Cloud Run
- `.gcloudignore` — excludes test/docs from Cloud Build (KEEP prompt .md files!)

## Architecture

```
POST /solve
  → LLM Phase 1 (Haiku 4.5): tool calls to look up Tripletex API schemas
  → LLM Phase 2 (Sonnet 4.6): generate ordered API call steps as JSON array
  → Execute steps sequentially, saving response IDs as variables
  → Auto-fixes: account lookup query→number, VAT amounts, employee refs, dates
  → On failure: self-correction via retry_correction.md prompt (1 retry)
  → Return {"status": "completed"}
```
