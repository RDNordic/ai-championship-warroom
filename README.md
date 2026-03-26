# AI Championship War Room

Competition repo for the Norwegian AI Championship (NM i AI), March 19–22, 2026.

## Results

| Challenge | Sponsor | Owner | Score (normalised) |
|-----------|---------|-------|-------|
| NorgesGruppen — Object Detection | NorgesGruppen Data | Chris | 96.0 |
| Tripletex — AI Accounting Agent | Tripletex | KO (Oddar) | 51.8 |
| Astar Island — Viking World Prediction | Astar | AD (Andrew) | 85.5 |
| **Overall (rank 139)** | | | **77.8** |

*Preliminary results — subject to code review and verification by organizers.*

---

## Purpose
- Ship high-performing challenge solutions fast.
- Maintain compliance, risk control, and traceability by default.
- Run a repeatable team workflow under competition pressure.

## Team
- **Andrew Davidson (AD)** — Team Captain, Governance, Astar Island
- **Christopher Coello (Chris)** — NorgesGruppen Object Detection
- **Oddar (KO)** — Tripletex Accounting Agent
- **Patrick** — Advisory (Signal)

Full role assignments in `CLAUDE.md`.

---

## Repo Layout

```
solutions/          Per-challenge implementation (active competition work)
  tripletex/          Challenge 1 — AI Accounting Agent
  astar-island/       Challenge 2 — Viking World Prediction
  norgesgruppen-data/ Challenge 3 — Grocery Object Detection
  grocerybot-simulator/     } Pre-competition trial work only —
  grocerybot-trial-vs-code/ } not part of the NM i AI 2026 submission

submissions/        Packaged submission artifacts from pre-competition trials
governance/         EU AI Act + GDPR compliance docs for all three challenges
  README.md           Structure guide and AI Act classification summary
  risk-register.md    All risks across all challenges
  tripletex/          AI Act checklist, model card, data card, privacy checklist
  astar-island/       AI Act checklist, model card, data card, privacy checklist
  norgesgruppen-data/ AI Act checklist, model card, data card, privacy checklist
playbooks/          Execution runbooks (submission, intake, incident response)
evals/              Red-team tests and evaluation guidance
ops/                Decision log and postmortems
CLAUDE.md           Operating rules for AI coding assistants (includes team roster)
CONTRIBUTING.md     Branch naming and PR workflow reference
```

---

## How We Work (Git Workflow)

`main` is the submission branch. All significant changes go through pull requests.

```bash
# 1. Make sure you're on main and up to date
git checkout main && git pull

# 2. Create a branch
git checkout -b tripletex/my-fix

# 3. Commit your changes
git add <files>
git commit -m "tripletex: describe what changed"

# 4. Push and open a PR
git push -u origin tripletex/my-fix
# https://github.com/RDNordic/ai-championship-warroom/pulls
```

### Branch naming

| Prefix | When to use |
|--------|-------------|
| `tripletex/` | Tripletex challenge work |
| `astar-island/` | Astar Island challenge work |
| `norgesgruppen/` | NorgesGruppen challenge work |
| `governance/` | Compliance, risk, AI Act |
| `docs/` | Documentation |
| `hotfix/` | Urgent fixes |

---

## Minimum Evidence Before Any Submission
- Repro command and pinned dependencies.
- Metrics + known failure modes documented.
- Risk and compliance checklist completed (`governance/<challenge>/ai-act-checklist.md`).
- Named owner and rollback strategy.
