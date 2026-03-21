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
│  Phase 1: TOOL CALLS  — Haiku queries swagger for schemas    │
│  Phase 2: GENERATION  — Sonnet produces JSON API steps       │
│  Phase 3: VALIDATE    — swagger schema check + auto-fix      │
│  Phase 4: EXECUTE     — sequential Tripletex API calls       │
│  Phase 5: SELF-CORRECT — on failure, Sonnet retries          │
│                                                              │
│  Single path. No branching. Every task type goes through     │
│  the same pipeline. Two models: Haiku (speed) + Sonnet       │
│  (precision).                                                │
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
│   Two-phase LLM: Haiku (tools) → Sonnet (generation)          │
│   Uses: SwaggerQueryService, SchemaValidator,                 │
│         ApiCallValidator, TripletexClient                     │
└──────────┬───────────────────────────────────────────────────┘
           │
     ┌─────┼────────────────┬──────────────────┬────────────────┐
     ▼     ▼                ▼                  ▼                ▼
┌────────┐ ┌──────────────┐ ┌────────────────┐ ┌──────────────┐ ┌──────────┐
│swagger │ │endpoint      │ │schema_validator│ │api_validator │ │client.py │
│_tools  │ │_catalog.py   │ │.py             │ │.py           │ │          │
│.py     │ │              │ │                │ │              │ │Tripletex │
│        │ │Parses        │ │SchemaValidator │ │ApiCall       │ │Client    │
│Swagger │ │swagger.json  │ │                │ │Validator     │ │          │
│Query   │ │→ compact     │ │Validates body  │ │              │ │HTTP calls│
│Service │ │index for     │ │fields, types,  │ │Validates     │ │with auth │
│        │ │system prompt │ │read-only.      │ │route exists  │ │+ logging │
│3 tools │ │+ full detail │ │Auto-fixes.     │ │in swagger    │ │          │
│for LLM │ │for validator │ │                │ │catalog       │ │          │
└────────┘ └──────────────┘ └────────────────┘ └──────────────┘ └──────────┘

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
│   Used by: endpoint_catalog.py (index), swagger_tools.py     │
│            (full queries), schema_validator.py (body checks)  │
│   NOT sent raw to LLM — queried on demand via tool calls     │
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

  1. Load AppSettings
  2. Create LLMApiExecutor(api_key, tool_model, executor_model)
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

### 3.3 Core Engine: `llm_executor.py` — Two-Phase LLM

