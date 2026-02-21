# Norwegian & Danish AI Championship - Competition Reference

> Compiled from NORA.ai, Ambolt AI, DM-i-AI GitHub repos, Pioneer Centre articles, kode24.no, and web research.
> Last updated: 2026-02-21

---

## 2026 Competition (THIS YEAR)

**Event:** NM i KI / NMiAI - Norwegian AI Championship 2026
**Organizer:** Astar Consulting (founded by Mikael Steenbuch and Erik Nymo Bohne, both 23, NTNU)
**Partners:**
- **Google** — infrastructure, Gen AI capabilities, and servers for participants
- **KI Norge** (Norwegian Government AI Unit) — signed Letter of Intent
- **NorgesGruppen Data** — main partner, defining one of the three challenges, co-sponsoring 400K NOK first prize
- **DNV** — gold partner (energy, maritime, healthcare, digital infrastructure)
- **Miles AS** — first gold partner (IT consulting)
- **TEK Norge** — industry association for Norwegian tech
- **NORA** — Norwegian AI Research Consortium
- **ODA-Nettverk** — diversity in tech partner
- **Mesh Community** — venue/hub partner

**Dates:** March 19-22, 2026 (some sources say 19-23; treat as Thu evening → Sun)
**Locations:** Digital (remote) + physical hubs in Oslo (Mesh Youngstorget), Trondheim (DIGS), and partner offices (Google, consulting firms)
**Kickoff:** March 19 at 17:00 in Oslo; challenges released at 18:00
**Expected participants:** ~1,000 (was 120 in 2025)
**Prize pool:** NOK 1,000,000 (first prize: 400,000 NOK co-sponsored by NorgesGruppen Data)
**App:** https://app.ainm.no/
**Registration:** https://app.ainm.no/

**Sources:**
- https://www.kode24.no/artikkel/nm-i-ki-arrangeres-for-forste-gang-for-alle-premiepotten-er-pa-1-million-kroner/253722
- https://www.shifter.no/nyheter/mangedobler-potten-legger-en-million-pa-bordet-for-a-kare-norges-beste-i-ai/440322
- LinkedIn posts from Astar / NorgesGruppen Data / KI Norge

### Challenge Categories (CONFIRMED)
1. **Computer Vision**
2. **Machine Learning**
3. **NLP / Language Models** (språkmodeller)

### Challenge Providers
- **NorgesGruppen Data** is defining one of the three challenges based on a real business problem. NorgesGruppen has 46,000 employees, 2,000 stores, 17,000 products already using computer vision at checkout. This is very likely the **Computer Vision** challenge.
- The other two challenge providers are not yet confirmed publicly.

### Key Changes From 2025
- **Open to everyone** — students, professionals, retirees, companies. Not student-only.
- **Students compete in a separate subcategory** but are also automatically entered in the main competition.
- **4-day format** (was 7 days in 2025).
- **March timing** (was August in 2025).
- **Massively increased prizes** — 1M NOK total (was 50K NOK in 2025). First prize: 400K NOK.
- **Free for individuals**, companies pay participation fee.
- Physical hubs with livestreamed kickoff.
- **~1,000 expected participants** (was 120 in 2025).
- **Google providing infrastructure and servers** — participants may get cloud access.
- **Government backing** via KI Norge.

### Organizer Statements (kode24.no interview)

**On AI tooling (Erik Nymo Bohne):**
> "The value of a coder in 2026 isn't syntax knowledge — it's infrastructure, code, and problem-solving. We expect top-ten finishers haven't written a single line of code themselves but relied almost entirely on language models. Otherwise, you're working too slowly."

**On who can win (Steenbuch & Bohne):**
> "We don't think a large consulting firm's AI team will necessarily win. One student alone could take victory. It's such a transformative time for AI — that's very possible."

