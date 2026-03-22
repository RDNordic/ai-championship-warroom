# Privacy and Security Checklist — Astar Island: Viking World Prediction

Challenge: Astar Island
Owner: AD (Andrew/John), Andrew (governance escalation)
Date: 2026-03-22

---

## Data Inventory

- [x] **Data sources listed:** Astar Island API (`api.ainm.no/astar-island`) — synthetic simulation observations. Initial grid states from `/rounds/{round_id}`. Ground truth analysis from `/analysis/{round_id}/{seed_index}`.
- [x] **Lawful basis:** NM i AI competition rules. All data is competition-issued synthetic simulation output. No external datasets used.
- [x] **Personal data identified:** None. All data represents fictional terrain types (Empty, Settlement, Port, Ruin, Forest, Mountain) and abstract simulation statistics (population, food, wealth, defense). No real persons involved at any stage.
- [x] **Sensitive attributes:** None present. Settlement statistics are simulation abstractions — not derived from or representative of real people, health, biometric, ethnic, or political data.
- [x] **Third-party data compliance:** All data sourced exclusively via competition API. No external datasets, scraping, or third-party enrichment.

---

## GDPR Principles (Apply By Default)

- [x] **Purpose limitation:** Data used solely for predicting terrain probability distributions in the competition. Not used for training, profiling, or any secondary purpose.
- [x] **Data minimisation:** Only grid observations and settlement statistics necessary for parameter inference are collected. Budget-constrained by design (50 queries max per round).
- [x] **Storage limitation:** Observation artifacts stored locally in `solutions/astar-island/artifacts/` (gitignored). Ground truth exports retained for post-competition analysis. No PII in any stored data. Post-competition cleanup: delete JWT tokens; observation data may be retained indefinitely (fully synthetic).
- [x] **Accuracy:** Not applicable — synthetic simulation data with no accuracy obligation toward real-world subjects.
- [x] **Integrity and confidentiality:** API access secured via JWT Bearer token. Token stored in `solutions/astar-island/.token` — excluded from version control via `.gitignore`. All API communication over HTTPS.

---

## Security

- [x] **Secrets management:** JWT access_token stored in `.token` file — gitignored, never committed. `.token.example` provided as safe placeholder. No API keys or credentials in source code. Verified: `.token` is in `.gitignore` (`**/.token` pattern).
- [x] **Dependency review:** `numpy`, `requests` — standard, actively maintained packages. No known CVEs at time of writing. Minimal dependency surface.
- [x] **Prompt injection checks:** Not applicable — system is a pure read/compute/submit pipeline. No LLM component. No user-provided natural language input. All API inputs are structured JSON (viewport coordinates, prediction tensors).
- [x] **Output filtering:** Submissions contain only probability tensors (H×W×6 numeric arrays). No capability to leak training data, PII, or credentials through submission output.
- [x] **API endpoint hardening:** Not applicable — no hosted endpoint. All computation is local. Interaction with competition API is outbound-only (authenticated GET/POST requests).

---

## Operational

- [x] **Incident owner:** AD — primary. Andrew for governance escalation.
- [x] **Escalation contacts:** AD → Christopher (technical backup) → KO. Patrick on Signal for awareness.
- [x] **Backup / rollback:** If observation run fails mid-budget, submit baseline predictions (terrain priors only) for remaining seeds — baseline scores 20–40 vs. 0 for missing seeds. Prior round observations retained in artifacts for reference.
- [x] **Competition data handling rules checked:** JWT token is competition-issued, scoped to team account, valid through competition end (March 22, 2026). Observation data is synthetic simulation output — no restrictions on retention. Query budget (50/round) enforced server-side.

---

## Decision Rule

When in doubt about data rights or privacy: **pause, log in risk-register.md, and ask** — don't silently proceed and don't silently refuse.
