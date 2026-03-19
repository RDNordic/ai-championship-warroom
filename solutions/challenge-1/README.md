# Challenge 1 — Tripletex: AI Accounting Agent

**Sponsor:** Tripletex
**Status:** In progress
**Owner:** TBD

---

## What We're Building

A publicly accessible HTTPS `/solve` endpoint that:

1. Receives an accounting task prompt (7 languages: nb, en, es, pt, nn, de, fr)
2. Optionally receives base64-encoded PDF/image attachments
3. Gets fresh Tripletex credentials (proxy URL + session token) per submission
4. Uses an LLM to interpret the task and make Tripletex REST API calls
5. Returns `{"status": "completed"}` when done

---

## Endpoint Contract

**Method:** POST `/solve`
**Timeout:** 300 seconds (5 minutes)
**Response:** `{"status": "completed"}` with HTTP 200

### Request Shape

```json
{
  "prompt": "Opprett en ansatt med navn Ola Nordmann, ola@example.org.",
  "files": [
    {
      "filename": "faktura.pdf",
      "content_base64": "JVBERi0xLjQg...",
      "mime_type": "application/pdf"
    }
  ],
  "tripletex_credentials": {
    "base_url": "https://tx-proxy.ainm.no/v2",
    "session_token": "abc123..."
  }
}
```

### Tripletex Auth

Basic Auth on every API call:
- Username: `0` (zero)
- Password: `session_token` from request

```python
auth = ("0", session_token)
requests.get(f"{base_url}/employee", auth=auth)
```

---

## Scoring System

| Layer | Detail |
|---|---|
| **Correctness** | Field-by-field check after agent finishes. Partial credit given. Normalized 0–1. |
| **Tier multiplier** | ×1 simple / ×2 medium / ×3 complex multi-step |
| **Efficiency bonus** | Unlocks only on **perfect** correctness. Penalises 4xx errors + excess API calls. Can double tier score. |

**Score ceiling:** Tier 3 + perfect + best efficiency = **6.0 per task**
**Total score:** Sum of best scores across all 30 task types
**Best score kept:** Bad runs never lower your score
**Efficiency benchmarks:** Recalculated every 12h — others improving can lower your score retroactively

### Efficiency Rules (Critical)
- Every **4xx error** reduces the bonus — no trial-and-error calling
- Every **extra GET call** reduces the bonus — don't re-fetch what you already created
- Plan the full API sequence before making the first call
- Validate inputs locally before sending

---

## The 30 Task Types (7 Categories)

| Category | Example tasks |
|---|---|
| **Employees** | Create employee, set roles, update contact info |
| **Customers & Products** | Register customer, create product |
| **Invoicing** | Create invoice, register payment, issue credit note |
| **Travel Expenses** | Register or delete travel expense reports |
| **Projects** | Create project linked to customer |
| **Corrections** | Delete or reverse incorrect entries |
| **Departments** | Create department, enable accounting modules |

Each task has 56 variants (7 languages × 8 datasets). You'll rarely see the same prompt twice.

---

## Key Tripletex API Endpoints

| Endpoint | Methods | Use |
|---|---|---|
| `/employee` | GET, POST, PUT | Employees |
| `/customer` | GET, POST, PUT | Customers |
| `/product` | GET, POST | Products |
| `/invoice` | GET, POST | Invoices |
| `/order` | GET, POST | Orders |
| `/travelExpense` | GET, POST, PUT, DELETE | Travel expenses |
| `/project` | GET, POST | Projects |
| `/department` | GET, POST | Departments |
| `/ledger/voucher` | GET, POST, DELETE | Vouchers |

Tips:
- `?fields=id,firstName,lastName` — select only what you need
- `?from=0&count=100` — pagination
- List responses: `{"fullResultSize": N, "values": [...]}`
- POST response has the new entity: `resp.json()["value"]["id"]` — don't re-fetch it

---

## Common Task Patterns

| Pattern | API Flow |
|---|---|
| Create single entity | `POST /employee` |
| Create with linking | `GET /customer` → `POST /order` → `POST /invoice` |
| Modify existing | `GET /customer` → `PUT /customer/{id}` |
| Delete/reverse | `GET /travelExpense` → `DELETE /travelExpense/{id}` |
| Multi-step setup | `POST /customer` → `POST /invoice` → `POST /payment` |

---

## Common Errors

| Error | Fix |
|---|---|
| 401 Unauthorized | Use Basic Auth: username=`0`, password=session token |
| 404 Not Found | Check endpoint path against Tripletex v2 docs |
| 422 Validation | Read error message — it names the missing field |
| Empty `values` | Broaden search params |
| Timeout (5 min) | Reduce unnecessary API calls |

---

## Agent Architecture

```
Prompt (multilingual)
  → LLM: detect language + classify task type
  → LLM: extract entities, field values, relationships
  → LLM: generate ordered API call plan (no errors, minimal calls)
  → Execute plan
  → [If files: decode base64, extract data via LLM vision]
  → Return {"status": "completed"}
```

**LLM:** Claude API (handles all 7 languages natively)
**Hosting:** FastAPI + cloudflared tunnel or GCP endpoint

---

## Infrastructure

### Run Locally

```bash
pip install fastapi uvicorn requests anthropic
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Expose via HTTPS

```bash
npx cloudflared tunnel --url http://localhost:8000
```

### Submit Endpoint

Register at: `https://app.ainm.no/submit/tripletex`

---

## Sandbox

- URL: `https://kkpqfuj-amager.tripletex.dev`
- Claim at: Tripletex submission page on `app.ainm.no`
- Token expires: March 31, 2026
- One sandbox per team (all members share it)
- Use it to explore the data model before writing agent logic

---

## Strategy

1. **Breadth first** — 20/30 task types beats perfecting 10. Get baseline coverage.
2. **Tier 3 tasks win competitions** — 6.0 ceiling vs 2.0 for Tier 1. Prioritise after baseline.
3. **Zero errors = efficiency bonus unlocked** — plan before calling, validate before sending.
4. **Sandbox first** — understand the data model before writing the agent.
5. **Rate limit: 10 concurrent, unlimited/day** — can hammer submissions without concern.

---

## Rate Limits

| | Value |
|---|---|
| Concurrent submissions | 10 |
| Per day | Unlimited |

---

## Open Questions

- [ ] Who owns this challenge (keeps endpoint running throughout competition)?
- [ ] Hosting: cloudflared on local machine vs GCP?
- [ ] Claim sandbox at `app.ainm.no` immediately
