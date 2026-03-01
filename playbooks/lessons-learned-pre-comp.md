# Lessons Learned from Pre-Competition Trials (Grocery Bot)

Date: 2026-03-01

## 1. Version Control Discipline

**Problem:** The code that produced the best easy score (110, run `211903`) was committed at `7ce679e`, but subsequent uncommitted iterative changes (~411 lines of diff) never exceeded it. When trying to reproduce the high score, the original code could not be easily recovered.

**Rules for competition day:**
- **Commit before every run.** Use descriptive messages: `grocerybot: score=110 easy, added solo lookahead`.
- **Tag high-water marks.** After any new best score: `git tag easy-best-110 HEAD`.
- **Never iterate on uncommitted code.** If a change doesn't improve the score, `git checkout -- <file>` to revert before trying the next idea.
- **One change per commit.** Makes it easy to bisect which change helped vs. hurt.

## 2. Score Regression from Over-Engineering

**Timeline of easy-mode scores:**

| Run | Score | Key change from previous |
|-----|-------|--------------------------|
| 204323 | 86 | First working solo bot |
| 211903 | **110** | Solo lookahead route planner (committed at `7ce679e`) |
| 212753 | 26 | Unknown regression (uncommitted tweak) |
| 213409 | 84 | Partial recovery |
| 215012 | 103 | Further tuning |
| 215705 | 103 | Added end-game cutoff, reduced cooldown, pre-positioning |
| 220218 | 109 | Added aisle penalty, detour threshold changes |

**Key insight:** The score went from 110 -> 26 -> 84 -> 103 -> 109 with increasingly complex code. The simplest version (7ce679e) with permanent pick-failure bans (`round_number + 10000`) and no end-game cutoff logic outperformed all the "smarter" versions.

**Rules for competition day:**
- Measure before and after every change. If score drops, revert immediately.
- Complexity is not free. Each added heuristic has interaction effects.
- The scoring variance on this map is ~10-15 points between identical runs. Don't chase noise.

## 3. Changes That Helped vs. Hurt

### Helped (keep these)
- **Solo lookahead route planner** (`_select_solo_item_with_lookahead`): Plans 3-item pickup sequences optimizing total route cost including drop-off. This was the single biggest jump (86 -> 110).
- **BFS-based pathfinding** with distance caching: Correct distances through walled grid, not manhattan.
- **Preview pre-picking**: While waiting for active order items to become useful, pre-pick for the next order. Saves 2-4 rounds per order transition.

### Unclear / Possibly Hurt
- **Reduced pick-failure cooldown** (10000 -> 3): Intended to allow re-use of restocking shelves. But the original permanent ban actually produced better scores, suggesting failed picks are rare and the cooldown noise isn't worth it.
- **End-game cutoff with `_can_start_pickup_delivery_trip`**: Prevents wasting rounds on unfinishable trips. But the BFS cost calculation per round may be adding overhead, and the original `round_number > 298` hard-cutoff was simpler and scored higher.
- **Aisle span penalty** (`_aisle_span_penalty`): Added 4+ penalty for cross-aisle sequences. Theoretically sound but may be over-penalizing valid short routes.
- **Early 2-item delivery threshold** (1.5x vs 2.0x): Oscillated between values. Neither clearly better.

### Hurt (avoid these patterns)
- **Pre-positioning during end-game idle**: Bot moves toward items it can't pick up, wasting the few remaining rounds. Should just wait.
- **Reducing `successful_pick_count` penalty** from `2 *` to `1 *`: Less diversity in shelf selection may cause the bot to over-pick depleted shelves.

## 4. Map-Specific Knowledge (Easy Mode)

- **Grid:** 12x10, walls form 4 aisle columns (x=2,6,10 are walls at y=2-4 and y=6)
- **Item layout:** 16 items in 4 types (cheese, butter, yogurt, milk) at fixed positions in two aisle groups:
  - Left aisles: x=3,5 (cheese, butter, yogurt, milk at y=2-4,6)
  - Right aisles: x=7,9 (yogurt, milk, cheese, butter at y=2-4,6)
- **Drop-off:** `[1,8]` (bottom-left corner)
- **Bot start:** `[10,8]` (bottom-right corner)
- **300 rounds, 50 total orders, 3-4 items per order**
- Items restock at same positions after pickup
- Optimal throughput ceiling: ~15 orders at ~20 rounds/order = 300 rounds

## 5. Recovering the Best Code

The code that produced score 110 is preserved at commit `7ce679e`:

```bash
# View the best-scoring code
git show 7ce679e:solutions/grocerybot-trial/run_easy.py

# Restore it to working directory
git checkout 7ce679e -- solutions/grocerybot-trial/run_easy.py

# Or create a branch from it
git checkout -b grocerybot-baseline 7ce679e
```

## 6. Competition Day Protocol

1. **Start from baseline.** Checkout `7ce679e` version of `run_easy.py`.
2. **Run 3 trials** to establish baseline variance range.
3. **Make ONE change at a time.** Commit with score in message.
4. **Run 3 trials** after each change. Compare median, not best.
5. **Revert if median drops.** Don't rationalize regressions.
6. **Tag new high-water marks** immediately.
7. **Time-box tuning.** If no improvement in 30 min, move to next challenge.

## 7. High-Priority Improvements Still Worth Trying

These are ideas NOT yet tested against the baseline (7ce679e) code:

1. **Batch 3 items before delivering** -- the baseline sometimes delivers 1-2 items when it could fill the bag. Worth testing a strict "fill bag first" policy.
2. **Spatial clustering** -- prefer items in the same aisle over closer items in the opposite aisle. Simple heuristic: if all needed items exist in left aisle, don't cross to right.
3. **Order lookahead** -- when current order needs only 1 more item, start pre-positioning for preview order items.
4. **Deterministic seeds** -- set `random.seed(42)` to eliminate variance from `_random_nudge`. Makes A/B testing reliable.
