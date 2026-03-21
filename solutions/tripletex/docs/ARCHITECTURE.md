# Architecture

## Guiding principle

The LLM is a semantic interpreter, not an API agent. It reads the prompt and produces
a structured `TaskPlan`. Deterministic Python code executes that plan against the
Tripletex API. This separation is what makes the system scorable — every API call is
intentional, validated, and traceable.

## Request lifecycle

```
POST /solve
  │
  ├─ 1. Parse and validate request
  │     Extract: prompt, files, base_url, session_token
  │
  ├─ 2. Attachment normalisation (if files present)
  │     Decode base64 → extract structured facts (PDF/CSV/image)
  │     Facts are merged into prompt context for the planner
  │
  ├─ 3. Planner (LLM call, temp=0)
  │     Input:  prompt + attachment facts + domain context block
  │     Output: TaskPlan (structured JSON)
  │
  ├─ 4. Workflow selection
  │     TaskPlan.task_family + TaskPlan.operation → workflow handler
  │
  ├─ 5. Workflow execution
  │     Deterministic API call sequence
  │     Each step validates before writing
  │     IDs from responses reused — no re-fetching what we just created
  │
  ├─ 6. Validation-with-retry (if 422 or schema mismatch)
  │     Feed exact error + schema back to LLM
  │     Max 2 retries — if not resolved, fail fast
  │
  ├─ 7. Postcondition check
  │     Verify the requested outcome was achieved
  │     Not just "entity created" but "entity created AND sent" if that was asked
  │
  ├─ 8. Trace logging
  │     Log: prompt, plan, API sequence, status codes, postcondition result
  │
  └─ 9. Return {"status": "completed"} HTTP 200
```

## The three prompt-handling layers

### Layer 1 — Domain context block (static, always in system prompt)

A ~2,000 token document injected into every planner call. Contains:
- The three invoice types and when to use each
- Voucher lifecycle (draft → inbox → ledger)
- Travel expense state machine
- Norwegian accounting terminology
- Invoice line item rules (description vs productLookup)
- Multilingual action semantics (send/approve/deliver in all 7 languages)
- Disambiguation rules for write operations

See `docs/TRIPLETEX_DOMAIN.md` for the full text of this block.

### Layer 2 — Retrieved endpoint schemas (dynamic, per-request)

Not implemented yet in the current codebase but the target architecture.
The full OpenAPI spec (800 endpoints, ~75k tokens compact) cannot be injected whole.
Instead, a pre-built index of compact endpoint summaries is searched semantically
and the top 3–5 matching endpoint schemas are injected alongside the prompt.

Pre-processing (offline, one-time):
- For each endpoint: extract path, method, operationId, summary, parameters, and
  top-level request body fields (one level deep, no recursive $ref resolution)
- Embed each entry with a multilingual embedding model
- Store in a vector index (pgvector, Qdrant, or flat FAISS file for hackathon)

Runtime retrieval:
- Stage 1: family classifier narrows search to 1–3 API families
- Stage 2: embedding search within those families, top-k=5
- Inject the 5 compact schemas into the planner prompt

For the hackathon, a simpler approach is acceptable: a hardcoded map of
task_family → relevant endpoint schemas, loaded from a JSON file. This avoids
the need for a vector store while still keeping prompt size bounded.

### Layer 3 — Clarification (disabled for hackathon)

When `allow_clarification=False` (the hackathon default):
- On ambiguous write operations, prefer the safer interpretation
- Never ask questions — always produce a plan
- Prefer GET over write if truly ambiguous

When `allow_clarification=True` (future production mode):
- Ask exactly one clarifying question before generating a call on ambiguous writes

Controlled by a single flag in `build_system_prompt(allow_clarification: bool)`.

## TaskPlan schema

```python
class EntityToCreate(BaseModel):
    entity_type: str           # "customer", "invoice", "employee", etc.
    fields: dict               # Extracted field values

class EntityToFind(BaseModel):
    entity_type: str
    lookup_fields: dict        # Fields to search by

class CompletionCheck(BaseModel):
    kind: str                  # "created", "sent_to_customer", "approved", "delivered"
    entity_type: str
    expected_fields: list[str]

class ActionSemantics(BaseModel):
    send_to_customer: bool | None
    approve: bool | None
    deliver: bool | None
    reverse: bool | None
    delete: bool | None

class TaskPlan(BaseModel):
    task_family: str           # "invoicing", "employees", "travel_expenses", etc.
    operation: str             # "create", "update", "delete", "unknown"
    entities_to_create: list[EntityToCreate]
    entities_to_find: list[EntityToFind]
    fields_to_set: dict
    links_between_entities: list[dict]
    attachment_facts: list[dict]
    completion_checks: list[CompletionCheck]
    action_semantics: ActionSemantics
    confidence: float          # 0.0–1.0
```

The `action_semantics` block is the critical addition over the current schema.
It must capture secondary actions explicitly so workflows don't have to re-infer
them from free text.

## Validation-with-retry

```python
def execute_with_retry(endpoint, payload, schema, max_retries=2):
    for attempt in range(max_retries + 1):
        response = client.call(endpoint, payload)
        
        if response.status_code in (200, 201):
            return response
        
        if response.status_code == 422:
            error_detail = response.json()
            
            # Diagnose: is this a missing schema context problem?
            if attempt < max_retries:
                # Build a targeted retry prompt:
                # - exact validation error
                # - relevant schema section
                # - previous payload
                # Ask LLM to fix ONLY the invalid part
                payload = llm_fix_payload(payload, error_detail, schema)
                continue
        
        # Non-422 or exhausted retries: fail fast
        raise WorkflowExecutionError(f"{response.status_code}: {response.text}")
```

Key rules:
- Retry prompt must include: exact error message, the schema section violated,
  and the previous payload. Not a vague "try again."
- Max 2 retries. If not resolved, the task plan is wrong — fail fast.
- Never retry a 4xx that is not 422 (wrong endpoint, wrong auth, etc.)
- Distinguish schema failure (retry) from semantic failure (re-plan or fail)

## Efficiency rules

These directly affect the scoring efficiency bonus:

- Never fetch an entity you just created — use the ID from the creation response
- Use `fields=id,name,...` to request only needed fields on GET calls
- Use batch endpoints (`/list`) when creating multiple entities of the same type
- Never mutate data unrelated to the prompt (the bank-account bootstrap is banned)
- The first write attempt must succeed — validate inputs locally before calling

## Attachment handling

Priority order:
1. PDF invoice/receipt → extract: amount, date, vendor, line items, VAT
2. CSV bank statement → extract: transactions as structured rows
3. Image → OCR if text content needed, otherwise describe

Approach:
- Extract only the minimum structured facts needed for the TaskPlan
- Feed extracted facts as additional context to the planner, not raw file content
- Do not dump entire file content into the prompt

## Logging

Every `/solve` request must emit structured events to `logs/solve-events.jsonl`:
- `received` — raw request (prompt, files present y/n, base_url)
- `planned` — the TaskPlan output
- `tripletex_call` — each API call (method, path, params, body, status, duration)
- `solved` — postcondition verification passed
- `failed` — error type and message

This log is the primary feedback loop. The `scripts/inspect_solve_logs.py` tool
mines it for prompt patterns, failure clusters, and efficiency analysis.
