# Evaluation Harness Guidance

Owner: Christopher (primary), Oddar (support).

## Verification Ladder
Every model change follows: **extract → draft → review**.
1. **Extract**: understand the problem, gather baseline metrics, read the data.
2. **Draft**: implement and instrument the change, capture metric deltas.
3. **Review**: challenge the change — use review prompts before accepting.

## Requirements
- Fixed validation split or challenge-equivalent protocol.
- Deterministic seed policy (document seeds used).
- Single command for baseline and candidate comparison.
- All eval runs logged with timestamp, commit hash, and seed.

## Minimum Report
Per eval run, capture:
- Metrics table with timestamp and commit hash.
- Delta vs baseline (absolute and relative).
- Runtime and cost notes (compute, API calls, wall time).
- Error sample analysis (top failure modes).
- Confidence notes (variance across seeds if applicable).

## Regression Rule
A change is accepted only if:
- Primary metric improves, **or**
- Primary metric holds while robustness improves materially.

A change is **rejected** if:
- Primary metric regresses without compensating improvement elsewhere.
- Reproducibility is broken (different results across runs with same seed).

## Review Prompts (Use Before Accepting Any Change)
- "Grill me on these changes" — force justification of every decision.
- "Prove to me this works" — demand evidence, not assertions.
- "Knowing everything you know now, scrap this" — check if the approach is still the best one.

## Eval Entrypoint (Template)
Each challenge folder should have a single-command eval:
```bash
# From solutions/challenge-N/
python eval.py --seed 42 --split val --baseline results/baseline.json
```
Adapt per challenge once requirements are known.
