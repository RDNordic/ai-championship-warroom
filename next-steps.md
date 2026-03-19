# Next Steps — NM i AI Championship

**Competition kickoff:** March 19, 2026 at 18:00 CET
**Challenges released:** March 19 at 18:00 (3 simultaneous, unknown until kickoff)
**Winner announced:** March 22, 2026

---

## Session Log
- **2026-03-19:** COMPETITION HAS BEGUN. Added `nmiai` MCP server (`https://mcp-docs.ainm.no/mcp`) — restart Claude Code to activate. Challenges not yet read.
- **2026-03-17:** Rules published. Task 2 sponsor confirmed as Astar (not DNV). GCP account applied. Repo cleaned of legacy trial references. Vipps verification and public repo flagged as urgent.
- **2026-03-13:** Meeting with Patrick. Intel gathered, Slack connected, `/session-handoff` + `/btw` commands created, next-steps cleaned. See `comms/meeting-notes.md` and `comms/intel-sources.md` for full details.

---

## Team

| Member | Role | Hardware |
|--------|------|----------|
| AD (Andrew) | PM / Governance | — |
| Chris (Christopher) | Solver / Eval Lead | — |
| Patrick | Governance + Coordination | Intel Core Ultra 5 135H, 96GB RAM, 54GB NPU, no dedicated GPU |
| KO (Oddar) | Infra / Red Team | ASUS ROG Zephyrus G16 — RTX 5090 Mobile 24GB VRAM, Intel Core Ultra 9, 64GB RAM |

**Comms:** Signal for team updates. John keeps GitHub hub in sync.

**Hardware strategy:**
- GPU workloads (LLM inference, CV, fine-tuning) → KO's machine (RTX 5090 Mobile, 24GB VRAM)
- CPU/tabular ML, large-context NPU inference → John's machine (96GB RAM)
- Cloud burst → Google infra (confirm access at app.ainm.no before March 19)

---

## Known Challenge Sponsors

| Task | Sponsor | Likely Domain |
|------|---------|--------------|
| Task 1 | Tripletex | Accounting / finance NLP or ML |
| Task 2 | Astar | **Unknown** — Astar is the organizer's consulting firm; no prior intel |
| Task 3 | NorgesGruppen Data | Simulation / game (WebSocket platform — pre-comp trial experience applies) |

Task types confirmed at kickoff March 19, 18:00 CET. See `comms/intel-sources.md` for full intelligence.

## Scoring Rules (from official rules)

- Each task normalized 0–100 (÷ highest score in that task across all teams)
- Overall score = average of 3 normalized scores (33.33% each)
- **Zero on any task = catastrophic.** Get a baseline submission on all 3 before optimizing.
- Ties broken by timestamp of the submission that first achieved the tying score.
- Verified teams (Vipps) get higher submission rate limits.

---

## Before March 19 — Prep Tasks

### Infrastructure (Priority — do this week)
- [ ] **Vipps verification — ALL 4 members, do NOW** (unlocks higher submission rate limits + prize eligibility)
- [ ] **Set repo to public before March 22 15:00 CET — do this last minute** (prize eligibility; keep private during competition to protect strategy)
- [x] MIT license added (`LICENSE` file, March 17)
- [ ] **Do NOT submit to any task until all 4 members are on the team** (roster locks on first submission)
- [ ] GCP account applied — confirm access at app.ainm.no before March 19
- [ ] Install and configure must-have MCP stack (MarkItDown, GitHub MCP)
- [ ] Test each enabled MCP in a dry-run against a mock challenge
- [ ] Create `.claude/settings.json` with MCP server configs
- [ ] Add `requirements.txt` / `package.json` with pinned versions for core dependencies
- [ ] Pre-build FastAPI scaffold template ready to clone per challenge
- [ ] Test deployment pipeline: local → public endpoint in < 30 minutes (ngrok recommended)
- [ ] KO: install Ollama + Qwen2.5:27B, verify inference speed
- [ ] Activate branch protection ruleset back to "Active" once team is onboarded
- [ ] Consider: RunPod/Vast.ai as GPU burst backup if Google infra is limited

### Challenge Prep
- [ ] **Task 3 — Simulation / Game (NorgesGruppen):** WebSocket bot scaffold ready. Reuse pre-comp trial client as starting point. Key: `action_status` field, `round` field, 1.8s hard cutoff. Pre-comp trial experience directly transferable.
- [ ] **Task 1 — NLP / Accounting (Tripletex):** Most likely invoice classification, transaction categorisation, or NER on Norwegian text. Prep: `rank_bm25`, scikit-learn pipelines, HuggingFace NorBERT/multilingual model. BM25 beat LLMs in 2025 — try simple first.
- [ ] **Task 2 — Astar (UNKNOWN):** No prior intel. Astar is the organizer's own consulting firm. Broad prep: have classification, regression, and generation scaffolds ready. Reveal at kickoff.
- [ ] Consider: Firecrawl MCP for scraping Norwegian registers / accounting docs if Tripletex task is data-heavy
- [ ] Pre-write submission command template in each challenge folder (`solutions/challenge-1/`, `challenge-2/`, `challenge-3/`)
- [ ] Create single-command local eval entrypoint template
- [ ] Add reproducibility checklist to `playbooks/submission-runbook.md`

