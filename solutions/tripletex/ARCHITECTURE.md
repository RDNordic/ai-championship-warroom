# Tripletex Agent — Architecture (branch: tripletex/complex-multi-step-project)

## Level 1: High-Level Task Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 COMPETITION PLATFORM                         │
│  POST /solve                                                 │
│  IN:  {prompt, files[], tripletex_credentials}               │
│  OUT: {"status": "completed"}                                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    OUR SERVICE (FastAPI)                      │
│                                                              │
│  1. LLM CALL    — Sonnet reads prompt → JSON API steps       │
│  2. VALIDATE    — swagger.json schema check + auto-fix       │
│  3. EXECUTE     — sequential Tripletex API calls             │
│  4. SELF-CORRECT — on failure, retry with schema context     │
│                                                              │
│  Single path. No branching. Every task type goes through     │
│  the same pipeline.                                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   TRIPLETEX PROXY API                        │
│  REST API. Auth: Basic 0:{session_token}                     │
│  Responses wrapped in {"value": {...}} or {"values": [...]}  │
└─────────────────────────────────────────────────────────────┘
```

The platform sends a natural-language accounting task (7 languages).
We figure out the API calls and execute them.
The platform checks Tripletex state directly to score us.
We never return data — only `{"status": "completed"}`.

---

## Level 2: Module Map

```
┌──────────────────────────────────────────────────────────────┐
│ app.py                                                        │
│   IN:  HTTP POST /solve (SolveRequest)                        │
│   OUT: HTTP 200 {"status": "completed"}                       │
│   Creates SolverService at startup via build_default_service() │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ service.py — SolverService                                    │
│   IN:  SolveRequest + SolveRequestContext                     │
│   OUT: SolveResponse                                          │
│   Wires: LLMApiExecutor + TripletexClient + SolveEventLogger  │
│   Single path: prompt → executor → result                     │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│ llm_executor.py — LLMApiExecutor                              │
│   IN:  prompt, attachments, TripletexClient                   │
│   OUT: WorkflowResult                                         │
│   Core logic: LLM call → validate → execute → self-correct    │
│   Uses: ApiCallValidator, SchemaValidator, TripletexClient     │
└──────────┬───────────────────────────────────────────────────┘
           │
     ┌─────┼──────────────────┬──────────────────┐
     ▼     ▼                  ▼                  ▼
┌────────┐ ┌────────────────┐ ┌────────────────┐ ┌────────────┐
│endpoint│ │schema_validator│ │api_validator.py│ │client.py   │
│catalog │ │.py             │ │                │ │            │
│.py     │ │                │ │                │ │Tripletex   │
│        │ │SchemaValidator │ │ApiCallValidator│ │Client      │
│Parses  │ │                │ │                │ │            │
│swagger │ │Validates body  │ │Validates route │ │HTTP calls  │
│.json   │ │fields, types,  │ │exists in       │ │with auth   │
│→ text  │ │read-only.      │ │swagger catalog │ │+ logging   │
│for LLM │ │Auto-fixes.     │ │                │ │            │
└────────┘ └────────────────┘ └────────────────┘ └────────────┘

Supporting modules:
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐
│ config.py    │ │ models.py    │ │solve_logging │ │ runtime  │
│              │ │              │ │.py           │ │_context  │
│ AppSettings  │ │ SolveRequest │ │              │ │.py       │
│ loads env    │ │ SolveResponse│ │SolveEvent    │ │          │
│ vars         │ │ Attachment   │ │Logger →      │ │Context   │
│              │ │ File         │ │JSONL file    │ │vars for  │
│              │ │ Tripletex    │ │              │ │request   │
│              │ │ Credentials  │ │              │ │tracing   │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────┘

Source of truth:
┌──────────────────────────────────────────────────────────────┐
│ swagger.json (2MB, 490 paths, 1827 definitions)              │
│   Downloaded from https://tripletex.no/v2/swagger.json       │
│   Used by endpoint_catalog.py and schema_validator.py        │
│   NOT sent to LLM — parsed into focused text/models          │
└──────────────────────────────────────────────────────────────┘

Prompt files (editable independently of code):
┌──────────────────────────────────────────────────────────────┐
│ prompts/retry_correction.md — retry prompt template          │
│   Loaded by llm_executor.py when a step fails                │
│   Contains: error, schema context, saved vars, fixes applied │
└──────────────────────────────────────────────────────────────┘

