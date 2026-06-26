# Handoff — discovarr (`discov.arr`)

Current-state pointer for a fresh session. Concept + decisions: `DECISIONS.md`. Original
brief: `discov-handover.md`. KB: `homelab-kb/apps/discovarr.md`. Keep this lean.

## What this is

Trailer-first discovery app for the homelab — theatre-mode YouTube trailer reel, 2-D
arrow/remote navigation, feeding titles to Seerr. **Discovery only — never streams/plays
media.** Built in the `homelab-dashboard` shape (thin FastAPI proxy holding all keys +
single-file frontend). LAN/Tailscale only, never public.

## Current state

**Step 0 — DONE & signed off** (commits `df4779e`→`fdc784b`). Standalone trailer spike
(`trailer-test/`) verified on desktop Firefox **and iPhone Safari**: all four verdicts pass,
incl. the two scary ones — **sound-on autoplay after one Start-button gesture on iOS**, and
**auto-advance keeps sound on iOS**. Concept de-risked. (Spike is throwaway, not app code.)

**Step 1 — SCAFFOLDED, untested against live keys** (this session). Full backend under
`app/` in the dashboard shape. Compiles clean (`py_compile`), but NO real API keys yet, so
the upstream calls are written-from-docs, not curl-verified. **This is the next job:**
provision keys → `curl` each endpoint on the host → fix any 4xx in the upstream shapes
(MDBList list endpoint + Trakt sync bodies are the likeliest to need a tweak).

**Step 2** (theatre frontend) and **Step 3** (deploy: Caddy `discov.arr` route in arr-stack
repo + Pi-hole record + Tailscale DNS bounce) — not started.

## Next steps (Step 1 finish)

1. On the host, create `app/.env` from `app/.env.example` (`chmod 600`) with real keys:
   `TMDB_TOKEN`, `MDBLIST_API_KEY`, `TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET`, `SEERR_API_KEY`.
2. Fill the two `REPLACE_WITH_AN_MDBLIST_LIST_ID` placeholders in `app/config.toml`.
3. `docker compose -f app/docker-compose.yml up -d --build`, then verify (handover §9 —
   build one thing, curl, move on):
   - `curl localhost:8001/api/health` → status per upstream
   - `curl "localhost:8001/api/title/1396?type=tv"` → the tile contract (Breaking Bad)
   - `curl localhost:8001/api/themes` → `{nav, reel}`
4. **Trakt OAuth (one-time):** `curl -X POST localhost:8001/api/trakt/device` → open the
   `verification_url`, enter `user_code`, then poll
   `curl -X POST "localhost:8001/api/trakt/device/poll?device_code=<device_code>"` until
   `{authorised:true}`. Tokens land in `/data/discov.db` and auto-refresh on 401.

## Deploy & verify (inherited dashboard gotchas — these bite)

- Image **bakes `main.py` + `config.toml` + `web/`** — every backend OR frontend edit needs
  `--build`. No `--reload`. `git pull` without `--build` deploys nothing.
- After any `.env` change use `up -d` (recreates), **NOT `restart`** (reuses cached config).
- `pydantic-settings extra="ignore"` silently drops unmatched env vars — add the `Settings`
  field in `main.py` FIRST, then the env var.
- `from __future__ import annotations` must be the first statement after the docstring.
- `curl localhost:8001/...` on the host: 500 = handler raised (`docker compose logs
  discov-api`); **connection-refused = app failed to *start*** (import/syntax).

## Relevant files

- `app/main.py` — backend: `Settings`, SQLite (`/data/discov.db`: cache + excludes + Trakt
  tokens), TMDB/MDBList/Trakt/Seerr clients, tile contract, theme engine (generated reel +
  standard nav), routes `/api/{health,title/{id},themes,exclude,watchlist,request,
  trakt/device,trakt/device/poll}`, static mount. Use grep, not line numbers.
- `app/config.toml` — nav (standard) themes, generated genres/decades, rating chips, TTLs,
  per-theme cap. (Two MDBList list-id placeholders to fill.)
- `app/{Dockerfile,docker-compose.yml,requirements.txt,.env.example}` — port 8001, container
  `discov-api`, network `arr-stack_media_net` (external), `/data` volume.
- `app/web/index.html` — placeholder; **Step 2 replaces it** with the theatre UI (per the
  player requirements in `DECISIONS.md`: hide title/share via poster-fade, pause on Space +
  remote OK, clean chrome).
- `trailer-test/` — Step 0 spike (throwaway; keep for re-testing on new devices).
