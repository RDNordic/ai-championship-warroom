# /session-handoff

You are performing a session handoff. The goal is to capture all current working state so the next conversation can resume immediately without re-reading the codebase or re-establishing context.

Follow these steps in order:

## Step 1 — Gather current state

Read the following files to understand what has happened this session:
- `next-steps.md` — current task list and workstream status
- Any active `solutions/<challenge>/SESSION_HANDOFF.md` files for in-progress challenges
- Recent git log: run `git log --oneline -10` to see what was committed
- Any files modified this session (check IDE context and conversation history)

## Step 2 — Update next-steps.md

Edit `next-steps.md` to reflect the current state:
- Mark completed tasks as `[x]`
- Add any new tasks discovered this session
- Update "Current State" sections with latest scores, artifacts, or findings
- Add a dated entry at the top of the relevant workstream section summarising what changed

## Step 3 — Update CLAUDE.md if needed

Only update `CLAUDE.md` if this session revealed a new stable pattern, rule, or protocol that should apply to all future sessions. Examples:
- A new anti-pattern proven to cause regressions
- A new protocol adopted by the team
- A new tool or constraint confirmed

Do not add session-specific details to CLAUDE.md — only durable project-level rules.

## Step 4 — Write the handoff summary

Output a concise handoff block using this exact format:

---

## Session Handoff — [DATE] [TIME]

**What was worked on:**
[1-3 sentences]

**Current state:**
- [Key file or artifact]: [status]
- [Key file or artifact]: [status]

**Scores / metrics (if applicable):**
| Difficulty | Best Score | Status |
|-----------|-----------|--------|
[fill in only if scores changed]

**What to do next (top 3 priorities):**
1. [Most important next action with specific file/command]
2. [Second priority]
3. [Third priority]

**Do not do:**
- [Anything that was tried and reverted this session]

**Resume command:**
```
cd "c:/Users/John Brown/ai-championship-warroom"
# [any specific command to resume]
```

---

Keep the handoff under 30 lines. It should be copy-pasteable as the first message in a new session.
