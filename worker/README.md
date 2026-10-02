# belt-picks Worker

Cloudflare Worker + KV behind the global **Beat the lean** leaderboard and the sites' **web push** alerts.
Live at `https://belt-picks.rjr5021.workers.dev` (free tier). `belt-picks.js` is the whole thing: no build step.

| Endpoint | Who calls it |
|---|---|
| `POST /pick` `{site, league, key, pick, uid, name}` | the Beat-the-lean widget on every belt's next-game page |
| `GET /standings?site=bh&league=nhl&uid=…` | `/<lg>/leaderboard/` pages; `site=cbb`, `wcbb`, `cfb`; `site=all` for `/leaderboard/` |
| `POST /subscribe` `{belt, sub}` / `POST /unsubscribe` | the push button in the alerts box (`bh:<lg>`, `all`, `cfb`, `cbb`, `wcbb`) |
| `POST /notify` `{belt, reign, title, body, url}` + `X-Notify-Key` | `notify_push.py` in the deploy workflow; one push per belt + reign |

A pick is accepted only for the game the site's `api/picks.json` lists as open, and only before its
`kickoff_utc`; grading reads the same file's `results`. Standings are cached in KV for 10 minutes.
Push uses VAPID (ES256) and aes128gcm encryption on WebCrypto, RFC 8291/8292, verified against an
independent decrypt in the session that built it.

To redeploy from a terminal: `npx wrangler deploy` in this folder (after `npx wrangler login`).
