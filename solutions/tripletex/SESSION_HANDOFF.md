# SESSION_HANDOFF.md

## Checkpoint (2026-03-21 ~18:10 CET)

Tripletex agent is deployed to Google Cloud Run and actively scoring. KO is running the deploy-score-fix cycle from Windows/PowerShell. Chris has a parallel instance (`tripletex-agent`).

**Current score: 7.5/10 best run (trending up from 0)**

## Deployment

- **Service:** `captains-tripletex` on Cloud Run (KO's instance)
- **Project:** `nmiai-490717`, region `europe-north1`
- **URL:** `https://captains-tripletex-339414168231.europe-north1.run.app`
- **Submission:** `https://app.ainm.no/submit/tripletex`
- **Branch:** `tripletex/complex-multi-step-project`
- **ANTHROPIC_API_KEY:** set as env var on Cloud Run (not in code, not via Secret Manager)
- **CLOUDSDK_CONFIG:** local `.gcloud-config/` dir to avoid Windows NTUSER.DAT permission issue

## Iteration Cycle (KO's workflow)

1. **Deploy:** `.\scripts\deploy-ko.ps1` (from `solutions\tripletex\`)
2. **Submit:** click on app.ainm.no, check score
3. **Post-score:** `.\scripts\post-score.ps1` (captures Cloud Run logs + git pull)
4. **Handoff:** paste score + log file path to Claude
5. **Claude fixes:** review logs, edit code
6. **Claude commits + pushes** → back to step 1

## What Works

- Departments, employees, customers, products, projects — simple creation tasks
- Invoice creation and send
- Multi-step tasks with variable extraction (GET → save ID → use in POST)
- Self-correction: when a step fails with 422, the LLM re-plans and retries
- Overdue invoice + surcharge + partial payment (complex 7-step flow)

## What's Failing

- **Payment reversals** — LLM requests nonexistent `payments` field on InvoiceDTO
- **Some generic exceptions** have empty error messages (fix deployed but not yet scored)
- **Travel expenses** — not yet implemented in live executor
- **Complex ledger correction tasks** — partial success, some steps fail
- **PDF/CSV extraction** — deferred

## Recent Fixes (this session)

1. **`.gcloudignore` was excluding prompt templates** (`*.md` glob) — caused all self-correction to crash with `FileNotFoundError: retry_correction.md`. This was the main blocker. Fixed by listing specific top-level .md files instead.

2. **`NameError` on unresolved variables** — `step_fixes`/`step_removed` used before definition. Fixed by moving init earlier.

3. **Variable extraction hardened** — `_resolve_value` now handles bracket notation (`values[0].id`) and falls back to `value.X` for single-object responses. `_normalize_save_fields` handles bracket notation in path detection.

4. **JSON parsing robustness** — LLM sometimes returns JSON array followed by commentary text. Parser now uses bracket-depth matching to extract the first complete JSON array.

5. **Better error logging** — generic exceptions now log `type(exc).__name__` and `repr(exc)` instead of empty string.

## Key Files

- `src/tripletex_agent/app.py` — FastAPI entrypoint (`/health`, `/solve`, `/logs`)
- `src/tripletex_agent/llm_executor.py` — main executor (two-phase LLM: Haiku for tools, Sonnet for planning)
- `src/tripletex_agent/service.py` — `build_default_service()` requires `ANTHROPIC_API_KEY`
- `src/tripletex_agent/prompts/retry_correction.md` — self-correction prompt template
- `src/tripletex_agent/prompts/planner_system.md` — system prompt for planning
- `scripts/deploy-ko.ps1` — build + deploy to Cloud Run
- `scripts/post-score.ps1` — capture logs + git pull
- `scripts/capture_logs-ko.ps1` — just capture logs
- `.gcloudignore` — excludes test/docs from Cloud Build (KEEP prompt .md files!)

## Architecture

```
POST /solve
  → LLM Phase 1 (Haiku): tool calls to look up Tripletex API schemas
  → LLM Phase 2 (Sonnet): generate ordered API call steps as JSON array
  → Execute steps sequentially, saving response IDs as variables
  → On failure: self-correction via retry_correction.md prompt
  → Return {"status": "completed"}
```

## Known Issues / Risks

- Chris's `deploy.sh` has his Anthropic API key hardcoded (line 15)
- Cloud Run logs are ephemeral (container restarts lose `/logs` endpoint data)
- `post-score.ps1` uses `gcloud logging read --freshness=30m` — increase if runs take longer
- Concurrent submissions (up to 10) can run against the same sandbox, causing data conflicts

## Next Priority

1. Deploy latest code (error logging fix) and re-score
2. Analyze the actual exception types from the improved error logs
3. Fix payment reversal (LLM needs guidance that InvoiceDTO has no `payments` field — use voucher reversal instead)
4. Improve complex ledger correction tasks
5. Consider travel expense implementation if time permits

## Restart Prompt

```text
Read solutions/tripletex/SESSION_HANDOFF.md then solutions/tripletex/README.md.

Current state: captains-tripletex is deployed on Cloud Run and scoring 7.5/10 best.
Branch: tripletex/complex-multi-step-project

KO's iteration cycle:
1. .\scripts\deploy-ko.ps1
2. Submit on app.ainm.no
3. .\scripts\post-score.ps1
4. Paste score + log path to Claude
5. Claude fixes + commits + pushes
6. Back to 1

Latest code has improved error logging. Next step: deploy, score, read logs, fix failures.
```
