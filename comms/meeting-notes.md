# Communication Notes

## Meeting Log

### 2026-03-13 — Patrick Meeting
**Attendees:** John, Patrick
**Status:** In progress

**Fresh intel from web search (2026-03-13):**
- Tripletex (Norway's largest cloud accounting platform) is a **platinum partner AND case provider** — one challenge will be accounting/finance related (NLP/ML on invoices, classification, etc.)
- NorgesGruppen Data = Grocery Bot / retail (already in pre-comp)
- DNV = likely CV or ML (maritime, energy, safety domain)
- Google providing Gen AI infrastructure for participants
- Challenge details NOT released until kickoff March 19 at 18:00
- Communication: Signal for team, John keeps GitHub hub updated

**Current Grocery Bot Scores (as of 2026-03-13):**
| Difficulty | Best Score | Status | Gap vs Leaderboard |
|-----------|-----------|--------|-------------------|
| Easy | 137 | Inactive | Unknown |
| Medium | 118 | Frozen | Unknown |
| Hard | 99 | Active (volatile) | -144 vs ref (243) |
| Expert | 93 | Active (volatile) | -126 vs ref (219) |
| Nightmare | 193 | Stable | Unknown |
| **Total** | **640** | | |

**DEADLINE: March 16 at 03:00 CET — 3 days away**
**CHAMPIONSHIP KICKOFF: March 19 at 18:00**

**Grocery Bot — CLOSED**
- Final rank: ~70th out of 317 teams. Happy with result.
- Purpose achieved: team is now familiar with the WebSocket platform and mechanics.
- No further tuning. All energy → championship prep.

**Task Division Discussion:**
- Chris = solver lead across all 3 challenges (primary technical driver)
- KO = infra owner + GPU box (RTX 5080); owns deployment pipeline
- Patrick = governance + coordination; support on NLP challenge
- Andrew = PM + compliance sign-off
- John = CPU/NPU box (96GB RAM); data wrangling, tabular ML, comms hub

**Hardware split:**
- GPU-heavy (LLM inference, CV, fine-tuning) → KO
- Tabular ML, large-context, data processing → John
- Cloud burst → Google infra (confirm before March 19)

**Interview questions NOT yet answered (resume next session):**
- Full availability March 19–22 per team member
- Is Signal group already set up?
- Has deployment pipeline (local → public endpoint) been tested?
- Chris's read on carrying 3 challenges — does he need support?

---

## Prep Checklist
- [x] Grocery Bot closed — rank ~70/317, platform familiar
- [x] Team members and hardware identified
- [x] Challenge hypotheses documented (comms/intel-sources.md)
- [x] `/session-handoff` and `/btw` commands created
- [x] next-steps.md cleaned and updated
- [ ] Signal group confirmed with all 4 members
- [ ] Google cloud access confirmed
- [ ] KO: Ollama + Qwen2.5:27B installed and tested
- [ ] FastAPI scaffold + ngrok deployment pipeline tested end-to-end
- [ ] All 4 members with GitHub push/PR access confirmed

## Action Items
1. **John** — share `comms/intel-sources.md` and updated `next-steps.md` with team on Signal
2. **KO** — confirm RTX 5080 has Ollama installed; test Qwen2.5:27B inference speed
3. **Everyone** — check app.ainm.no for Google cloud access details
4. **Next session** — finish interview: availability, Signal status, deployment pipeline test
