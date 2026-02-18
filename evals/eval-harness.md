# Evaluation Harness Guidance

## Requirements
- Fixed validation split or challenge-equivalent protocol.
- Deterministic seed policy.
- Single command for baseline and candidate comparison.

## Minimum Report
- Metrics table with timestamp.
- Delta vs baseline.
- Runtime and cost notes.
- Error sample analysis.

## Regression Rule
A change is accepted only if:
- Primary metric improves, or
- Primary metric holds while robustness improves materially.
