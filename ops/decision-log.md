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