Archived (kept for reference, not wired):
┌──────────────────────────────────────────────────────────────┐
│ _archive/endpoint_catalog_handcrafted.py                     │
│ planner.py, task_plan.py, workflows/live.py                  │
│ workflows/registry.py, workflows/stub.py                     │
│ api_call_planner.py, api_call_plan.py                        │
│ prompts/planner_system.md, prompts/planner_system.txt        │
└──────────────────────────────────────────────────────────────┘
```

---

## Level 3: Detailed Function-Level Flow

### 3.1 Entry Point: `app.py`

```
create_app()
  IN:  nothing (called at module load)
  OUT: FastAPI app

  1. load_local_env()         — reads .env file
  2. configure_logging()      — sets up logger
  3. build_default_service()  — creates SolverService
  4. Registers /health and /solve routes

POST /solve handler:
  IN:  SolveRequest (JSON body), HTTP headers
  OUT: SolveResponse {"status": "completed"}

  1. Extract trace_id from x-request-id header (or generate UUID)
  2. Build SolveRequestContext (trace_id, client_host, etc.)
  3. Call solver_service.solve(request, context)
  4. Return {"status": "completed"}
```

### 3.2 Orchestrator: `service.py`

```
build_default_service()
  IN:  nothing (reads AppSettings from env)
  OUT: SolverService

  1. Load AppSettings (ANTHROPIC_API_KEY, LLM_EXECUTOR_MODEL, etc.)
  2. Create LLMApiExecutor(api_key, model)
  3. Create SolveEventLogger(log_path)
  4. Return SolverService(executor, client_factory, event_logger)

SolverService.solve(request, context)
  IN:  SolveRequest, SolveRequestContext
  OUT: SolveResponse

  1. Record "received" event
  2. Bind runtime context (for per-request logging)
  3. Create TripletexClient from request credentials
  4. Call llm_executor.execute(prompt, attachments, client)
  5. Record "completed" or "failed" event
  6. Return SolveResponse
```

### 3.3 Core Engine: `llm_executor.py`

```
LLMApiExecutor.__init__(api_key, model)
  IN:  Anthropic API key, model name
  OUT: executor instance

  Creates:
  - anthropic.Anthropic client
  - ApiCallValidator (route-level checks)
  - SchemaValidator (body-level checks from swagger.json)

