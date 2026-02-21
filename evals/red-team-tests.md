# Red Team Tests

Owner: Oddar (primary), Andrew (support — governance/risk lens).

Run these before each serious submission.

## Test Categories

### Input Edge Cases
- Empty/null inputs
- Maximum length inputs
- Unicode, special characters, encoding edge cases
- Unexpected data types or formats

### Distribution Shift
- Inputs outside training distribution
- Rare class / extreme values
- Temporal shift (if time-series)

### Adversarial / Malformed Inputs
- Adversarial examples (if applicable to challenge type)
- Prompt injection (if LLM-based)
- Malformed API requests (bad JSON, missing fields, wrong types)

### Resource Stress
- Latency under load (concurrent requests)
- Memory usage at scale
- Timeout behaviour
- Recovery after failure

### Data Leakage / Privacy
- Does the model memorise or leak training data?
- Can outputs be used to reconstruct sensitive inputs?
- Are there unintended information channels?

## Output Requirements Per Test
- Test case identifier
- Expected behaviour
- Actual behaviour
- Severity (High / Medium / Low)
- Mitigation owner
- Status (Open / Mitigated / Accepted)

## Stop Conditions
Do **not** submit when:
- High severity issue is unmitigated.
- Reproducibility is broken.
- Safety/privacy control is missing for a known risk.
- API endpoint fails on any edge case in the "Input Edge Cases" category above.

## Quick Red Team Checklist (Pre-Submission)
- [ ] Ran all input edge case tests.
- [ ] Checked adversarial inputs (if applicable).
- [ ] Stress tested API endpoint.
- [ ] Verified no data leakage in outputs.
- [ ] All High severity findings mitigated or explicitly accepted.
