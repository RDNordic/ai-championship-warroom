# Data Card — Tripletex: AI Accounting Agent

Challenge: Tripletex
Owner: KO
Date: 2026-03-19

---

## Dataset Overview

- **Name:** NM i AI Tripletex Competition Prompts + Sandbox API
- **Version:** Competition round (March 2026)
- **Source:** NM i AI judging system (prompts); Tripletex sandbox (`tx-proxy.ainm.no`)
- **License / usage basis:** NM i AI competition rules. Sandbox data is synthetic/ephemeral — issued per submission, destroyed after. Not subject to Tripletex production data terms.
- **Owner:** Competition infrastructure (read-only for our team)

---

## Composition

- **Prompt types:** 30 task types × 7 languages × 8 datasets = up to 1,680 prompt variants
- **Languages:** Norwegian Bokmål (nb), English (en), Spanish (es), Portuguese (pt), Norwegian Nynorsk (nn), German (de), French (fr)
- **Task categories:** Employees, Customers & Products, Invoicing, Travel Expenses, Projects, Corrections, Departments
- **Optional attachments:** Base64-encoded PDF or image files embedded in prompt payload
- **Missingness:** Some prompts have no file attachment (most tasks); file presence is task-dependent

---

## Collection and Processing

- **Collection method:** Prompts are issued at runtime by the automated judging system via POST to our `/solve` endpoint. We do not batch-collect or store them.
- **Preprocessing:** Agent pre-processes: language detection, task classification, entity extraction — all done in-flight by LLM. No offline preprocessing.
- **Filtering:** None — agent must handle all 30 task types as-is.

---

## Quality and Bias Notes

- **Known quality issues:** Prompts are synthetic; edge cases in multilingual phrasing (nn vs nb) may cause misclassification.
- **Bias risks:** Agent uses Claude API which may exhibit language-quality variance across the 7 supported languages. Norwegian (nb/nn) prompts are natively strong; other languages depend on LLM multilingual capability.
- **Mitigation:** System prompt includes explicit language handling instruction; agent is tested against sample prompts in each language before competition.

---

## Security and Privacy

- **Sensitive fields present:** Fictional employee names and email addresses in prompts (competition-generated fictions, not real data subjects). Session tokens in request body.
- **Protection controls:**
  - Session tokens never logged or persisted beyond the request lifecycle.
  - Prompt content not stored after agent returns `{"status": "completed"}`.
  - No database or file persistence in agent.
- **Retention policy:** Zero retention. Agent is stateless per request. Competition ends March 22, 2026 — endpoint decommissioned after.
