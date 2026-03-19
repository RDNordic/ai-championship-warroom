# Token Workflow

## One-time setup per token refresh

1. Copy [`solutions/astar-island/.token.example`](/C:/Users/John%20Brown/ai-championship-warroom/solutions/astar-island/.token.example) to `solutions/astar-island/.token`.
2. Open `solutions/astar-island/.token`.
3. Replace the placeholder with the full `access_token` JWT from the browser.
4. Save the file.

`solutions/astar-island/.token` is ignored by git.

## Check that auth works

From repo root:

```powershell
python solutions/astar-island/client.py
```

What it does:
- calls `GET /astar-island/rounds`
- finds the active round
- calls `GET /astar-island/rounds/{round_id}`
- calls authenticated `GET /astar-island/budget`

This is safe. It does not spend query budget.

## When to refresh the token

Refresh the token if:
- the script returns 401 or 403
- you logged out of `app.ainm.no`
- the JWT expired

To refresh:
1. Log in again at `https://app.ainm.no`
2. Copy the new `access_token`
3. Replace the contents of `solutions/astar-island/.token`

## Security

- Do not commit `.token`
- Do not paste the token into repo files other than `.token`
- If the token was exposed in chat, log out and get a fresh one after the session