### External Data Playbook
- [ ] Build quick-reference list of external data sources:
  - NLP: HuggingFace datasets, Wikipedia dumps
  - CV: ImageNet, COCO, Open Images
  - Tabular/ML: Kaggle public datasets, UCI ML repo
  - Finance/accounting: open invoice datasets, Norwegian public registers

### Team Onboarding
- [ ] All 4 members in Signal group
- [ ] All 4 members with GitHub repo access and confirmed push/PR ability
- [ ] Each member does a test PR → review → merge cycle
- [ ] Share `comms/intel-sources.md` with team for review
- [ ] Run full dry-run of `playbooks/submission-runbook.md`

### Governance (Andrew)
- [ ] Prepare lightweight model card template (fillable in < 10 minutes per challenge)
- [ ] Simplify AI Act checklist for competition speed
- [ ] Consider referencing `D:\Projects\eu-ai-compliance-toolkit` during competition

---

## Competition Week Plan (March 19–22)

### Thursday March 19 — Kickoff
- 17:00: Kickoff event (Oslo / remote, Nicolai Tangen keynote)
- 18:00: Challenges released
- 18:00–18:30: Read all 3 challenges. Identify quick wins vs hard problems.
- 18:30–19:00: Assign challenge ownership. Chris picks primary challenge.
- 19:00–21:00: Get baseline submissions running for all 3 challenges.
- 21:00: First sync — what's working, what's blocked.

### Friday March 20 — Build Day
- Parallel work: Chris + KO on modelling; Andrew + Patrick on governance + external data
- 2-hour sync checkpoints
- Goal: all 3 challenges scoring on leaderboard by end of day

### Saturday March 21 — Optimise
- Focus on improving scores. External data integration.
- Red team testing on leading solutions.
- Goal: competitive scores on all 3 challenges.

### Sunday March 22 — Final
- Morning: final optimisation push
- Midday: freeze code. Run submission runbook.
- Final submission gate: Andrew (compliance) + Chris (technical) sign-off

---

## MCP Tooling

### Must-Have (install before March 19)
1. **MarkItDown** — convert challenge PDFs and dataset docs to Markdown
2. **GitHub MCP Server** — GitHub integration in AI workflow

### Optional (only if challenge requires)
3. **Context7** — live library docs for unfamiliar frameworks
4. **Playwright MCP** — browser automation for web submissions
5. **MCP Run Python** — sandboxed Python for rapid prototyping
6. **Cognee** — graph/vector RAG if RAG-heavy challenge appears

### Kill Criteria
- Remove any MCP if setup takes > 30 minutes with no working dry-run
- Remove any MCP that fails in 2+ dry-runs
- Fallback: local-script-only workflow (no MCP dependency)

---

## Still Unclear
- Exact submission format for each challenge (revealed March 19)
- Submission cap/frequency
- Exact timezone binding for deadline
- What Google-provided infrastructure access looks like in practice
- Inference constraints (cloud API ban? VRAM limits?)
- Code disclosure obligations for top teams

---

## Completed
- [x] Pre-competition trial (NorgesGruppen simulation, rank ~70/317) → `solutions/grocerybot-trial-vs-code/TRIAL_SUMMARY.md`
- [x] GCP account applied (March 17)
- [x] Competition rules reviewed → `ops/NMiAI-main-competition-rules-regulations.txt`
- [x] Team roles assigned in `AGENTS.md`
- [x] Branch protection rules set on GitHub
- [x] PR template and `CONTRIBUTING.md` created
- [x] Competition intelligence gathered → `past-championships-data/competition-reference.md`
- [x] Verification ladder and data handling defaults in `CLAUDE.md`
- [x] Eval harness, red team tests, privacy checklist expanded
- [x] `/session-handoff` and `/btw` slash commands created → `.claude/commands/`
- [x] Slack connected to official NM i AI workspace (intel in `comms/intel-sources.md`)
- [x] Hardware assessed: KO = RTX 5080 GPU box; John = 96GB RAM / NPU CPU box
- [x] Tripletex + DNV challenge hypotheses documented in `comms/intel-sources.md`
- [x] External resource map built (compute, MCPs, data sources, inference APIs)
- [x] `next-steps.md` cleaned — Grocery Bot trial data archived to `TRIAL_SUMMARY.md`
