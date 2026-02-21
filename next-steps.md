# Next Steps

## Completed
- [x] Finalize role assignments for competition week coverage (4-person team assigned in AGENTS.md).
- [x] Set up branch protection rules on GitHub (main-protection ruleset).
- [x] Create PR template and CONTRIBUTING.md for team workflow.
- [x] Comprehensive competition intelligence gathered (competition-reference.md).
- [x] Integrate verification ladder, review prompts, and data handling defaults into CLAUDE.md.
- [x] Expand eval harness, red team tests, and privacy checklist.

## Before March 19 (Competition Prep)

### Infrastructure (Priority — do this week)
- [ ] Install and configure must-have MCP stack (MarkItDown, GitHub MCP).
- [ ] Test each enabled MCP in a dry-run against a mock challenge.
- [ ] Create `.claude/settings.json` with MCP server configs.
- [ ] Add `requirements.txt` / `package.json` with pinned versions for core dependencies.
- [ ] Pre-build FastAPI scaffold template (based on DM-i-AI pattern) ready to clone per challenge.
- [ ] Test deployment pipeline: local → public endpoint (ngrok or cloud) in < 30 minutes.
- [ ] Confirm GPU access: Oddar's hardware specs, Google cloud access (if provided to participants), any backup options.
- [ ] Activate branch protection ruleset back to "Active" once team is onboarded.

### Challenge Prep (Based on confirmed categories)
- [ ] **Computer Vision**: Review NorgesGruppen's existing CV use (product recognition at checkout). Prepare common CV pipelines (detection, segmentation, classification). Have pretrained models ready (YOLO, SAM, ResNet, etc.).
- [ ] **NLP / Language Models**: Prepare RAG pipeline template (based on 2025 Healthcare RAG pattern). Have BM25 + local LLM ready (the approach that won 2025). Test offline LLM inference (Ollama/vLLM).
- [ ] **Machine Learning**: Prepare general ML pipeline template (data loading, feature engineering, model training, eval). Have XGBoost/LightGBM/scikit-learn ready.
- [ ] Pre-write one submission command template per challenge folder in `solutions/challenge-1/README.md`, `solutions/challenge-2/README.md`, and `solutions/challenge-3/README.md`.
- [ ] Add a reproducibility checklist item for model/code artifact retention in `playbooks/submission-runbook.md`.
- [ ] Create a single-command local eval entrypoint template.

### External Data Playbook
- [ ] Build a quick-reference list of external data sources for common challenge types:
  - Medical imaging: public datasets (TCIA, Grand Challenge, etc.)
  - NLP: HuggingFace datasets, StatPearls, Wikipedia dumps
  - Retail/grocery: open product databases, image datasets
  - General CV: ImageNet, COCO, Open Images
- [ ] Document how to rapidly integrate external data (download scripts, format conversion).

### Team Onboarding
- [ ] All 4 members in Signal group.
- [ ] All 4 members with GitHub repo access and confirmed push/PR ability.
- [ ] Each member does a test PR → review → merge cycle.
- [ ] Share competition-reference.md with team for review.
- [ ] Run full dry-run of `playbooks/submission-runbook.md` with tooling in place.

### Governance (Andrew)
- [ ] Consider referencing `D:\Projects\eu-ai-compliance-toolkit` during competition as local decision-support.
- [ ] Prepare lightweight model card template that can be filled in < 10 minutes per challenge.
- [ ] Review if AI Act checklist needs simplification for competition speed.

## Competition Week Plan (March 19-22)

### Thursday March 19 (Kickoff)
- 17:00: Kickoff event (Oslo / remote)
- 18:00: Challenges released
- 18:00-18:30: Read all 3 challenges. Identify quick wins vs hard problems.
- 18:30-19:00: Assign challenge ownership. Christopher picks primary challenge.
- 19:00-21:00: Get baseline submissions running for all 3 challenges.
- 21:00: First sync — what's working, what's blocked.

### Friday March 20 (Build Day)
- Parallel work: Christopher + Oddar on modelling, Andrew + Patrick on governance + external data.
- 2-hour sync checkpoints.
- Goal: all 3 challenges scoring on leaderboard by end of day.

### Saturday March 21 (Optimise)
- Focus on improving scores. External data integration.
- Red team testing on leading solutions.
- Goal: competitive scores on all 3 challenges.

### Sunday March 22 (Final)
- Morning: final optimisation push.
- Midday: freeze code. Run submission runbook.
- Final submission gate: Andrew (compliance) + Christopher (technical) sign-off.

## MCP Tooling Review (2026-02-19)

### Must-Have Baseline (install before March 19)
1. **MarkItDown** (microsoft/markitdown) - Convert challenge PDFs, papers, and dataset docs into Markdown for LLM ingestion.
2. **GitHub MCP Server** (github/github-mcp-server) - GitHub integration through AI workflow.

### Optional MCPs (only if challenge requires them)
3. **Context7** (upstash/context7) - Live library docs; useful for unfamiliar frameworks.
4. **Playwright MCP** (microsoft/playwright-mcp) - Browser automation for web submissions.
5. **MCP Run Python** (pydantic/pydantic-ai) - Sandboxed Python execution for rapid prototyping.
6. **Cognee** (topoteretes/cognee) - Graph/vector RAG pipeline if RAG-heavy challenge appears.

### MCP Kill Criteria
- Remove any MCP if setup takes more than 30 minutes with no working dry-run.
- Remove any MCP that fails in 2 or more dry-runs.
- Remove any MCP that cannot show clear value in speed, score, or submission reliability.

### Fallback Path
- If MCP stack is unstable, run local-script-only workflow (no MCP dependency).

## Still Unclear (Track As Assumptions)
- Submission cap/frequency (single vs multiple attempts on eval set).
- Exact timezone binding for deadlines.
- Exact end date (some sources say March 22, others March 23).
- What Google-provided infrastructure access looks like in practice.
- Who provides the other two challenges (NorgesGruppen confirmed for one).
- Inference constraints (cloud API ban? VRAM limits?).
- Code disclosure obligations for top teams.
