# Astar Poller

This poller is read-only. It does not call `/simulate` and it does not call `/submit`.

## What it checks

- `GET /astar-island/rounds`
- `GET /astar-island/my-rounds`
- `GET /astar-island/budget`
- `GET /astar-island/analysis/{round_id}/{seed_index}` when the latest relevant round is `scoring` or `completed`

## Why it is safe

- No query budget is spent
- No predictions are overwritten
- It only writes local state and event logs under `solutions/astar-island/artifacts/poller/`

## One-shot check

```powershell
python solutions/astar-island/poll_round_status.py --once
```

## Overnight polling

```powershell
python solutions/astar-island/poll_round_status.py --interval-sec 180
```

That polls every 3 minutes.

## Output files

- `solutions/astar-island/artifacts/poller/latest_state.json`
- `solutions/astar-island/artifacts/poller/events.jsonl`

## Event types

- `poller_started`
- `active_round_changed`
- `latest_round_status_changed`
- `budget_changed`
- `my_rounds_changed`
- `analysis_status_changed`
- `auth_failed`
- `auth_restored`

## Stop conditions

Stop and refresh the token if:
- the summary shows `"ok": false`
- the event log records `auth_failed`

Do not run a second live operator against Astar at the same time.
