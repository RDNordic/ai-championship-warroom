# AI Championship War Room

Private prep repo for the Norwegian AI Championship (March 19-22, 2026).

## Purpose
- Ship high-performing challenge solutions fast.
- Maintain compliance, risk control, and traceability by default.
- Run a repeatable team workflow under competition pressure.

## Team
- **Andrew Davidson** — Team Captain (governance, compliance, coordination)
- **Christopher Coello** — ML/Data Science lead
- **Patrick Lundebye** — Digitalization, process design, communication
- **Oddar** — Infrastructure, cyber/security, compute

Full profiles and role assignments are in `AGENTS.md`.

## Repo Layout
- `CLAUDE.md`: Operating rules for AI coding assistants.
- `AGENTS.md`: Team roster, agent roles, contracts, and handoffs.
- `CONTRIBUTING.md`: Branch naming and PR workflow reference.
- `playbooks/`: Execution runbooks for intake, submission, and incidents.
- `governance/`: Compliance and governance templates.
- `evals/`: Evaluation harness and red-team test guidance.
- `solutions/`: Per-challenge implementation folders.
- `ops/`: Decision log, assumptions, and postmortems.
- `.github/pull_request_template.md`: Auto-fills PR descriptions.

## How We Work (Git Workflow)

`main` is protected. Nobody pushes directly to it. All changes go through pull requests.

### Step by step

```bash
# 1. Make sure you're on main and up to date
git checkout main
git pull

# 2. Create a branch for your work (see naming convention below)
git checkout -b challenge-1/my-feature

# 3. Do your work — edit files, add code, etc.

# 4. Stage and commit your changes
git add <files you changed>
git commit -m "Add baseline model for challenge 1"

# 5. Push your branch to GitHub
git push -u origin challenge-1/my-feature

# 6. Open a pull request
#    Go to the link GitHub prints in your terminal, or visit:
#    https://github.com/RDNordic/ai-championship-warroom/pulls
#    Click "New pull request", select your branch, fill in the template.

# 7. Get at least 1 approval from a teammate, then merge.

# 8. After merging, switch back to main and pull
git checkout main
git pull
```

### Branch naming convention

| Prefix | When to use | Example |
|--------|-------------|---------|
| `challenge-N/` | Solution work for challenge N | `challenge-1/baseline` |
| `governance/` | Compliance, risk, AI Act work | `governance/ai-act-checklist` |
| `infra/` | Tooling, CI, eval harness | `infra/eval-harness` |
| `docs/` | Documentation changes | `docs/update-readme` |
| `hotfix/` | Urgent leaderboard or reliability fixes | `hotfix/api-timeout` |

### Common situations

**"I accidentally committed to main and can't push"**
```bash
# Save your work to a new branch
git branch my-branch-name

# Reset main back to match the remote
git reset --hard origin/main

# Switch to your branch and push it
git checkout my-branch-name
git push -u origin my-branch-name

# Then open a PR on GitHub
```

**"I want to get someone else's latest changes"**
```bash
git checkout main
git pull
```

**"I'm working on a branch and main has been updated"**
```bash
git checkout main
git pull
git checkout my-branch
git rebase main
```

## Challenge Kickoff (Captain Action)
When organizers release the challenge repository, paste the link here and start intake.

- Captain: Andrew Davidson
- Challenge Repo URL: `PASTE_URL_HERE`
- Kickoff command set:
  - Clone or add remote to local workspace.
  - Create challenge branch (`challenge-1/*`, `challenge-2/*`, or `challenge-3/*`).
  - Execute `playbooks/challenge-intake.md` immediately.

## Minimum Evidence Before Any Submission
- Repro command and pinned dependencies.
- Metrics + known failure modes.
- Risk and compliance checklist completed.
- Named owner and rollback strategy.

## Quick Start (New Team Member)
1. Clone the repo: `git clone https://github.com/RDNordic/ai-championship-warroom.git`
2. Read this README and `CONTRIBUTING.md`.
3. Check your role in `AGENTS.md`.
4. Before kickoff, run one full dry-run using `playbooks/submission-runbook.md`.
5. For each challenge, copy governance templates and complete minimum fields.
