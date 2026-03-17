# Intelligence Sources — NM i AI 2026

## Official Competition
- [NM i AI 2026 — Main Site](https://ainm.no/en)
- [NM i AI 2026 — App / Registration](https://app.ainm.no/)
- [NM i AI 2026 — Game Docs](https://app.ainm.no/docs/game)
- [NM i AI 2026 — Leaderboard](https://app.ainm.no/leaderboard)
- [NM i AI 2026 — FAQ (nmiai2026.no)](https://nmiai2026.no/en/faq)
- [NM i AI 2026 — FAQ (ainm.no)](https://ainm.no/en/faq)
- [NM i AI 2026 — Articles / Media](https://ainm.no/en/articles)
- [NM i AI 2026 — Manifest](https://ainm.no/en/manifest)

## Partner Announcements
- [Tripletex — Platinum Partner Press Release](https://www.tripletex.no/presse/tripletex-er-platinumpartner-nar-astar-arrangerer-norgesmesterskapet-i-ai/)
- [NorgesGruppen Data — Sponsor LinkedIn Post](https://no.linkedin.com/posts/norgesgruppen-asa_norgesgruppen-data-sponser-nm-i-ai-2026-activity-7429042881983774720-jEij)
- [EdTech Innovation Hub — Coverage](https://www.edtechinnovationhub.com/news/norway-puts-ai-skills-to-the-test-with-first-national-ai-championship)

## Key Facts (as of 2026-03-13)
- Dates: March 19-22, 2026 (kickoff 17:00, challenges released 18:00)
- Prize pool: 1,000,000 NOK (1st place: 400,000 NOK)
- Format: 3 simultaneous challenges, API scoring, real-time leaderboard
- Challenges NOT revealed until March 19 at 18:00

## Known Challenge Sponsors → Expected Domains
| Sponsor | Role | Likely Challenge Domain |
|---------|------|------------------------|
| NorgesGruppen Data | Major sponsor | Grocery Bot (pre-comp already live) |
| Tripletex | Platinum partner + case provider | Accounting/finance NLP or ML |
| DNV | Gold partner | TBC — see research below |

## Tripletex Challenge — Research Notes (2026-03-13)
- Details fully embargoed until March 19 at 18:00
- Press release only states: *"reflects real problems Tripletex works with daily; will challenge participants hard"*
- Tripletex core product: invoicing, bookkeeping, transaction categorisation, payroll, VAT/tax, financial reporting

**Most likely challenge types (ranked):**
1. Invoice/document classification — extract fields, categorise expenses (NLP)
2. Transaction categorisation — match bank transactions to accounting codes (tabular ML)
3. Anomaly detection in financial data — fraud/error detection in ledgers
4. Named entity extraction from Norwegian text — amounts, dates, vendors from invoices
5. Forecasting/time series — revenue or cash flow prediction (less likely)

**Prep strategy:** BM25 + simple retrieval beat complex LLMs in 2025. Have scikit-learn, HuggingFace pipelines, and a BM25 library (rank_bm25) ready. Norwegian text likely — consider NorBERT or multilingual models.

---

## DNV Challenge — Research Notes (2026-03-13)
- DNV challenge details NOT publicly announced yet (revealed March 19 at 18:00)
- DNV's core AI domains: maritime safety, predictive maintenance, anomaly detection, oil & gas, digital twins, safety-critical industries
- Most likely challenge types: predictive maintenance (ML/tabular), anomaly detection (CV or time-series), or safety document classification (NLP)
- DNV published recommended practices for "safe application of industrial AI" — challenge may test responsible/safe AI
- Sources: [DNV AI page](https://www.dnv.com/digital-trust/expertise/artificial-intelligence/) | [DNV maritime AI](https://www.dnv.com/training/artificial-intelligence-AI-for-maritime-professionals/)

## 1,198 registered participants as of search date (youngest 16, oldest 64)

---

## Official NM i AI Slack Intelligence (2026-03-13)
Workspace: norwegianaich-rgz4407.slack.com

### Critical Strategic Intel from Slack
1. **Competition format will resemble Grocery Bot** — Erik (organiser): *"kommer nok potensielt til å ligne mer på Grocery Bot som er ute nå"* (will likely resemble Grocery Bot). Getting familiar with the platform is explicitly recommended.
2. **Same WebSocket platform likely used for all challenges** — strong signal that competition mechanics = Grocery Bot mechanics.
3. **LLMs fully allowed** — Erik joked they were forbidden, then confirmed it was a joke. Opus 4.6, Sonnet 4.5, Qwen3.5:27B all being used by competitors.
4. **Leaderboard bar is high** — Opus 4.6 needed to break 600+ total score. Local models (Qwen3.5:27B) at ~Sonnet 4.5 level.
5. **Server update (March 11)** — `action_status` field + `round` field added to prevent stale/timeout desyncs. Ping/pong keepalive added. Backward compatible.
6. **Bot swap is blocked** — 97.4% of swap attempts fail. Only spawn zone allows it.
7. **Drop-offs and walls deterministic** — grid structure never changes mid-game. Item types rotate daily (midnight UTC).
8. **Winner announced March 22** — prize ceremony April/May at larger national event.
9. **Nicolai Tangen** (Norges Bank Investment Management CEO) keynote at kickoff.
10. **Jonas Gahr Støre** (Norwegian PM) sent message of support.

### Slack Channels Found
- #announcements (C0AHWFD8UKF) — official updates from Astar
- #random (C0AHDGZ8CEL) — competitor discussion, strategy hints
- #bug-report (C0AJ6UFT6S2) — server fixes, protocol clarifications
- #welcome (C0AGH6PCEJ2) — onboarding
- #looking-for-team (C0AJ2H0DX35) — team formation
