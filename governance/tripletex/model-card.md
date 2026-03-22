# Model Card — Tripletex: AI Accounting Agent

Challenge: Tripletex
Owner: KO
Version: v1 (competition)
Date: 2026-03-19

---

## Model Overview

- **Name:** Tripletex Accounting Agent
- **Architecture:** LLM agent — Claude API (claude-sonnet-4-6 or equivalent) with structured API call planning
- **Owner:** KO
- **Challenge:** NM i AI — Tripletex
- **Date:** 2026-03-22 (final submission)

---

## Intended Use

- **Primary use:** Receive a natural-language accounting task prompt, classify it, extract entities, plan and execute Tripletex REST API calls, return `{"status": "completed"}`.
- **Users:** NM i AI automated judging system (evaluation); KO (operator).
- **Environment:** FastAPI endpoint exposed via HTTPS (cloudflared tunnel or GCP). Timeout: 300 seconds per request.
- **Out of scope:** Not intended for production accounting use. No real financial data. No real employees.

---

## Data

- **Training / fine-tune sources:** None — uses pre-trained Claude API model as-is. No fine-tuning.
- **Validation sources:** Tripletex sandbox (`tx-proxy.ainm.no`); manual testing against all 30 task types before competition.
- **Data limitations:** Agent relies entirely on in-context learning and system prompt. Performance degrades on task types not explicitly covered in system prompt.

---

## Performance

- **Primary metric:** Total competition score (sum of best scores across 30 task types; tier × correctness × efficiency bonus).
- **Secondary metrics:** 4xx error rate (must be 0 for efficiency bonus); task coverage (target: 20+ of 30 task types).
- **Known weak spots:**
  - Tier 3 multi-step tasks (e.g., create employee → create project → link → create invoice) — more failure points.
  - Nynorsk (nn) prompts — closest to Bokmål but distinct; misclassification risk.
  - Tasks requiring DELETE or reversal — agent must correctly identify the target entity to delete.

---

## Safety and Risk

- **Abuse / misuse considerations:** Agent executes accounting actions autonomously. A maliciously crafted prompt could attempt to exfiltrate session data or cause unintended API calls. Mitigated by: sandboxed environment, ephemeral tokens, one company scope per session.
- **Failure modes:**
  1. LLM hallucination → wrong API endpoint or fields → 4xx error → efficiency penalty
  2. Timeout (>300s) → task scored 0
  3. Missing required fields → 422 validation error → partial credit at best
  4. Endpoint downtime → missed evaluations
- **Mitigations:** See risk-register R-001 through R-005. Pre-validate before calling. Plan API sequence before first call. Test all task types in sandbox first.

---

## Operational Notes

- **Repro command:**
  ```bash
  pip install fastapi uvicorn requests anthropic
  uvicorn main:app --host 0.0.0.0 --port 8000
  npx cloudflared tunnel --url http://localhost:8000
  ```
- **Dependencies:** `fastapi`, `uvicorn`, `requests`, `anthropic` (pinned versions in requirements.txt)
- **Rollback / fallback:** If endpoint fails, restart uvicorn. GCP deployment available as fallback. Judging system retries — endpoint recovery within 5 minutes is acceptable.
- **Register endpoint at:** `https://app.ainm.no/submit/tripletex`
