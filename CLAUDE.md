# CLAUDE.md — discovarr (`discov.arr`)

Project context for the trailer-first discovery app. Inherits the global rules in
`~/.claude/CLAUDE.md` — this file only adds what's specific to this repo.

## What this is

A **trailer-first discovery app**: theatre-mode YouTube trailer reel you navigate with
arrow keys / a TV remote, to find new TV & film without a Netflix-style subscription, then
hand a title to **Seerr** (which drives Sonarr/Radarr). **Discovery only — it never streams
or plays media, and must not gain any acquisition path that bypasses Gluetun.** LAN/Tailscale
only, never public. No Cloudflare tunnel.

Shape (mirrors `homelab-dashboard`): a thin FastAPI proxy (`app/main.py`) that holds every
API key and normalises TMDB/MDBList/Trakt into one **tile contract**, served same-origin with
a single-file HTML/CSS/JS frontend (`app/web/index.html`).

Read `DECISIONS.md` first (the grilled design + why), then `handoff.md` (current state),
then `discov-handover.md` (original brief). KB: `homelab-kb/apps/discovarr.md`.

## Two theme systems (the core UX)

- **↑/↓ vertical reel** = *generated* themes from TMDB Discover (genre × decade), random ~10
  per session → "fake infinite". `config.toml [generated]`.
- **Nav bar** = fixed *standard* themes (Trakt Trending, Watchlist, MDBList curated lists).
  `config.toml [[standard_themes]]`.
- Movies + TV interleaved in one carousel (`type` per tile). Both feeds post-filtered by
  `watched (Trakt) ∪ never-show-again (SQLite)` before serving.

## Layout

- `app/main.py` — `Settings` (every key first — see gotcha), SQLite `/data/discov.db`
  (cache + excludes + Trakt tokens), TMDB/MDBList/Trakt/Seerr clients, tile contract, theme
  engine, the `/api/*` routes, static mount. Single file by convention; grep, don't trust
  line numbers.
- `app/config.toml` — themes, rating chips, cache TTLs, per-theme cap (version-controlled).
- `app/web/index.html` — frontend (Step 2 replaces the current placeholder).
- `app/{Dockerfile,docker-compose.yml,requirements.txt,.env.example}`.
- `app/.env` (git-ignored, host-only, chmod 600) — keys; see `Settings` for the field list.
- `trailer-test/` — the throwaway Step 0 playback spike.

## How it deploys

Own Compose project (`discov-api`) on the arr-stack host, joining the **arr-stack repo's**
network externally as `arrnet` (real name `arr-stack_media_net`) so Caddy + `seerr:5055` are
reachable by name. Port `127.0.0.1:8001:8001`. Caddy fronts it at `http://discov.arr/` —
that route + the Pi-hole record live in the **arr-stack repo**, not here.

```bash
git pull && docker compose -f app/docker-compose.yml up -d --build   # on the host
```

## Key gotchas (inherited — they bit the dashboard repeatedly)

- **Image bakes `main.py`/`config.toml`/`web/` in — every edit needs `--build`.** No `--reload`.
- **After any `.env` change use `up -d`, NOT `restart`** (restart reuses cached config).
- **`pydantic-settings extra="ignore"` silently drops unmatched env vars** — add the
  `Settings` field FIRST, then the env var.
- **`from __future__ import annotations` must be the first statement** after the docstring.
- Verify on the host: `curl localhost:8001/api/title/<id>` — 500 = handler raised (`docker
  compose logs discov-api`); **connection-refused = the app failed to *start*** (import/syntax).
- Log on every upstream failure — silent failures were the dashboard's worst time-sink.
- Don't touch the live host — Claude edits this repo only; deployment is manual.
