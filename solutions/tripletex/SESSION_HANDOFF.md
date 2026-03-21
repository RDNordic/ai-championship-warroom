# SESSION_HANDOFF.md

## Checkpoint (2026-03-21 ~19:00 CET)

Tripletex agent is deployed to Google Cloud Run and actively scoring. Deploy-score-fix cycle running from Windows/PowerShell. Chris has a parallel instance (`tripletex-agent`).

**Current best score: 8/8 on simple tasks. Complex tasks (travel expense, bank reconciliation, ledger corrections) still failing.**

**Branch: `tripletex/complex-multi-step-project`**

## Deployment

- **Service:** `captains-tripletex` on Cloud Run (KO's instance)
- **Project:** `nmiai-490717`, region `europe-north1`
- **URL:** `https://captains-tripletex-339414168231.europe-north1.run.app`
- **Submission:** `https://app.ainm.no/submit/tripletex`
- **ANTHROPIC_API_KEY:** set as env var on Cloud Run (not in code, not via Secret Manager)
- **CLOUDSDK_CONFIG:** local `.gcloud-config/` dir to avoid Windows NTUSER.DAT permission issue

## Iteration Cycle

1. **Deploy:** `.\scripts\deploy-ko.ps1` (from `solutions\tripletex\`)
2. **Submit:** click on app.ainm.no (max 3 concurrent), check score
3. **Post-score:** `.\scripts\post-score.ps1` (captures Cloud Run logs + git pull)
4. **Handoff:** paste score + log file path to Claude
5. **Claude fixes:** review logs, edit code
6. **Claude commits + pushes** → back to step 1

## Score History

| Time | Scores | Notes |
|------|--------|-------|
| 16:35 | 0/8 | Old container, retry_correction.md missing |
| 16:51 | 7/7 | .gcloudignore fix deployed |
| 17:04 | 7.5/10 | Self-correction working, variable extraction fixed |
| 17:36 | 0/10 | Bank reconciliation (Tier 3, expected fail) |
| 17:41 | 0/10, 0/13, 0/14 | Complex tasks + 500 crash on string correction steps |
| 17:46 | 8/8 | Employee creation, clean |
| 17:54 | 8/8 + 0/10 | Customer creation OK, cost analysis used placeholder names |

## What Works

- Departments, employees, customers, products — simple creation tasks
- Invoice creation and send
- Multi-step tasks with variable extraction (GET → save ID → POST)
- Self-correction: when a step fails with 422, the LLM re-plans and retries
- Overdue invoice + surcharge + partial payment (complex 7-step flow)

## What's Failing

- **Travel expenses** — LLM can't find/create suppliers
- **Bank reconciliation** — LLM hardcodes invoice numbers from CSV instead of searching
- **Ledger corrections** — partial success, cascade failures when early steps fail
- **Cost analysis** — LLM uses `{{placeholder}}` names instead of extracting from data
- **Payment reversals** — LLM doesn't know how to reverse vouchers correctly

## Fixes Applied This Session

1. **`.gcloudignore` excluding prompt templates** — `*.md` glob removed `retry_correction.md`. Fixed by listing specific files.
2. **`NameError` on unresolved variables** — `step_fixes`/`step_removed` used before definition. Fixed.
3. **Variable extraction hardened** — bracket notation (`values[0].id`), `value.X` fallback.
4. **JSON parsing robustness** — bracket-depth matching for LLM responses with trailing text.
5. **Better error logging** — `repr(exc)` fallback for empty exception messages.
6. **Non-dict correction steps** — skip gracefully instead of 500 crash.
7. **Field name renames** — `voucherDate→date`, `address→postalAddress` in schema validator.
8. **Strip `fields` param from GETs** — prevents hallucinated field names (NOT YET SCORED).
9. **Retry on proxy timeouts** — 3 attempts with backoff on ConnectTimeout (NOT YET SCORED).

## Latest Unscored Fixes (deployed but not yet submitted against)

- Strip `fields` query param from all GET requests (prevents hallucinated field names)
- Retry with exponential backoff on Tripletex proxy ConnectTimeout/ReadTimeout

## Cloud Run Logs

Scoring run logs are committed in `solutions/tripletex/logs/run_*.log`. These are captured from `gcloud logging read` after each scoring submission. Recent logs:

- `run_20260321_185704.log` — latest (8/8 + 0/10)
- `run_20260321_184238.log` — 3 concurrent runs (2/10, 0/13, 0/14)
- `run_20260321_183848.log` — bank reconciliation (0/10)

## Key Files

- `src/tripletex_agent/app.py` — FastAPI entrypoint (`/health`, `/solve`, `/logs`)
- `src/tripletex_agent/llm_executor.py` — main executor (two-phase LLM: Haiku for tools, Sonnet for planning)
- `src/tripletex_agent/client.py` — Tripletex API client (now with retry logic)
- `src/tripletex_agent/schema_validator.py` — validates/fixes LLM-generated request bodies
- `src/tripletex_agent/service.py` — `build_default_service()` requires `ANTHROPIC_API_KEY`
- `src/tripletex_agent/prompts/retry_correction.md` — self-correction prompt template
- `src/tripletex_agent/prompts/planner_system.md` — system prompt for planning
- `scripts/deploy-ko.ps1` — build + deploy to Cloud Run
- `scripts/post-score.ps1` — capture logs + git pull
- `.gcloudignore` — excludes test/docs from Cloud Build (KEEP prompt .md files!)

## Architecture

```
POST /solve
  → LLM Phase 1 (Haiku): tool calls to look up Tripletex API schemas
  → LLM Phase 2 (Sonnet): generate ordered API call steps as JSON array
  → Execute steps sequentially, saving response IDs as variables
  → On failure: self-correction via retry_correction.md prompt (1 retry)
  → Return {"status": "completed"}
```

## Next Priority

1. Score the latest fixes (fields stripping + retry)
2. Fix cost analysis — LLM must extract actual account names from voucher data, not use placeholders
3. Fix travel expense — needs supplier creation or different approach
4. Consider increasing self-correction retries from 1 to 2
5. The `address→postalAddress` rename helps, but address objects need proper structure (nested `addressLine1`, `postalCode`, `city`)

## Restart Prompt

```text
Read solutions/tripletex/SESSION_HANDOFF.md then solutions/tripletex/README.md.

Current state: captains-tripletex deployed on Cloud Run, scoring 8/8 on simple tasks.
Branch: tripletex/complex-multi-step-project

Iteration cycle:
1. .\scripts\deploy-ko.ps1
2. Submit on app.ainm.no
3. .\scripts\post-score.ps1
4. Paste score + log path to Claude
5. Claude fixes + commits + pushes → back to 1

Key: simple tasks pass, complex tasks fail. Focus on highest-ROI fixes.
Latest unscored: fields stripping + proxy retry. Deploy and score first.
```
