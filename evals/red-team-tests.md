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

### Tripletex
- [x] Ran all input edge case tests — empty/null JSON body, missing session_token, malformed prompt.
- [x] Checked adversarial inputs — prompt injection attempts blocked by system prompt scope restriction. Agent ignores instructions to deviate from accounting task context.
- [x] Stress tested API endpoint — concurrent request handling verified; stateless design ensures no state leakage between sessions.
- [x] Verified no data leakage in outputs — endpoint returns only `{"status": "completed"}`. No prompt content, API responses, or session tokens echoed.
- [x] All High severity findings mitigated or explicitly accepted — see risk-register R-001 through R-005. Residual: LLM hallucination (R-002) accepted.

### Astar Island
- [x] Ran all input edge case tests — invalid viewport coordinates, seed_index out of range, expired JWT.
- [x] Checked adversarial inputs — not applicable; pure read/compute pipeline with no user-controlled LLM input.
- [x] Stress tested API endpoint — not applicable; no hosted endpoint. Outbound API calls only.
- [x] Verified no data leakage in outputs — submissions contain only numeric probability tensors. No credentials or observations in submission payload.
- [x] All High severity findings mitigated or explicitly accepted — see risk-register R-006 through R-009. Zero-probability risk (R-007) fully mitigated.

### NorgesGruppen Data
- [x] Ran all input edge case tests — empty image directory, unsupported image format, very small/large images.
- [x] Checked adversarial inputs — not applicable; image-only model with no LLM or text input.
- [x] Stress tested API endpoint — not applicable; offline inference only. Benchmarked inference time locally: within 300s limit.
- [x] Verified no data leakage in outputs — COCO JSON predictions contain only bounding boxes and category IDs. No training data or weights exposed.
- [x] All High severity findings mitigated or explicitly accepted — see risk-register R-010 through R-013. Banned import check (R-010) enforced pre-packaging.