**On GDPR / security (Steenbuch):**
> "Participants solve challenges on their own machines and send the answers back. They don't need to worry about security aspects. For actual production development, there are major concerns around GDPR — you need professionals who can serve as a human quality stamp."

**On accessibility:**
> "It's remarkable how far you can get with little tech insight. Use ChatGPT to guide you in understanding the problem and achieving solutions. Prompt coding becomes an important part of the competition itself."

### What We Know
- 3 challenges released simultaneously at 18:00 on March 19.
- Categories: Computer Vision, Machine Learning, NLP.
- NorgesGruppen Data providing one challenge (likely CV — grocery/retail context).
- Automated API scoring with real-time leaderboard.
- Solve on own machine, send answers back.
- LLM-assisted coding explicitly expected and encouraged.
- Google providing infrastructure and servers to participants.
- Supports common programming languages.
- Students have a separate subcategory but also compete in main.

### What We Don't Know Yet
- Exact challenge specifications (revealed at kickoff).
- Submission limits (single vs multiple attempts on eval set).
- Inference constraints (cloud API ban? VRAM limits? Time limits per request?).
- Who provides the other two challenges (ML and NLP).
- Top-N code verification requirement.
- Exact scoring formula (F1-style points vs normalized placement).
- Exact prize distribution beyond first place (400K NOK).
- What Google infrastructure access looks like in practice.

---

## Historical Overview

| Year | Country | Format | Duration | Challenges | Scoring |
|------|---------|--------|----------|------------|---------|
| 2022 | Denmark | API | ~1 week | Sentiment Analysis, Pig Detection, Robot Robbers | Normalized 0-1 averaged |
| 2023 | Denmark | API | ~1 week | Lunar Lander, AI Text Detector, Tumor Segmentation | Normalized 0-1 averaged |
| 2024 | Denmark | API | 1 week | Traffic Simulation, Cell Classification, CT Inpainting | Normalized 0-1 averaged |
| 2025 | Denmark + Norway (first) | API | 1 week (Aug 1-8) | Race Car, Emergency Healthcare RAG, Tumor Segmentation | F1-style points |
| 2026 | Norway | API | 4 days (Mar 19-22) | Language Models, Computer Vision, Machine Learning | TBD |

---

## Past Challenges (Detailed)

### 2025

#### Race Car (Simulation / Reinforcement Learning)
Control a yellow car dodging opponent vehicles across 5 lanes. Maximize distance traveled in 60 seconds (3,600 ticks at 60 fps). Crashing ends the run.

- **Actions:** NOTHING, ACCELERATE, DECELERATE, STEER_RIGHT, STEER_LEFT
- **Sensors:** 16 sensors at fixed angles, 1,000-pixel range, detecting obstacles in all directions.
- **Scoring:** Distance traveled before crash, normalized. Below baseline = 0.
- **Key detail:** Send batches of actions (not one at a time) to minimize network delay impact.
- **Evaluation:** One attempt with preset seed. Validation: random seeds, unlimited attempts.

#### Emergency Healthcare RAG (NLP / RAG)
Evaluate medical statements about emergency healthcare conditions:
1. Binary classification: Is the statement true or false?
2. Multi-class classification: Which of 115 emergency healthcare topics does it relate to?

- **Data:** 200 training, 200 validation, 749 evaluation. Source: Claude Opus-generated statements from StatPearls articles.
- **Scoring:** Accuracy per sub-task.
- **Constraints:** Max 5 seconds per statement, max 24 GB VRAM, fully offline inference (no cloud APIs).

#### Tumor Segmentation (Medical Imaging)
Detect and segment tumors in whole-body MIP-PET images. Binary pixel classification.

- **Data:** 182 patients + 426 healthy controls. Validation/test: 200 cancer patients each.
- **Input:** MIP-PET images, max 400x991 px.
- **Output:** RGB mask — white for tumor, black for healthy.
- **Scoring:** Dice-Sorensen coefficient.
- **Constraints:** 10 seconds per image.

### 2024

