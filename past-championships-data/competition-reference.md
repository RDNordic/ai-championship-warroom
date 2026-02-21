# Norwegian & Danish AI Championship - Competition Reference

> Compiled from NORA.ai, Ambolt AI, and the DM-i-AI 2024/2025 GitHub repositories.

---

## Overview

The Norwegian AI Championship is a week-long virtual hackathon organized by NORA (Norwegian Artificial Intelligence Research Consortium) in partnership with Ambolt AI, the Danish Data Science Academy, and the Danish Pioneer Centre for AI. Norwegian and Danish teams share the same challenges (set by Ambolt AI) but compete separately within their own national leaderboards.

The Danish version ("DM i AI") has been running since ~2021, making the challenge format and infrastructure well-established. Norway's first edition was in 2025.

**2025 key dates (Norway):**

| Event | Date |
|---|---|
| Registration closes | July 31, 2025 23:59 |
| Hackathon runs | August 1-8, 2025 |
| Virtual kick-off & use-case reveal | August 1, 10:00 |
| Final submission deadline | August 8, 14:00 |
| Winner presentations | August 26-27, 2025 |
| Award ceremony (Nordic AI Meet) | November 26-27, 2025 |

**Prizes (Norway):** 40,000 NOK (1st), 5,000 NOK each (2nd & 3rd).

---

## Competition Format

- **3 use cases**, each worth equal weight (1/3 of total score).
- Participants build **end-to-end ML systems with API endpoints** - not just models.
- **Evaluation is fully automated** based on well-defined scoring metrics. Code robustness only matters if things break during evaluation.
- **Validation:** unlimited attempts against a validation dataset, scores shown on a live scoreboard.
- **Evaluation:** a single final submission per use case, scored on a held-out test set.
- Top 5 teams must submit their training code and models for a Scientific Jury review.

### Scoring (2025 - F1-style ranking)

| Place | Points |
|---|---|
| 1st | 25 |
| 2nd | 18 |
| 3rd | 15 |
| 4th | 12 |
| 5th | 10 |
| 6th | 8 |
| 7th | 6 |
| 8th | 4 |
| 9th | 2 |
| 10th | 1 |
| 11th+ | Fractional (1 to 0) |

Total score = sum of points across all 3 use cases.

In 2024, scoring was instead a normalized 0-1 placement per use case, averaged.

---

## Rules & Constraints

### Allowed
- **External data** is strongly encouraged and has been a key differentiator for past winners (e.g., finding additional medical images for a CT scan task, gathering ratings from other websites for sentiment analysis).
- **Pretrained models** from any source (HuggingFace, etc.).
- **Any programming language or framework**, though Python dominates.
- Training on personal hardware, Google Colab, or cloud resources.

### Not Allowed (2025)
- **No cloud API calls during inference** (OpenAI, Google Cloud, AWS, Azure). Cloud APIs are fine for development, but deployed models must run independently.
- Exceeding per-request time limits (varies by challenge, typically 5-10 seconds).
- Exceeding memory limits where specified (e.g., 24 GB VRAM).

### Infrastructure
- Teams provide their own compute for training.
- 2025 participants got access to **UCloud** with NVIDIA L4 (24 GB) or L40 (48 GB) GPUs.
- Azure for Students free credits are also an option.
- Local deployment with a public IP (e.g., via ngrok) works and took past winners about an hour to set up.
- **Get a server running early** - don't discover infrastructure issues at the deadline.

---

## Team & Preparation

- **Recommended team size:** 2-5 people. Solo participation is possible (a solo competitor was runner-up one year), but teams of 2-5 have been most successful.
- **Pre-work:** Challenges aren't revealed until kick-off, but you can prepare by learning API setup, server communication, model training pipelines, and studying past challenges.
- **Past winners invested significant hours.** Strategy: run long training jobs overnight, optimize quality hours when mentally sharp.
- **Community:** Discord server for connecting with other participants and organizers.

---

## Past Challenges

### 2025 Challenges

#### 1. Race Car (Simulation / Reinforcement Learning)

Control a yellow car dodging opponent vehicles across 5 lanes. Maximize distance traveled in 60 seconds (3,600 ticks at 60 fps). Crashing ends the run.

- **Actions:** NOTHING, ACCELERATE, DECELERATE, STEER_RIGHT, STEER_LEFT
- **Sensors:** 16 sensors at fixed angles, 1,000-pixel range, detecting obstacles in all directions.
- **Scoring:** Distance traveled before crash, normalized (lowest = 0, highest = 1). Below baseline = 0.
- **Key detail:** Send batches of actions (not one at a time) to minimize network delay impact.
- **Evaluation:** One attempt with a preset seed. Validation uses random seeds with unlimited attempts.

#### 2. Emergency Healthcare RAG (NLP / Retrieval-Augmented Generation)

