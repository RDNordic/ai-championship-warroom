# Lessons Learned from Pre-Competition Trial

Date: 2026-03-01 (NorgesGruppen simulation trial, rank ~70/317)

## 1. Version Control Discipline

**Problem:** The code that produced the best score was committed, but subsequent uncommitted iterative changes never exceeded it. When trying to reproduce the high score, the original code could not be easily recovered.

**Rules for competition day:**
- **Commit before every run.** Use descriptive messages: `challenge-1: score=110, added lookahead`.
- **Tag high-water marks.** After any new best score: `git tag challenge-1-best-110 HEAD`.
- **Never iterate on uncommitted code.** If a change doesn't improve the score, `git checkout -- <file>` to revert before trying the next idea.
- **One change per commit.** Makes it easy to bisect which change helped vs. hurt.

## 2. Score Regression from Over-Engineering

**Key insight:** The simplest working version outperformed all the "smarter" follow-on versions. Score went high → collapsed → slowly recovered but never exceeded the simple baseline.

**Rules for competition day:**
- Measure before and after every change. If score drops, revert immediately.
- Complexity is not free. Each added heuristic has interaction effects with previous ones.
- Scoring variance on real-time platforms is ~10-15 points between identical runs. Don't chase noise.
- Simple heuristics (greedy assignment, BFS) beat over-engineered approaches.

## 3. What Generally Helps vs. Hurts

### Helps
- **BFS-based pathfinding** with distance caching: correct distances through obstacles, not manhattan.
- **Lookahead planning**: planning multi-step sequences to optimise total route cost.
- **Deterministic seeds** (`random.seed(42)`): eliminates variance from random nudge/tiebreaking, makes A/B testing reliable.

### Hurts
- **End-game special-case logic**: usually over-fitted and adds overhead.
- **Reduced cooldown/penalty values**: the original conservative values often score better.
- **Pre-positioning during idle**: bots moving toward things they can't act on wastes rounds.

## 4. Competition Day Protocol

1. **Start from a clean baseline commit.**
2. **Run 3 trials** to establish baseline variance range.
3. **Make ONE change at a time.** Commit with score in message.
4. **Run 3 trials** after each change. Compare median, not best.
5. **Revert if median drops.** Don't rationalize regressions.
6. **Tag new high-water marks** immediately.
7. **Time-box tuning.** If no improvement in 30 min, move to next challenge.

## 5. Scoring Normalization (NMiAI 2026)

The competition normalizes each task score to 0–100 by dividing by the highest score in that task across all teams, then averages the three task scores equally (33.33% each). **A zero on any task is catastrophic.** Get a baseline submission running on all three tasks before optimizing any single one.