#### Traffic Simulation (Optimization / Control)
Optimize traffic light control at congested intersections using SUMO. Minimize waiting times over 10-minute simulation.

- **Input:** Vehicles within 100m (distance, speed, lane), signal states, allowed combos, tick.
- **Output:** Traffic light commands per signal group.
- **Scoring:** Sum of waiting times + exponential penalty for waits > 90s. Normalized 0-1.
- **Constraints:** 1-second response time. Signal transition rules enforced.
- **Key detail:** Tested on multiple intersections — must generalize.

#### Cell Classification (Computer Vision)
Classify fluorescence microscopy images of bone marrow cells (heterogeneous vs homogeneous).

- **Data:** 139 training (16-bit .tif), 131 validation (8-bit), 117 evaluation (8-bit).
- **Scoring:** `(a0 * a1) / (n0 * n1)` — must perform well on both classes.
- **Constraints:** 10 seconds per image.

#### CT Inpainting (Medical Imaging / Generative)
Reconstruct corrupted regions in 2D CT images.

- **Data:** 5,900 samples from 590 patients. Val: 166, test: 182 slices.
- **Input:** Corrupted 256x256 CT + mask + tissue map + vertebrae index.
- **Scoring:** Mean Absolute Error, normalized. Baseline MAE: 6.0.
- **Constraints:** 10 seconds per image.

### 2023

#### Lunar Lander (Reinforcement Learning / Control)
Classic control problem — land a spacecraft safely.

#### AI Text Detector (NLP / Classification)
Detect AI-generated vs human-written text.

#### Tumor Segmentation (Medical Imaging)
Same type as 2025 — recurring challenge category.

### 2022

#### Sentiment Analysis (NLP)
Predict review score (1-5) from electronics product review text.

#### Pig & Piglet Detection (Computer Vision / Object Detection)
Detect and count pigs in images.

#### Robot Robbers (Simulation / Optimization)
Optimization/control challenge.

---

## Winners and Strategies

### 2025 Norway — Team "Attention Heads" (NTNU)
- 6 students (4th-5th year CS and Cybernetics)
- Won the inaugural Norwegian championship
- No specific strategy details disclosed publicly

### 2025 Denmark — Team "Powered by SmartFridge"
- Won with **simple, proven techniques over complex AI systems**
- Used **BM25 indexing** (classical information retrieval) for the healthcare RAG challenge
- Applied **Bayesian optimization** methods
- Used **Gemma 3:27B** language model for truthfulness evaluation
- Key lesson: "Simple, proven techniques can be just as effective as complex alternatives" under resource constraints

### 2024 Denmark — Team "PER" (KU + DTU)
- First-ever joint team from two universities to win
- Credited "good organisation, thorough testing, and early exploration of different strategies"
- Had "a solid technical setup" prepared before competition
- "Effectively divided the work" for parallel problem-solving
- Previously placed 2nd in DM i AI 2023
- 5 members who met 6 years ago at a programming competition

---

## Cross-Year Patterns

| Pattern | Details |
|---------|---------|
| **Challenge mix** | Always 3 challenges. Typically: 1 vision/medical imaging, 1 NLP/classification, 1 simulation/optimization |
| **Medical imaging recurs** | Tumor segmentation (2023, 2025), CT inpainting (2024), cell classification (2024) |
| **RL/simulation recurs** | Robot Robbers (2022), Lunar Lander (2023), Traffic Sim (2024), Race Car (2025) |
| **NLP always present** | Sentiment (2022), AI Text Detection (2023), Healthcare RAG (2025) |
| **API-first** | Everything served via REST API (FastAPI). Response time matters. |
| **Time limits** | 1-10 seconds per request depending on challenge |
| **External data wins** | Consistently cited as the biggest competitive advantage |
| **One-shot evaluation** | Single submission to test set — validation strategy is critical |
| **Generalization** | Test sets differ from validation — overfitting is punished |
| **Simple beats complex** | 2025 winner used BM25 over complex LLM approaches |
| **Preparation wins** | 2024 winner credited pre-built infrastructure and organisation |

