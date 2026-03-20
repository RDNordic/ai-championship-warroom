# Privacy and Security Checklist — Tripletex: AI Accounting Agent

Challenge: Tripletex
Owner: KO (primary), Andrew (governance escalation)
Date: 2026-03-19

---

## Data Inventory

- [x] **Data sources listed:** Competition-issued prompts (NM i AI judging system); Tripletex sandbox API (`tx-proxy.ainm.no`); optional base64 PDF/image attachments in prompt payload.
- [x] **Lawful basis:** NM i AI competition rules. Sandbox data is synthetic and ephemeral — competition-issued, not subject to production Tripletex data terms.
- [x] **Personal data identified:** Prompts contain fictional employee names and email addresses (competition-generated). Not real data subjects. Processed transiently — not stored, not logged.
- [x] **Sensitive attributes:** None. No health, biometric, ethnic, political, or financial data about real persons. Financial ledger entries are synthetic sandbox data only.
- [x] **Third-party data compliance:** All data sourced via competition platform. No external datasets used.

---

## GDPR Principles (Apply By Default)

- [x] **Purpose limitation:** Data used solely for interpreting and executing competition accounting tasks. Not used for training, profiling, or any secondary purpose.
- [x] **Data minimisation:** Agent extracts only the fields required to complete each task. No bulk GET calls to harvest data beyond task scope.
- [x] **Storage limitation:** Agent is stateless per request. No persistence layer. No database. Prompt content and session tokens are not written to disk. Retention: zero.
- [x] **Accuracy:** Synthetic data — accuracy checks not applicable. Agent validates field values before submission to avoid 422 errors.
- [x] **Integrity and confidentiality:** Session token handled in-memory only. Not logged. Not included in any error output. HTTPS enforced (cloudflared tunnel / GCP endpoint).

---

## Security

- [x] **Secrets management:** Session token arrives per-request in POST body — ephemeral, never stored. No API keys or credentials in source code. `.gitignore` verified for any local credential files.
- [x] **Dependency review:** `fastapi`, `uvicorn`, `requests`, `anthropic` — standard, actively maintained packages. Pin versions in requirements.txt. No known CVEs at time of writing.
- [x] **Prompt injection checks:** Agent receives arbitrary natural-language prompts from the judging system. Risk: adversarially crafted prompt attempts to override system instructions or exfiltrate data. Mitigation: system prompt instructs agent to treat all user content as accounting task input only; no tool that could exfiltrate data is exposed.
- [x] **Output filtering:** Agent returns only `{"status": "completed"}`. No prompt content, no API response data, no session token echoed in response. Confirmed in endpoint implementation.
- [x] **API endpoint hardening:**
  - HTTPS enforced via tunnel/GCP (no plaintext HTTP).
  - No authentication on `/solve` endpoint — competition design; judging system calls it directly. Acceptable given sandbox-scoped session tokens are single-use.
  - Input validation: request body validated against expected schema before processing.
  - Rate limiting: competition allows 10 concurrent submissions — endpoint must handle concurrent requests without state leakage between them (stateless design ensures this).

---

## Operational

- [x] **Incident owner:** KO — primary. Andrew for governance escalation.
- [x] **Escalation contacts:** KO (endpoint ops) → Andrew (governance) → Christopher (technical backup). Patrick on Signal for awareness.
- [x] **Backup / rollback:** If endpoint fails, restart uvicorn. GCP deployment available as cold fallback. Judging system retries — recovery within 5 minutes is acceptable. Previous submission scores are retained (bad runs never lower score).
- [x] **Competition data handling rules checked:** Sandbox credentials are ephemeral per-request tokens. One sandbox per team. Token expires March 31, 2026. No obligation to delete sandbox data post-competition (synthetic only) — but endpoint will be decommissioned March 22, 2026.

---

## Decision Rule

When in doubt about data rights or privacy: **pause, log in risk-register.md, and ask** — don't silently proceed and don't silently refuse.
