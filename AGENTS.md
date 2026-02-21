# AGENTS.md

This file defines agent roles and handoff contracts for competition execution.

## Operating Model
- One owner per challenge.
- Daily sync on blockers, metrics, and risks.
- Any high-risk submission requires owner + governance sign-off.

## Agent Roster

## Team Roster (4 Members)

### Andrew Davidson (Team Captain)
- Background: R&D practitioner specialising in privacy, research ethics, AI governance, and organisational behavioural management. Cross-sector experience in higher education, health, public administration, and cultural/creative sectors (Norway and UK).
- Key strengths: GDPR and EU AI Act practical implementation, RAG systems, evaluation frameworks, automation pipelines, agent-style workflows, privacy-by-design (RoPA, IP, risk management). Grant development (Norwegian Research Council, Horizon Europe, Erasmus+). Training in project management, leadership, and communication. Behavioural science and OBM for real adoption.
- Notable: Translates policy intent into defensible, practical implementation. Designs governance into systems from day one. Strong on partnership building, budgeting, and proposal work.
- Style: Pragmatic, anti-theatre governance. Focused on making adoption real through behavioural change.

### Patrick Lundebye
- Background: Digitalization advisor (municipality sector). Former Telenor (2015–2022).
- Key strengths: Digital transformation, process design, chatbot/RPA orchestration, stakeholder communication, Microsoft cloud (MCSA 70-347), talent development, customer service redesign.
- Notable: First MCSA 70-347 in Telenor Cloud Support. Built first chatbot+RPA integration. Led corporate chatbot "Telmi" launch. Speech-to-text/text analytics acquisition lead.
- Style: Creative connector, pattern-spotter, strong communicator, morale driver.

### Christopher Coello
- Background: Data scientist / ML engineer with 13+ years in quantitative mathematical modelling, machine learning, and software engineering.
- Key strengths: End-to-end ML pipelines, production-ready Python, exploratory data analysis, mathematical modelling. Domain experience in precision farming, health, and energy.
- Notable: Focused on bringing ML products to life — full pipeline from data to deployment. Strong at simplifying complex concepts.
- Style: Hands-on builder, systematic, communication-oriented.

### Oddar (anonymised)
- Background: Sambandsoffiser (signals officer) in the Norwegian Army. Former head of Cyber Technician School (Cyberforsvaret). Bachelor from Krigsskolen (Norwegian Military Academy). Service at Garnisonen i Sør-Varanger, Telemark bataljon, Sambandsbataljonen.
- Key strengths: Computer science (systems, networking, radio, infrastructure), cyber operations, connecting systems. Has high-end compute hardware.
- Notable: Deep CS fundamentals and system integration expertise. Military-grade operational discipline.
- Style: Technical generalist, infrastructure-focused, security-minded.

## Team Assignments (Current)

Role mapping based on member strengths:
- `solver-agent`: Christopher (primary), Patrick (support)
- `eval-agent`: Christopher (primary), Oddar (support)
- `redteam-agent`: Oddar (primary — cyber/security background), Andrew (support — risk/governance lens)
- `governance-agent`: Andrew (primary — AI Act, GDPR, ethics expertise), Patrick (support)
- `submission-agent`: Andrew (primary — compliance gate owner), Patrick (coordination), Oddar (infra support)

Shift coverage: Full team coverage across competition hours.
Compute: Oddar's high-end hardware available for burst workloads alongside any cloud resources.

### 1) `solver-agent`
Scope:
- Implements baseline and advanced approaches.
- Optimizes data processing, modeling, and inference.

Must output:
- Code changes.
- Repro command.
- Metric deltas.
- Known failure cases.

### 2) `eval-agent`
Scope:
- Builds and maintains the evaluation harness.
- Checks regression across datasets/seeds.

Must output:
- Eval report with metric table.
- Confidence notes and variance.
- Regression alert summary.

### 3) `redteam-agent`
Scope:
- Stress tests edge cases and abuse patterns.
- Probes robustness and reliability.

Must output:
- Test cases run.
- Failure severity.
- Suggested mitigations.

### 4) `governance-agent`
Scope:
- Tracks AI Act relevance, privacy, and security controls.
- Maintains risk register and compliance artifacts.

Must output:
- Updated risk register entries.
- Checklist completion status.
- Blocking issues (if any).

### 5) `submission-agent`
Scope:
- Packages final deliverable and metadata.
- Verifies final gate criteria.

Must output:
- Submission bundle manifest.
- Final gate checklist result.
- Rollback/fallback plan.

## Handoff Contract
Every handoff must include:
- Current objective.
- Exact commit or artifact reference.
- What is proven.
- What is assumed.
- Next highest-priority task.

## Priority Rules
1. Validity over novelty.
2. Reproducibility over one-off wins.
3. Compliance blockers override speed.