---

## Rules & Constraints (Based on 2024-2025, expect similar in 2026)

### Typically Allowed
- External data (strongly encouraged, key differentiator).
- Pretrained models from any source (HuggingFace, etc.).
- Any programming language or framework.
- Training on personal hardware, Colab, or cloud.
- Cloud APIs during development/training.

### Typically Not Allowed
- Cloud API calls during inference (models must run independently).
- Exceeding per-request time limits.
- Exceeding memory limits (e.g., 24 GB VRAM).

### Infrastructure
- Teams provide own compute for training.
- Past years provided UCloud access (NVIDIA L4/L40 GPUs).
- Local deployment with public IP (ngrok) works.
- **Get server running early** — don't discover infra issues at deadline.

### Scoring (2025 Model — F1-style)
| Place | Points |
|-------|--------|
| 1st | 25 |
| 2nd | 18 |
| 3rd | 15 |
| 4th | 12 |
| 5th | 10 |
| 6th-10th | 8, 6, 4, 2, 1 |
| 11th+ | Fractional (1→0) |

Total = sum across all 3 challenges.

### Top-5 Verification
Top 5 teams must submit training code and models for Scientific Jury review.

---

## Strategic Takeaways for 2026

### Pre-Competition (NOW → March 18)
1. **API scaffold ready** — FastAPI template with health check, ready to deploy.
2. **Deployment pipeline tested** — Can go from local to public endpoint in < 30 minutes.
3. **GPU access confirmed** — Know exactly where you'll train (local, cloud, UCloud if offered).
4. **External data playbook** — Know how to rapidly find and integrate external datasets for common challenge types (medical imaging, NLP, CV).
5. **Team roles and workflow rehearsed** — Everyone knows the branch/PR/deploy flow.

### During Competition (March 19-22)
1. **Hour 1-2: Get a valid baseline submission for all 3 challenges.** Don't optimise until you have something scoring.
2. **External data hunt immediately** — Biggest competitive edge historically.
3. **Simple first, complex later** — BM25 beat LLMs in 2025. Start with proven methods.
4. **Monitor validation carefully** — One-shot eval means your validation strategy IS your strategy.
5. **Infra discipline** — One person owns deployment. Everyone else focuses on modelling.
6. **Sleep and shift** — 4 days is a marathon. Rotate to stay sharp.

### Common Pitfalls
- Spending too long on one challenge (equal weight across 3).
- Overfitting to validation set (test set will differ).
- Infrastructure failures at deadline (test deployment early).
- Over-engineering when simple methods score well.
- Not using external data when it's allowed and encouraged.

---

## Resource Links

- [NMiAI 2026 App](https://app.ainm.no/)
- [DM-i-AI 2022](https://github.com/amboltio/DM-i-AI-2022)
- [DM-i-AI 2023](https://github.com/amboltio/DM-i-AI-2023)
- [DM-i-AI 2024](https://github.com/amboltio/DM-i-AI-2024)
- [DM-i-AI 2025](https://github.com/amboltio/DM-i-AI-2025)
- [2025 Winners Guide](https://norwegian-ai-championships-guide.lovable.app)
- [2025 Norway Winner Article](https://www.nora.ai/news/2025/studentteam-attention-heads-fra-ntnu-ble-historien.html)
- [2025 Denmark Winner Article](https://www.aicentre.dk/news/dm-in-ai-2025-sometimes-the-simple-solutions-are-just-as-good-as-the-fancy-ones)
- [2024 Denmark Winner Article](https://di.ku.dk/english/news/2024/first-time-ever-a-joint-team-of-students-from-two-universities-win-dm-in-ai/)
- [NORA News](https://www.nora.ai/news/)
- [DM i AI Official](https://dmiai.dk/)
