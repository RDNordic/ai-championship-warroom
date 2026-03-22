# Decision Log

## Entry Template
- Date:
- Challenge:
- Decision:
- Options considered:
- Why chosen:
- Evidence:
- Risks accepted:
- Owner:

## 2026-02-21 — Branch protection on main
- Date: 2026-02-21
- Challenge: All (repo governance)
- Decision: Enable branch protection ruleset `main-protection` on `main`.
- Options considered: (1) No protection, trust the team. (2) Light protection with PR + 1 approval. (3) Heavy protection with CI status checks + CODEOWNERS.
- Why chosen: Option 2. Team of 4, no CI yet. Enforces review without blocking velocity. Can add status checks later when GitHub Actions are wired up.
- Evidence: GitHub Pro enables rulesets on private repos.
- Risks accepted: No automated checks yet — review is human-only until CI is added.
- Owner: Andrew

## 2026-03-19 — Tripletex: Claude Sonnet as LLM backbone
- Date: 2026-03-19
- Challenge: Tripletex
- Decision: Use `claude-sonnet-4-6` via Anthropic API as the LLM backbone for the accounting agent.
- Options considered: (1) GPT-4o (2) Claude Sonnet (3) Claude Opus (4) Local open-source model.
- Why chosen: Claude Sonnet — best balance of speed (300s timeout constraint), multilingual capability (7 languages), and structured output quality. Opus too slow for per-request latency budget. GPT-4o considered but team has deeper Anthropic API experience.
- Evidence: Sandbox testing showed Sonnet completing multi-step accounting tasks within 60–120s.
- Risks accepted: Vendor dependency on Anthropic API availability during competition window.
- Owner: KO

## 2026-03-19 — Tripletex: FastAPI + cloudflared as deployment architecture
- Date: 2026-03-19
- Challenge: Tripletex
- Decision: Deploy as FastAPI app exposed via cloudflared tunnel, with GCP Cloud Run as fallback.
- Options considered: (1) cloudflared only (2) GCP Cloud Run only (3) cloudflared primary + GCP fallback.
- Why chosen: Option 3. cloudflared gives instant iteration from local machine; GCP provides reliability if local machine goes offline. Dual deployment covers R-004.
- Evidence: Both paths tested and functional before competition start.
- Risks accepted: cloudflared tunnel may drop under sustained load — acceptable with GCP fallback.
- Owner: KO

## 2026-03-19 — NorgesGruppen: YOLOv8m as detection architecture
- Date: 2026-03-19
- Challenge: NorgesGruppen Data
- Decision: Use YOLOv8m fine-tuned on competition COCO dataset as the primary detection model.
- Options considered: (1) YOLOv8n (fast, low accuracy) (2) YOLOv8m (balanced) (3) YOLOv8l (higher accuracy, VRAM risk) (4) Faster R-CNN (slower inference).
- Why chosen: YOLOv8m — fits L4 24GB VRAM comfortably, strong baseline mAP, inference well within 300s timeout. YOLOv8l considered but VRAM margin too thin for safety.
- Evidence: Run 2 scored 0.8329 (+16% over baseline), confirming model viability.
- Risks accepted: 254 images for 357 classes is severe class imbalance — low-frequency classes will have near-zero AP.
- Owner: Chris

## 2026-03-19 — Astar Island: Bayesian tiling + cross-seed inference strategy
- Date: 2026-03-19
- Challenge: Astar Island
- Decision: Tile the full 40×40 map per seed (9 queries each, 45 total), use remaining 5 queries for targeted re-observation of settlement-dense regions. Infer hidden parameters by cross-seed comparison.
- Options considered: (1) Uniform prior only (0 queries, score ~20–40) (2) Partial observation (25 queries, 5/seed) (3) Full tiling (45 queries) + targeted re-obs (5 queries).
- Why chosen: Option 3. Full tiling maximises direct evidence. Cross-seed parameter sharing is the key competitive advantage — same hidden params across all 5 seeds.
- Evidence: 14 rounds completed with this strategy; consistent scoring.
- Risks accepted: Budget fully committed — no margin for query failures.
- Owner: AD

## 2026-03-20 — Governance: EU AI Act + GDPR review for all challenges
- Date: 2026-03-20
- Challenge: All
- Decision: Complete AI Act checklists, model cards, data cards, and privacy-security checklists for all three challenges as part of submission. Apply GDPR principles by default even though competition uses synthetic data.
- Options considered: (1) Skip governance — not scored. (2) Minimal compliance notes. (3) Full governance documentation per challenge.
- Why chosen: Option 3. Differentiator for judges — demonstrates responsible AI practice beyond minimum requirements. Shows team maturity.
- Evidence: All three challenge governance folders populated with filled-in documents.
- Risks accepted: Time spent on governance is time not spent on model improvement — accepted trade-off.
- Owner: Andrew

## 2026-03-21 — Tripletex: Iterative hardening cycle (score 22 → 53.2)
- Date: 2026-03-21
- Challenge: Tripletex
- Decision: Adopt a deploy-score-fix cycle: commit before every run, revert on regression, one change per commit. Applied 23+ targeted fixes covering VAT auto-correction, plan validation, field hardening, and multilingual handling.
- Options considered: (1) Big-bang rewrite. (2) Incremental fix cycle.
- Why chosen: Option 2. Commit-before-run protocol per CLAUDE.md. Each fix isolated and testable. Score improved monotonically: 22 → 42.2 → 53.2.
- Evidence: Git history shows continuous score progression across 23+ commits.
- Risks accepted: Diminishing returns on tier-1 fixes; tier-3 multi-step tasks remain weak.
- Owner: KO