Evaluate medical statements about emergency healthcare conditions. Two tasks per statement:
1. **Binary classification:** Is the statement true or false?
2. **Multi-class classification:** Which of 115 emergency healthcare topics does it relate to?

- **Data:** 200 training statements, 200 validation, 749 evaluation. Source: Claude Opus-generated statements based on StatPearls articles (provided in `data/topics/`).
- **Scoring:** Accuracy (correct / total) for each sub-task.
- **Constraints:** Max 5 seconds per statement, max 24 GB VRAM, fully offline inference (no cloud APIs).
- **Approaches:** RAG with offline LLMs (Ollama, llama.cpp, vLLM, HuggingFace Transformers). Optimize quantization and context length for speed/memory.

#### 3. Tumor Segmentation (Medical Imaging)

Detect and segment tumors in whole-body MIP-PET images. Binary pixel classification: tumor vs. healthy tissue.

- **Data:** 182 patient images with ground truth + 426 healthy controls. Validation/test: 200 cancer patient samples each (no healthy controls in eval).
- **Input:** MIP-PET images, max 400x991 px.
- **Output:** RGB segmentation mask - white (255,255,255) for tumor, black (0,0,0) for healthy.
- **Scoring:** Dice-Sorensen coefficient: `(2*TP) / (2*TP + FP + FN)`. Range 0-1, higher is better.
- **Constraints:** 10 seconds per image.
- **Complexity:** Organs like brain, bladder, kidneys, heart, and liver naturally show high glucose uptake in PET scans, creating false positives. Patient factors (fasting, chemo, temperature) add noise.

### 2024 Challenges

#### 1. Traffic Simulation (Optimization / Control)

Optimize traffic light control at congested intersections using the SUMO framework. Minimize vehicle waiting times over a 10-minute simulation.

- **Input (every second):** Vehicles within 100m (distance, speed, lane), current signal states, allowed green combinations, simulation tick.
- **Output:** Traffic light commands (red/green per signal group).
- **Scoring:** Sum of waiting times + exponential penalty for waits > 90 seconds. Normalized 0-1 against baseline and best.
- **Constraints:** 1-second response time. Signal transition rules enforced (min green: 6s, min amber: 4s, min redamber: 2s).
- **Key detail:** Tested on multiple intersections with varying traffic patterns - must generalize, not overfit to validation.

#### 2. Cell Classification (Computer Vision)

Classify fluorescence microscope images of bone marrow cells into heterogeneous vs. homogeneous subpopulations. The homogeneous population is a small minority.

- **Data:** 139 training images (16-bit .tif), 131 validation (8-bit), 117 evaluation (8-bit). Single donor, identical culture/imaging conditions.
- **Scoring:** `(a0 * a1) / (n0 * n1)` where a0/a1 = correct predictions per class, n0/n1 = total per class. Must perform well on both classes - failing either zeros the score.
- **Constraints:** 10 seconds per image.

#### 3. CT Inpainting (Medical Imaging / Generative)

Reconstruct corrupted regions in 2D cross-sectional CT images.

- **Data:** 5,900 samples from 590 patients (10 slices each). Validation: 166 slices, test: 182 slices.
- **Input:** Corrupted 256x256 grayscale CT image + binary corruption mask + tissue map (fat/body segmentation) + vertebrae position index.
- **Output:** Reconstructed image.
- **Scoring:** Mean Absolute Error (MAE), normalized to 0-1 scale. Baseline MAE: 6.0.
- **Constraints:** 10 seconds per image.

---

## Patterns Across Competitions

| Pattern | Details |
|---|---|
| **Challenge mix** | Typically 1 vision/medical imaging, 1 NLP/classification, 1 simulation/optimization task |
| **Medical imaging is common** | CT inpainting (2024), tumor segmentation (2025), and past winners used external medical data |
| **API-first** | Everything is served via REST APIs (FastAPI or Flask). Fast response times matter. |
| **Time limits** | 1-10 seconds per request depending on challenge |
| **External data wins** | Consistently cited as the biggest competitive advantage |
| **One-shot evaluation** | Single submission to test set, so validation strategy is critical |
| **Generalization** | Test sets differ from validation sets - overfitting is punished |

---

## Resource Links

- [DM-i-AI 2022 challenges](https://github.com/amboltio/DM-i-AI-2022)
- [DM-i-AI 2023 challenges](https://github.com/amboltio/DM-i-AI-2023)
- [DM-i-AI 2024 challenges](https://github.com/amboltio/DM-i-AI-2024)
- [DM-i-AI 2025 challenges](https://github.com/amboltio/DM-i-AI-2025)
- [Advice from 2025 winners](https://norwegian-ai-championships-guide.lovable.app)
- [Discord community](https://discord.gg/QVSZECgw8g)
