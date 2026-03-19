# Astar Island — Documentation Index

All documentation sourced from the `nmiai` MCP server at `https://mcp-docs.ainm.no/mcp`.
Captured: 2026-03-19.

## Raw Pages

| File | Source URI | Why it matters |
|------|-----------|----------------|
| `raw/overview.md` | `challenge://astar-island/overview` | High-level concept, key terms, round lifecycle summary. Start here. |
| `raw/mechanics.md` | `challenge://astar-island/mechanics` | Full simulation rules — terrain types, all 5 yearly phases (growth/conflict/trade/winter/environment), settlement properties. Required to understand what drives the world. |
| `raw/endpoint.md` | `challenge://astar-island/endpoint` | Complete API reference — all 8 endpoints, full request/response schemas, field types, error codes, auth methods. The ground truth for building code. |
| `raw/scoring.md` | `challenge://astar-island/scoring` | Scoring formula (entropy-weighted KL divergence), ground truth generation, per-round averaging, leaderboard weighting, the 0.0-probability pitfall. |
| `raw/quickstart.md` | `challenge://astar-island/quickstart` | Auth setup, step-by-step code examples, uniform baseline, 0.01 floor warning. |

## Synthesised Files

| File | Contents |
|------|---------|
| `spec-extracted.md` | All operational facts: endpoints, schemas, constraints, limits, formulas — no prose, no fluff |
| `examples.md` | All exact JSON payloads, response samples, and code from the docs |
| `open-questions.md` | Contradictions, ambiguities, and inferred behaviour |