```
LLMApiExecutor.__init__(api_key, tool_model, executor_model)
  IN:  Anthropic API key, Haiku model ID, Sonnet model ID
  OUT: executor instance

  Creates:
  - anthropic.Anthropic client (shared by both models)
  - ApiCallValidator (route-level checks)
  - SchemaValidator (body-level checks from swagger.json)
  - SwaggerQueryService (tool implementations)

LLMApiExecutor.execute(prompt, attachments, tripletex_client)
  IN:  prompt (str), attachments (list[AttachmentFile]), TripletexClient
  OUT: WorkflowResult {name, completed, intended_operations, resource_ids, details}

  STEP 1 — Build system prompt
    _build_system_prompt()
      IN:  nothing
      OUT: system prompt string (~4K tokens)
      Contains:
      - Compact endpoint index (~2K tokens: method + path + summary for 94 endpoints)
      - Recipes (concise multi-step patterns for common tasks)
      - Rules (nested refs, date formats, multilingual)
      - Today's date
      - Tool use instructions ("use 3-5 lookups max")

  STEP 2 — Build user content with inline attachments
    _build_user_content(prompt, attachments)
      IN:  prompt string, attachments list
      OUT: list of content blocks

      For each attachment:
      - PDF  → document content block (Claude reads natively)
      - Image (PNG/JPG/GIF/WEBP) → image content block
      - CSV/Text → decoded text block (capped at 10K chars)
      - Other → skipped with warning

  STEP 3 — Two-phase LLM call
    _call_llm_with_tools(messages, system_prompt)
      IN:  user messages, system prompt
      OUT: list[dict] (parsed API steps) or None

      PHASE 1 — Haiku does tool calling (fast, cheap):
        Loop (max 5 rounds):
          - Call Haiku with tools=[lookup_endpoint, search_endpoints, get_model_schema]
          - If Haiku calls tools → dispatch to SwaggerQueryService → collect results
          - If Haiku stops calling tools → break
        Collects all tool results as schema context text.
        Typical: 3-7 tool calls in 2-3 seconds.

      PHASE 2 — Sonnet generates steps (precise):
        - Builds a new message: original prompt + all tool results as context
        - Calls Sonnet WITHOUT tools (pure generation)
        - Sonnet sees full endpoint schemas and produces correct JSON steps
        - Parse via _parse_steps()

  STEP 4 — Route validation
    ApiCallValidator.validate_plan(steps)
      IN:  list of step dicts
      OUT: PlanValidationResult {valid, errors}

  STEP 5 — Execute with body validation
    _execute_steps(steps, client, saved_vars, ...)
      IN:  steps, TripletexClient, mutable state dicts
      OUT: None (success) or failure context dict

      For each step:
        a. _substitute_vars(path/params/body, saved_vars)
        b. SchemaValidator.validate_and_clean(method, path, json_body)
           Auto-fixes: remove read-only, remove unknown, coerce refs/types
        c. tripletex_client.request(method, path, params, json_body)
        d. _resolve_value(response, field_path) → save to saved_vars

  STEP 6 — Self-correction on failure (Sonnet)
    _request_correction(...)
      IN:  failure context (error, schema, fixes, saved vars)
      OUT: corrected steps or None

      1. Load prompts/retry_correction.md template
      2. Fill with: Tripletex error, endpoint schema, auto-fixes applied,
         fields removed, saved variables, remaining steps
      3. Call Sonnet (no tools, direct generation)
      4. Parse corrected steps → re-execute via _execute_steps()
```

### 3.4 Swagger Tool Service: `swagger_tools.py`

```
SwaggerQueryService.__init__(swagger)
  IN:  swagger dict (or loads from swagger.json)
  OUT: service with full swagger spec in memory

3 tools (called by Haiku during Phase 1):

  lookup_endpoint(method, path)
    IN:  "POST", "/invoice"
    OUT: Full schema: summary, required/optional query params,
         body fields with types/required/read-only, ref hints
    Example output: {method, path, summary, query_params: [{name, required, type}],
                     body_schema: {required_fields, optional_writable_fields,
                                   read_only_fields_do_not_send}}

  search_endpoints(keyword)
    IN:  "credit note"
    OUT: list of {method, path, summary} (max 20 results)
    Searches both path and summary text.

  get_model_schema(model_name)
    IN:  "Posting"
    OUT: Full model: required_field_names, required_fields (with types),
         optional_writable_fields, read_only_fields_do_not_send
    Used for nested objects (Posting, OrderLine, Order, etc.)

SWAGGER_TOOLS: list of tool definitions for Anthropic API
  Defines the input_schema for each tool (JSON Schema format).
```

### 3.5 Endpoint Catalog: `endpoint_catalog.py`

```
build_catalog(swagger)
  IN:  swagger dict (or loads from swagger.json)
  OUT: list[dict] — structured endpoint entries (94 endpoints)
  Filters to _RELEVANT_PATHS whitelist.
  Extracts: method, path, description, required/optional params and fields.

catalog_as_text(swagger)
  IN:  swagger dict (optional)
  OUT: string (~12K tokens) — full detail for validator tests

catalog_index_text(swagger)
  IN:  swagger dict (optional)
  OUT: string (~2K tokens) — compact index for system prompt
  Format: "METHOD  /path                          One-line summary"
  Gives the LLM awareness of ALL endpoints without field details.
  The LLM uses lookup_endpoint() tool for field-level info.

ENDPOINT_CATALOG: pre-built list for the ApiCallValidator.
```