LLMApiExecutor.execute(prompt, attachments, tripletex_client)
  IN:  prompt (str), attachments (list[AttachmentFile]), TripletexClient
  OUT: WorkflowResult {name, completed, intended_operations, resource_ids, details}

  STEP 1 — Build system prompt
    _build_system_prompt()
      IN:  nothing
      OUT: system prompt string
      Combines:
      - Endpoint catalog text (from swagger.json via catalog_as_text())
      - Recipes (common multi-step patterns)
      - Rules (nested refs, date formats, multilingual)
      - Today's date

  STEP 2 — Call LLM
    _call_llm_for_steps(messages, system_prompt)
      IN:  messages list, system prompt
      OUT: list[dict] (parsed API steps) or None
      1. Call Claude Sonnet (max_tokens=4096)
      2. Parse response via _parse_steps()

  STEP 3 — Route validation
    ApiCallValidator.validate_plan(steps)
      IN:  list of step dicts
      OUT: PlanValidationResult {valid, errors}
      Checks each step:
      - Method is GET/POST/PUT/DELETE
      - Normalized path exists in swagger catalog

  STEP 4 — Execute with body validation
    _execute_steps(steps, client, saved_vars, ...)
      IN:  steps, TripletexClient, mutable state dicts
      OUT: None (success) or failure context dict

      For each step:
        a. _substitute_vars(path/params/body, saved_vars)
           IN:  template with $var_name refs, saved_vars dict
           OUT: resolved values

        b. SchemaValidator.validate_and_clean(method, path, json_body)
           IN:  method, path, json_body dict
           OUT: SchemaValidationResult {cleaned_body, valid, errors,
                                        fixes_applied, fields_removed}
           Auto-fixes:
           - Removes read-only fields
           - Removes unknown fields
           - Coerces flat int refs to {"id": X}
           - Coerces string/number/boolean types

        c. tripletex_client.request(method, path, params, json_body)
           IN:  HTTP method, path, query params, JSON body
           OUT: API response dict
           On 4xx/5xx: raises TripletexAPIError → step fails

        d. _resolve_value(response, field_path) for save_response_fields_as
           IN:  response dict, dot-path like "value.id"
           OUT: extracted value (saved to saved_vars for next steps)

  STEP 5 — Self-correction on failure
    _request_correction(messages, system_prompt, failure_context, ...)
      IN:  original messages, system prompt, failure details
      OUT: list[dict] (corrected steps) or None

      1. Load prompts/retry_correction.md template
      2. Get endpoint schema via SchemaValidator.describe_endpoint_fields()
      3. Fill template with:
         - Error from Tripletex
         - Completed steps so far
         - Saved variables
         - Auto-fixes applied (so LLM doesn't re-introduce them)
         - Fields removed by validator
         - Endpoint schema (required + optional fields)
         - Remaining steps from original plan
      4. Call LLM with enriched context
      5. Parse corrected steps
      6. Re-execute via _execute_steps()
```

### 3.4 Swagger-Based Validation: `endpoint_catalog.py`

```
build_catalog(swagger)
  IN:  swagger dict (or loads from swagger.json)
  OUT: list[dict] — structured endpoint entries

  1. Iterate all paths in swagger.json
  2. Filter to _RELEVANT_PATHS whitelist (93 endpoints)
  3. For each endpoint extract:
     - method, path, description
     - query params (from "in": "query" parameters)
     - body fields (resolved from $ref → definitions)
       - required vs optional
       - read-only excluded
       - type annotations
       - entity ref hints

catalog_as_text(swagger)
  IN:  swagger dict (optional)
  OUT: string (~12K tokens, ~1090 lines)

  Renders the catalog as human-readable text for the LLM system prompt.
  Grouped by resource (CUSTOMER, EMPLOYEE, INVOICE, etc.)
```

### 3.5 Body Validation: `schema_validator.py`

```
SchemaValidator.__init__(swagger)
  IN:  swagger dict (or loads from swagger.json)
  OUT: validator with 152 endpoint schemas

  Builds _EndpointSchema for every POST/PUT path:
  - Parses field specs: name, type, required, read_only, is_ref

SchemaValidator.validate_and_clean(method, path, json_body)
  IN:  method (str), path (str), json_body (dict)
  OUT: SchemaValidationResult

  Layer 1: Remove read-only fields         → fixes_applied
  Layer 2: Remove unknown fields           → fixes_applied
  Layer 3: Check required fields present   → errors
  Layer 4: Type coercion                   → fixes_applied or errors
           string ↔ number, int → {"id": int}, bool coercion

SchemaValidator.describe_endpoint_fields(method, path)
  IN:  method (str), path (str)
  OUT: human-readable field list (for retry prompt)
  Lists required and optional writable fields with types.
```

### 3.6 HTTP Client: `client.py`

```
TripletexClient.__init__(base_url, session_token, timeout=20s)
  Auth header: Basic base64("0:{session_token}")

TripletexClient.request(method, path, params, json_body, expected_status)
  IN:  HTTP method, path, query params, JSON body, expected status codes
  OUT: parsed response dict
  1. Send HTTP request via httpx
  2. Decode response (JSON or text)
  3. Record call to JSONL event log (via runtime context)
  4. If status not in expected_status → raise TripletexAPIError

TripletexClient.unwrap_value(payload) → payload["value"]
TripletexClient.unwrap_values(payload) → payload["values"]
```

### 3.7 Config: `config.py`

```
AppSettings.load()
  IN:  environment variables (+ .env file)
  OUT: AppSettings dataclass

  Key settings:
  - ANTHROPIC_API_KEY          — required
  - LLM_EXECUTOR_MODEL         — default: claude-sonnet-4-6
  - SOLVE_EVENT_LOG_PATH        — default: logs/solve-events.jsonl
  - TRIPLETEX_BASE_URL          — for local testing only
  - TRIPLETEX_SESSION_TOKEN     — for local testing only
  - HOST / PORT / LOG_LEVEL     — server config
```

---

## Defense Layers Against Bad API Calls

```
LLM generates JSON steps
      │
      ▼
LAYER 0: JSON parsing (_parse_steps)
  ✅ Valid JSON array?
      │
      ▼
LAYER 1: Route validation (ApiCallValidator)
  ✅ Method is GET/POST/PUT/DELETE?
  ✅ Path exists in swagger catalog?
      │
      ▼
LAYER 2: Body validation (SchemaValidator) — per step, before sending
  ✅ Auto-remove read-only fields
  ✅ Auto-remove unknown fields
  ✅ Auto-coerce flat refs → {"id": X}
  ✅ Auto-coerce types (str↔num, bool)
  ⚠️ Flag missing required fields
      │
      ▼
LAYER 3: Execute against Tripletex
  If 4xx → load retry_correction.md prompt with:
           error, schema, fixes applied, saved vars
         → one LLM retry with full context
```

---

## Data Flow Summary

```
prompt (str, 7 languages)
  → LLM system prompt (endpoint catalog ~12K tokens + recipes + rules)
  → Claude Sonnet → JSON array of steps
  → per step: substitute $vars → validate body → clean body → HTTP call
  → chain response IDs via save_response_fields_as
  → on failure: retry with schema context
  → WorkflowResult → {"status": "completed"}
```
