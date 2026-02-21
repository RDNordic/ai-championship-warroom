# Privacy and Security Checklist

Complete per challenge. Owner: Andrew (primary), Patrick (support).

## Data Inventory
- [ ] All data sources listed with origin and licence/terms.
- [ ] Lawful basis for processing documented (competition rules, open data, consent, etc.).
- [ ] Personal data identified — if present, purpose and minimisation documented.
- [ ] Sensitive attributes flagged (health, biometric, ethnic, political, etc.).
- [ ] External/third-party data usage compliant with competition rules.

## GDPR Principles (Apply By Default)
- [ ] **Purpose limitation**: data used only for the stated challenge purpose.
- [ ] **Data minimisation**: only necessary fields/features retained.
- [ ] **Storage limitation**: retention/deletion plan defined (post-competition cleanup).
- [ ] **Accuracy**: data quality checks run, known issues documented.
- [ ] **Integrity and confidentiality**: access controls and encryption where needed.

## Security
- [ ] Secrets managed outside source code (env vars, .gitignore, vault).
- [ ] Third-party dependencies reviewed for known vulnerabilities.
- [ ] Prompt injection or adversarial input checks run (if applicable).
- [ ] Output filtering policy defined (no leaking training data, PII, etc.).
- [ ] API endpoints hardened (rate limiting, auth, input validation).

## Operational
- [ ] Incident owner assigned per challenge.
- [ ] Escalation contacts listed (Andrew for governance, Christopher for technical).
- [ ] Backup/rollback artifact available and tested.
- [ ] Competition-specific data handling rules checked and documented.

## Decision Rule
When in doubt about data rights or privacy: **pause, log in risk-register.md, and ask** — don't silently proceed and don't silently refuse.
