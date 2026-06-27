# discovarr (`discov.arr`)

A trailer-first discovery app for the homelab. Theatre-mode YouTube trailer reel, navigated
with arrow keys / a TV remote, to find new TV & film without a Netflix-style subscription —
then hand a title to **Seerr** which drives Sonarr/Radarr. **Discovery only: it never streams
or plays media.** LAN/Tailscale only, never public.

- **Operations manual (deploy/operate/recover):** [`homelab-kb/apps/discovarr-operations.md`](https://github.com/mikeyzaur/homelab-kb/blob/main/apps/discovarr-operations.md)
- **Design + decisions:** [`DECISIONS.md`](DECISIONS.md)
- **Current state:** [`handoff.md`](handoff.md)
- **Original brief:** [`discov-handover.md`](discov-handover.md)
- **Project context for Claude:** [`CLAUDE.md`](CLAUDE.md)

## Status

**v1.0 — tagged 2026-06-27, maintenance-only.** Live at `https://discov.arr/`. All steps shipped:
trailer spike → full backend (TMDB/MDBList/Trakt/Seerr + Trakt OAuth) → theatre frontend + discovery
slice → deploy (Caddy/Pi-hole/favicon). Six grilled standard nav rows (Watchlist toggle, Top 10
ranked chart, Trending, Critically Acclaimed, Based on a Book, Anticipated). iPhone & Android apps
parked.

## Run (on the arr-stack host)

```bash
cp app/.env.example app/.env   # then fill in keys, chmod 600
docker compose -f app/docker-compose.yml up -d --build
curl localhost:8001/api/health
```

After a code change that alters tile shape or a theme's contents, clear the cache:
`curl -kX POST https://discov.arr/api/admin/flush`. Trakt user auth is a one-time device flow — see
the operations manual §7. The `discov.arr` Caddy route + Pi-hole record live in the **arr-stack**
repo (a Caddyfile change needs `caddy reload`, not `up -d`).

Stack: FastAPI + httpx proxy (holds all keys), single-file vanilla-JS frontend, SQLite at
`/data/discovarr.db`. Data sources: TMDB (catalog/trailers), MDBList (ratings/lists), Trakt
(watchlist/watched/trending), Seerr (requests).
