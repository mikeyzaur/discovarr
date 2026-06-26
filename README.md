# discovarr (`discov.arr`)

A trailer-first discovery app for the homelab. Theatre-mode YouTube trailer reel, navigated
with arrow keys / a TV remote, to find new TV & film without a Netflix-style subscription —
then hand a title to **Seerr** which drives Sonarr/Radarr. **Discovery only: it never streams
or plays media.** LAN/Tailscale only, never public.

- **Design + decisions:** [`DECISIONS.md`](DECISIONS.md)
- **Current state / next steps:** [`handoff.md`](handoff.md)
- **Original brief:** [`discov-handover.md`](discov-handover.md)
- **Project context for Claude:** [`CLAUDE.md`](CLAUDE.md)

## Status

- **Step 0 — done.** Trailer playback de-risked on desktop + iPhone (`trailer-test/`).
- **Step 1 — scaffolded.** FastAPI backend under `app/`; needs real API keys + host curl
  verification (see `handoff.md`).
- **Step 2** theatre frontend · **Step 3** deploy — not started.

## Run (on the arr-stack host)

```bash
cp app/.env.example app/.env   # then fill in keys, chmod 600
docker compose -f app/docker-compose.yml up -d --build
curl localhost:8001/api/health
```

Stack: FastAPI + httpx proxy (holds all keys), single-file vanilla-JS frontend, SQLite at
`/data/discovarr.db`. Data sources: TMDB (catalog/trailers), MDBList (ratings/lists), Trakt
(watchlist/watched/trending), Seerr (requests).
