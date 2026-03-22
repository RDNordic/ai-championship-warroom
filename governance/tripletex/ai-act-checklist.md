# AI Act Checklist — Tripletex: AI Accounting Agent

Challenge: Tripletex
Owner: KO
Date: 2026-03-22 (final submission)
Created: 2026-03-19

---

## System Definition

- [x] **Purpose:** Autonomous LLM agent that interprets natural-language accounting tasks (7 languages) and executes them via the Tripletex REST API. Responds to competition-issued prompts; no human review per transaction.
- [x] **Intended users:** NM i AI competition judges (automated evaluation system). Operator: Team. No end-user population outside competition context.

---

## EU AI Act Risk Classification

**Classification: Limited Risk (competition context) — would be High Risk in production**

Rationale:
- In production, an autonomous financial agent modifying employee records and financial ledgers would likely qualify as **high risk** under Annex III (employment decisions, financial services).
- In competition context: sandboxed environment, synthetic/competition-issued data, no real subjects, no production deployment. Treated as limited risk for this submission.
- **Note for judges:** If deployed in production, full high-risk obligations would apply: conformity assessment, human oversight, logging, right to explanation.

---

## Risk and Control

- [x] Key risks identified and logged in `governance/risk-register.md` (R-001 through R-005).
- [x] Controls assigned: KO owns all Tripletex risks.
- [x] Residual risk accepted: Session token exposure (R-001) — mitigated by no-logging rule; not fully eliminable in API agent context.

---

## Data Governance

- [x] **Data sources:** Competition-issued prompts via judging system; Tripletex sandbox API (synthetic data only); base64-encoded PDF/image attachments from prompts.
- [x] **Usage basis:** NM i AI competition rules. Data is sandbox/synthetic — no real subjects. All credentials are ephemeral per-request tokens issued by competition infrastructure.
- [x] **PII handling:** Prompts may contain fictional employee names and email addresses (e.g., "Ola Nordmann, ola@example.org"). These are competition-generated fictions, not real data subjects. Nonetheless: (a) not logged beyond competition run; (b) not stored persistently; (c) passed to Claude API under standard Anthropic data terms.
- [x] Sensitive data controls: session_token never logged; no persistent storage of entity data.

---

## Transparency and Traceability

- [x] Model card created: `governance/tripletex/model-card.md`
- [x] Data card created: `governance/tripletex/data-card.md`
- [x] Decision log updated in `ops/decision-log.md`

---

## Security and Robustness

- [x] **Failure mode — LLM hallucination:** Agent may call wrong endpoints, supply wrong fields, or misinterpret multilingual prompts. Mitigation: sandbox testing before competition; local validation logic; see R-002.
- [x] **Failure mode — Efficiency penalty:** Every 4xx error reduces efficiency bonus. Mitigation: pre-validate inputs; plan API sequence before first call.
- [x] **Abuse consideration:** Agent executes arbitrary accounting actions on behalf of a prompt. Could be misused with adversarial prompts. In competition context: sandboxed, scoped to one company per session, token expires after use.
- [x] Edge-case tests run (multilingual task classification) — 7-language prompt set tested; 23+ fixes applied during competition

---

## Human Oversight

- [x] **Human owner:** KO — go/no-go authority for endpoint deployment and major model changes.
- [x] **Escalation path:** KO → Andrew (governance) → Christopher (technical backup). Signal for Patrick.
- [x] **Competition note:** Per-transaction human oversight is not feasible given automated judging. Human oversight operates at system level (deployment, configuration, abort).
