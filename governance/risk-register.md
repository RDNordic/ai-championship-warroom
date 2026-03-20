# Risk Register

Track risks continuously. Update daily during competition.

| ID | Date | Challenge | Risk Description | Severity | Likelihood | Owner | Mitigation | Status |
|----|------|-----------|------------------|----------|------------|-------|------------|--------|
| R-001 | 2026-03-19 | Tripletex | JWT/session token logged or leaked (printed to stdout, stored in plaintext) | High | Medium | KO | Never log session_token; treat as ephemeral credential; confirm no logging in agent code | Open |
| R-002 | 2026-03-19 | Tripletex | LLM hallucination causes wrong API calls (wrong entity type, wrong fields) or 4xx errors, destroying efficiency score | High | High | KO | Pre-validate entities before calling; dry-run logic check; test against sandbox before live submission |  Open |
| R-003 | 2026-03-19 | Tripletex | Employee PII (names, email, roles) processed by external LLM — data minimisation obligation | Medium | High | KO | Use only competition-provided sandbox data; confirm Anthropic API terms allow this use case; do not log PII | Open |
| R-004 | 2026-03-19 | Tripletex | Endpoint downtime during active judging window causes missed evaluations | High | Low | KO | Keep cloudflared process monitored; have GCP fallback ready; test keep-alive/reconnect logic | Open |
| R-005 | 2026-03-19 | Tripletex | Multilingual prompt misclassification causes wrong task type detection (e.g., nb vs nn) | Medium | Medium | KO | Include language in system prompt; test with one prompt per language before competition; log task_type detected | Open |
| R-006 | 2026-03-19 | Astar Island | JWT access_token committed to git (`.token` file not gitignored) | High | Medium | AD | Verify `.token` is in `.gitignore`; confirm it's not tracked; use `.token.example` as safe placeholder | Open |
| R-007 | 2026-03-19 | Astar Island | Zero probability in prediction tensor causes KL divergence → ∞, destroying cell score | High | High | AD | Apply `np.maximum(prediction, 0.01)` + renormalise on every submission, no exceptions | Open |
| R-008 | 2026-03-19 | Astar Island | Query budget exhausted without full map coverage for all 5 seeds | High | Medium | AD | Plan tile queries upfront (9/seed × 5 seeds = 45); commit to budget before running observe loops | Open |
| R-009 | 2026-03-19 | Astar Island | Missing seed submission defaults to score 0 for that seed | High | Medium | AD | Submit all 5 seeds every round, even prior/baseline — partial beats 0 | Open |
| R-010 | 2026-03-19 | NorgesGruppen | `import os` or `import subprocess` in run.py triggers code scanner rejection | High | High | Chris | Use `pathlib` throughout; grep for banned imports before packaging | Open |
| R-011 | 2026-03-19 | NorgesGruppen | Model weight version mismatch causes silent load failure at inference time | High | Medium | Chris | Pin ultralytics==8.1.0, torch==2.6.0; export ONNX opset ≤ 17; test loading weights in clean env | Open |
| R-012 | 2026-03-19 | NorgesGruppen | Submission count exhausted (3/day) before best model is ready | High | Medium | Chris | Use freebie quota for infrastructure failures; run local eval before every submission; do not upload speculatively | Open |
| R-013 | 2026-03-19 | NorgesGruppen | run.py at wrong path in zip (nested in subfolder) causes submission to fail | Medium | Medium | Chris | Always use `cd my_submission && Compress-Archive`; verify with `unzip -l` before upload | Open |

## Severity Guide
- High: disqualification, major legal/privacy exposure, or hard submission failure.
- Medium: substantial metric or reliability impact.
- Low: minor impact, easy workaround.
