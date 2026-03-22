# Tripletex Submission Checklist

## Purpose

Use this checklist before every public `/solve` submission so we do not confuse API bugs, planner bugs, and deployment bugs.

## Gate

1. Verify sandbox credentials still work.
   - Run: `python scripts/smoke_read_only.py`
2. Start the live worker and tunnel under one foreground supervisor.
   - Run: `.\.venv\Scripts\python.exe scripts\run_public_endpoint.py`
   - Keep that process open during the full submission window.
   - Use the URL written to `logs/public-endpoint-state.json`. Do not reuse an older quick-tunnel hostname.
3. Validate the raw API behavior for the workflow we are about to trust.
   - Use the sandbox directly when needed to confirm required fields, lookup params, and write semantics.
4. Validate the workflow through the local runner.
   - Run: `./.venv/bin/python scripts/run_prompt.py --execute "<prompt>"`
5. Validate the full `/solve` HTTP contract with sandbox credentials.
   - Send a real `POST /solve` request to the running public endpoint.
   - Use a sandbox `base_url` and `session_token` in `tripletex_credentials`.
   - Confirm the response is HTTP 200 with `{"status":"completed"}`.
6. Verify the created or updated Tripletex record manually.
   - Confirm the exact fields, not only that some entity exists.
7. Check logs before submitting to the competition.
   - Confirm prompt, parsed plan, selected workflow, API sequence, and absence of 4xx errors.
8. Submit only after the exact scenario has passed all earlier gates.

## Scenario Rules

- Use unique names, emails, invoice comments, product numbers, and project names in sandbox validations.
- Test both Norwegian and English phrasings for each supported workflow.
- Cover one fresh-account style scenario that creates all needed prerequisites itself.
- Cover one existing-entity scenario that relies on search or lookup.
- Treat any `StubWorkflow` hit as a failed gate, even if `/solve` returned 200.
- Prefer API-only prompt handling work before attachments. PDF and CSV extraction stay lower priority until the prompt-to-API path is stable.

## Step 3 Explained

Step 3 is the most important rehearsal before a real submission.

We are not only testing a Tripletex API call. We are replaying the competition contract against our own service:

```json
{
  "prompt": "Create employee named Ola Nordmann, ola@example.org",
  "files": [],
  "tripletex_credentials": {
    "base_url": "https://.../v2",
    "session_token": "..."
  }
}
```

This works because our service is built to accept per-request Tripletex credentials:

- [app.py](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/app.py) receives the HTTP request.
- [models.py](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/models.py) validates the payload shape.
- [service.py](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/service.py) passes `tripletex_credentials` into the solver.
- [client.py](/home/benoit/Documents/Tripletex-KO/ai-championship-warroom/solutions/tripletex/src/tripletex_agent/client.py) uses those credentials for Basic auth with username `0`.

So we can send a competition-style request ourselves, but fill it with sandbox credentials. That gives us an end-to-end test of:

- public HTTPS reachability
- request validation
- planner execution
- workflow selection
- Tripletex authentication using request-supplied credentials
- correct `{"status":"completed"}` response shape

What this proves:

- the `/solve` contract is wired correctly
- the current workflow can run with the provided credentials
- the deployment path is working
- the current quick-tunnel URL is alive right now, not just in an older handoff note

What this does not prove:

- that the same task will succeed in a brand-new competition account
- that the scorer will award full points
- that we are not relying on old persistent sandbox data

## Current Supported Matrix

- Customer create
- Product create
- Employee create
- Department create
- Project create linked to existing customer
- Invoice create
- Invoice payment
- Invoice credit note

## Current Unsupported Or Partial Areas

- Travel expenses
- Corrections
- Module-activation workflows
- PDF and CSV extraction
- Broader conversational prompt coverage across all prompt variants

## Submission Notes

- If it fails in sandbox, assume it will fail in `/solve`.
- If it works in sandbox, treat it as high confidence, not a guarantee.
- Fresh competition accounts are stricter than the persistent sandbox because missing prerequisites are exposed immediately.
- A dead quick tunnel can produce a pure deployment failure with no useful task logs. Always regenerate and re-check the public URL right before submitting.
