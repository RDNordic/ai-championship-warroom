# RUNBOOK.md

## Quick Resume
Each difficulty has an independent bot file. Tune one without affecting others.

## Active Window
- Focus now: `Hard + Expert` point collection.
- External benchmark reference: `Hard 243`, `Expert 219`, combined `462`.
- Historical best in workspace: `Hard 99`, `Expert 71`, combined `170`.
- Current process gate uses clean baseline median, not historical best.
- Do not touch websocket/token/logging plumbing.

## Score Anchors
- Easy: 137 (KO reference run)
- Medium: 118
- Hard historical best: 99
- Expert historical best: 71

### Current clean baseline (as of 2026-03-03 UTC)
- Expert map seed: `7004`
- Baseline run_ids: `20260303_232503`, `20260303_232642`, `20260303_232807`
- Clean scores: `3, 3, 12`
- Clean median gate: `3`

## Token Setup
1. Go to `app.ainm.no/challenge`.
2. Select difficulty.
3. Click **Play**.
4. Update `.env`:

```dotenv
GROCERY_BOT_TOKEN_EASY=<token>
GROCERY_BOT_TOKEN_MEDIUM=<token>
GROCERY_BOT_TOKEN_HARD=<token>
GROCERY_BOT_TOKEN_EXPERT=<token>
GROCERY_BOT_TOKEN_NIGHTMARE=<token>
```

## Run Commands
From `solutions/grocerybot-trial-vs-code`:

```powershell
& ".venv\Scripts\python.exe" run_easy.py
& ".venv\Scripts\python.exe" run_medium.py
& ".venv\Scripts\python.exe" run_hard.py
& ".venv\Scripts\python.exe" run_expert.py
& ".venv\Scripts\python.exe" run_nightmare.py
& ".venv\Scripts\python.exe" test_nightmare_smoke.py --rounds 40
```

## Output + Artifacts
- Progress print every 25 rounds
- `Game over: {...}`
- `Run logged: {...}`
- Replay: `logs/game_YYYYMMDD_HHMMSS.jsonl`
- History table: `logs/run_history.csv`
- Notes: `logs/TRIAL_MEMORY.md`

## Rate Limits
- 60s cooldown between runs
- 40 runs/hour
- 300 runs/day

## Hard/Expert Lightweight Gate (Default)
1. Make exactly one behavior change in one file (`run_hard.py` or `run_expert.py`).
2. Run 3 games on that difficulty.
3. Validate each replay with `validator.py`.
4. Mark run noisy if `TIMEOUT ROUNDS > 5`.
5. Discard noisy runs from scoring.
6. Require at least 2 clean runs:
   - if fewer than 2, run one extra,
   - if still fewer than 2, classify trial inconclusive and revert.
7. Compare clean median score vs current clean baseline median.
8. Keep only if median improves baseline; otherwise revert.

### Decision notes
- Historical best (`Expert 71`) is a milestone target, not the trial gate.
- Use same map seed when comparing medians. If seed changes, refresh baseline first.

## Validator Command
From repo root:

```powershell
solutions\grocerybot-trial-vs-code\.venv\Scripts\python.exe solutions\grocerybot-simulator\validator.py <replay.jsonl>
```

## 3-Run Batch Command (Expert)
```powershell
$py = ".venv\Scripts\python.exe"
for ($i = 1; $i -le 3; $i++) {
  & $py run_expert.py
  if ($i -lt 3) { Start-Sleep -Seconds 65 }
}
```

## Wait-Cluster Diagnostic
After each batch, inspect rounds where all 10 bots issued `wait`.

```powershell
$replay = "logs/game_YYYYMMDD_HHMMSS.jsonl"
Get-Content $replay | ForEach-Object {
  $obj = $_ | ConvertFrom-Json
  if ($obj.event -eq "actions") {
    $acts = @($obj.actions)
    if ($acts.Count -eq 10 -and (@($acts | Where-Object { $_.action -ne "wait" }).Count -eq 0)) {
      $obj.round
    }
  }
}
```

Interpretation:
- mostly late rounds -> endgame policy issue
- mostly mid rounds -> congestion/deadlock issue
- mostly early rounds -> opening/assignment issue

## Current Direction
- Expert: traffic/deadlock coordination and failed-pick handling first.
- Hard: opening throughput / anti-stack only.
- Medium: frozen unless explicitly switched.
