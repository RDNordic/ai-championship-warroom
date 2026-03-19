# Next Steps - NM i AI Championship

**Competition kickoff:** March 19, 2026 at 18:00 CET
**Winner announced:** March 22, 2026

---

## Session Log
- **2026-03-19:** Challenges read and reviewed in full. Ownership assigned. Patrick out for personal reasons (kept in loop). Active build phase begun.
- **2026-03-19:** COMPETITION HAS BEGUN. Added `nmiai` MCP server (`https://mcp-docs.ainm.no/mcp`). Challenges released at 18:00.
- **2026-03-17:** Rules published. Task 2 sponsor confirmed as Astar. GCP account applied.
- **2026-03-13:** Meeting with Patrick. Intel gathered, Slack connected. See `comms/meeting-notes.md` and `comms/intel-sources.md`.

---

## Team

| Member | Role | Challenge | Hardware |
|--------|------|-----------|----------|
| AD (Andrew) | PM / Governance | **Astar Island** (Challenge 2) | - |
| Chris (Christopher) | Solver / Eval Lead | **NorgesGruppen Object Detection** (Challenge 3) | - |
| KO (Oddar) | Infra / Red Team | **Tripletex Accounting Agent** (Challenge 1) | ASUS ROG Zephyrus G16 - RTX 5090 Mobile 24GB VRAM, Intel Core Ultra 9, 64GB RAM |
| Patrick | Governance + Coordination | **Out - personal reasons. Kept in loop.** | Intel Core Ultra 5 135H, 96GB RAM, 54GB NPU |

**Comms:** Signal for team updates. John keeps GitHub hub in sync.

**Hardware strategy:**
- GPU workloads (CV training, LLM inference, fine-tuning) -> KO's machine (RTX 5090 Mobile, 24GB VRAM)
- CPU/analysis/Astar modelling -> AD's machine
- Cloud burst -> Google infra (app.ainm.no)

---

## Challenges - Confirmed

| Challenge | Sponsor | Type | Owner | Docs |
|-----------|---------|------|-------|------|
| Tripletex | Tripletex | AI Accounting Agent - HTTPS endpoint, LLM + REST API | KO | `solutions/tripletex/README.md` |
| Astar Island | Astar | Viking World Prediction - probabilistic ML, 50 queries | AD | `solutions/astar-island/README.md` |
| NorgesGruppen Data | NorgesGruppen | Object Detection - train & upload zip, mAP@0.5 | Chris | `solutions/norgesgruppen-data/README.md` |

---

## Scoring Rules

- Each task normalized 0-100 (divided by highest score in that task across all teams)
- Overall score = average of 3 normalized scores (33.33% each)
- **Zero on any task = catastrophic.** Get a baseline on all 3 before optimizing.
- Ties broken by timestamp of the submission that first achieved the tying score.

---

## Active Now - March 19

### KO - Tripletex
- [ ] Claim sandbox account at `app.ainm.no` (Tripletex submission page)
- [ ] Stand up FastAPI `/solve` endpoint locally
- [ ] Expose via `cloudflared` tunnel (HTTPS required)
- [ ] Submit endpoint URL at `app.ainm.no/submit/tripletex`
- [ ] Get first submission scored - even a stub that returns `{"status": "completed"}` establishes a baseline
- [ ] See `solutions/tripletex/README.md` for full spec, API patterns, and scoring details

### Chris - NorgesGruppen Object Detection
- [ ] **Download training data immediately** from Submit page at `app.ainm.no` (login required)
- `NM_NGD_coco_dataset.zip` (~864 MB)
- `NM_NGD_product_images.zip` (~60 MB)
- [ ] Set up environment: `pip install ultralytics==8.1.0` (must match sandbox version exactly)
- [ ] Run pretrained YOLOv8 zero-shot on training images - assess baseline detection quality
- [ ] Build local eval script with `pycocotools` (mandatory before any upload)
- [ ] First submission: detection-only (`category_id: 0` for all) - scores up to 0.70, no fine-tuning needed
- [ ] **Only 3 submissions/day** - never upload without local eval first
- [ ] See `solutions/norgesgruppen-data/README.md` for full spec

### AD - Astar Island
- [ ] Log in at `app.ainm.no`, extract JWT token from browser cookies
- [ ] Check `GET /astar-island/rounds` - is a round currently active?
- [ ] If active: `GET /rounds/{round_id}` - get initial states for all 5 seeds
- [ ] Build terrain-based prior tensor from initial grid (free, zero queries)
- [ ] **Submit prior-only prediction for all 5 seeds immediately** - establishes live score before spending any queries
- [ ] Then begin tiling queries (9 viewports covers full 40x40 map)
- [ ] See `solutions/astar-island/README.md` for full strategy, query plan, and code templates

---

## Competition Week Plan

### Thursday March 19 - Kickoff (NOW)
- [x] Challenges read and reviewed
- [x] Ownership assigned
- [ ] All 3 owners: baseline submission on the board before end of night
- [ ] AD: Astar prior-only submission
- [ ] KO: Tripletex stub endpoint live
- [ ] Chris: NorgesGruppen data downloaded, local eval script working

### Friday March 20 - Build Day
- KO: Improve Tripletex agent - cover more task types, reduce 4xx errors for efficiency bonus
- Chris: Fine-tune YOLOv8m on NorgesGruppen data, full `nc=357` classification
- AD: Query-based Astar model - tiling + parameter inference + resubmit
- Goal: all 3 challenges scoring on leaderboard

### Saturday March 21 - Optimise
- Improve scores across all 3. External data where applicable.
- Red team testing on leading solutions.
- NorgesGruppen: explore product reference images for classification boost

### Sunday March 22 - Final
- Morning: final optimisation push
- Midday: freeze code. Run submission runbook.
- **Set repo to public before 15:00 CET** (prize eligibility)
- Final submission gate: AD (compliance) + Chris (technical) sign-off

---

## Still Open

- [ ] **Vipps verification** - remaining members (prize eligibility + rate limits)
- [ ] Confirm GCP access at `app.ainm.no` (burst compute if needed)
- [ ] Check competition rules: are NorgesGruppen product reference images allowed as training data?
- [ ] NorgesGruppen: how many test images? Need to benchmark inference time vs 300s timeout.

---

## Completed
- [x] All 3 challenges read and deep-reviewed - see `solutions/*/README.md`
- [x] Challenge ownership assigned (KO=Tripletex, Chris=NorgesGruppen, AD=Astar)
- [x] Solution directories renamed to challenge names: `tripletex/`, `astar-island/`, `norgesgruppen-data/`
- [x] Pre-competition trial (NorgesGruppen simulation, rank ~70/317) -> `solutions/grocerybot-trial-vs-code/TRIAL_SUMMARY.md`
- [x] GCP account applied (March 17)
- [x] Competition rules reviewed -> `ops/NMiAI-main-competition-rules-regulations.txt`
- [x] Team roles assigned in `AGENTS.md`
- [x] Branch protection rules set on GitHub
- [x] PR template and `CONTRIBUTING.md` created
- [x] Competition intelligence gathered -> `past-championships-data/competition-reference.md`
- [x] Verification ladder and data handling defaults in `CLAUDE.md`
- [x] `/session-handoff` and `/btw` slash commands created -> `.claude/commands/`
- [x] Slack connected to official NM i AI workspace
- [x] KO hardware confirmed: RTX 5090 Mobile 24GB VRAM (matches NorgesGruppen sandbox GPU exactly)
- [x] MIT license added (`LICENSE` file, March 17)
