# Contributing

## Branch Rules

`main` is protected. All changes go through pull requests with at least 1 approval.

## Branch Naming

Use `{area}/{description}`:

| Prefix | Use | Example |
|--------|-----|---------|
| `challenge-N/` | Solution work for challenge N | `challenge-1/baseline` |
| `governance/` | Compliance, risk, AI Act artifacts | `governance/ai-act-checklist` |
| `infra/` | Tooling, CI, eval harness, compute setup | `infra/eval-harness` |
| `docs/` | Documentation only | `docs/update-readme` |

## PR Workflow

1. Create a branch from `main` using the naming convention above.
2. Make your changes. Keep commits focused.
3. Open a PR. The template will auto-populate — fill in all sections.
4. Get at least 1 approval before merging.
5. Use **squash merge** to keep `main` history clean.

### Review expectations by area

- **`challenge-N/`** — Christopher (technical review) + one other.
- **`governance/`** — Andrew (compliance approval) required.
- **`infra/`** — Oddar or Christopher review.
- **`docs/`** — Any team member, 1 approval.

## Required Output Format

Every PR description must include (matches CLAUDE.md):
- What changed
- Why it helps
- How to run
- Validation evidence
- Risks and mitigations

## Commit Messages

Keep them short and imperative: `Add baseline model for challenge 1`, `Fix seed handling in eval harness`.

No need for conventional commits (feat:, fix:, etc.) — just be clear.