### 3.6 Body Validation: `schema_validator.py`

```
SchemaValidator.__init__(swagger)
  IN:  swagger dict (or loads from swagger.json)
  OUT: validator with 152 endpoint schemas

SchemaValidator.validate_and_clean(method, path, json_body)
  IN:  method (str), path (str), json_body (dict)
  OUT: SchemaValidationResult {cleaned_body, valid, errors,
                                fixes_applied, fields_removed}

  Layer 1: Remove read-only fields         → fixes_applied
  Layer 2: Remove unknown fields           → fixes_applied
  Layer 3: Check required fields present   → errors
  Layer 4: Type coercion                   → fixes_applied or errors
           string ↔ number, int → {"id": int}, bool coercion

SchemaValidator.describe_endpoint_fields(method, path)
  IN:  method (str), path (str)
  OUT: human-readable field list (for retry prompt)
```

### 3.7 HTTP Client: `client.py`

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

### 3.8 Config: `config.py`

```
AppSettings.load()
  IN:  environment variables (+ .env file)
  OUT: AppSettings dataclass

  Key settings:
  - ANTHROPIC_API_KEY          — required
  - LLM_TOOL_MODEL             — default: claude-haiku-4-5-20251001
  - LLM_EXECUTOR_MODEL         — default: claude-sonnet-4-6
  - SOLVE_EVENT_LOG_PATH       — default: logs/solve-events.jsonl
  - TRIPLETEX_BASE_URL         — for local testing only
  - TRIPLETEX_SESSION_TOKEN    — for local testing only
  - HOST / PORT / LOG_LEVEL    — server config
```

---

## Two-Phase LLM Architecture

```
┌─────────────────────────────────┐    ┌──────────────────────────────────┐
│  PHASE 1: Haiku (tool calling)  │    │  PHASE 2: Sonnet (generation)    │
│                                 │    │                                  │
│  Sees: prompt + endpoint index  │    │  Sees: prompt + full schemas     │
│  Does: calls lookup_endpoint()  │    │        from all tool results     │
│        calls get_model_schema() │    │  Does: generates final JSON      │
│        3-7 tool calls           │───▶│        steps with correct        │
│  Time: ~2-3 seconds             │    │        field names + types       │
│  Cost: cheap                    │    │  Time: ~3-5 seconds              │
│                                 │    │  Cost: moderate                  │
│  WHY: fast schema discovery,    │    │  WHY: precise structured output, │
│       knows what to look up     │    │       follows schemas exactly    │
└─────────────────────────────────┘    └──────────────────────────────────┘
```

---

## Defense Layers Against Bad API Calls

```
Sonnet generates JSON steps (with full schema context from Haiku's lookups)
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
           error, endpoint schema, fixes applied, saved vars
         → one Sonnet retry with full context
```

---

## Attachment Handling

```
Attachment type       Strategy                              Token cost
─────────────────────────────────────────────────────────────────────────
PDF                   document content block (Claude vision) Higher (vision)
Image (PNG/JPG/etc)   image content block (Claude vision)    Higher (vision)
CSV / plain text      Decoded to text, included in prompt    Minimal
Other                 Skipped with warning                   None
```

Attachments are placed BEFORE the prompt text so the LLM sees the data
first, then the instruction. PDFs and images are read natively by Claude.

---

## Data Flow Summary

```
prompt (str, 7 languages) + attachments (PDF/image/CSV)
  → System prompt: compact endpoint index (~2K tokens) + recipes + rules
  → Phase 1 [Haiku]: tool calls → lookup_endpoint / get_model_schema
  → Phase 2 [Sonnet]: prompt + full schema context → JSON API steps
  → Per step: substitute $vars → validate body (swagger) → auto-fix → HTTP call
  → Chain response IDs via save_response_fields_as
  → On failure: Sonnet retry with error + schema context
  → WorkflowResult → {"status": "completed"}
```
