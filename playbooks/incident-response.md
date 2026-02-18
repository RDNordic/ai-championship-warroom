# Incident Response Playbook

Use this when a solution degrades suddenly, fails submission checks, or introduces risk.

## Incident Levels
- `SEV-1`: Blocks submission or causes disqualification risk.
- `SEV-2`: Significant metric drop or unstable behavior.
- `SEV-3`: Minor issue with workaround.

## Response Flow
1. Declare severity and incident owner.
2. Freeze non-essential changes.
3. Reproduce issue with minimal case.
4. Isolate root cause.
5. Apply fix and run focused regression checks.
6. Document outcome and prevention steps.

## Required Log Fields
- Timestamp.
- Affected challenge.
- Impact.
- Root cause.
- Mitigation.
- Follow-up actions.
