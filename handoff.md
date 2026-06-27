# Handoff — discovarr (`discov.arr`)

Current-state pointer for a fresh session. Concept + decisions: `DECISIONS.md`. Original
brief: `discov-handover.md`. KB: `homelab-kb/apps/discovarr.md`. Keep this lean.

## What this is

Trailer-first discovery app for the homelab — theatre-mode YouTube trailer reel, 2-D
arrow/remote navigation, feeding titles to Seerr. **Discovery only — never streams/plays
media.** Built in the `homelab-dashboard` shape (thin FastAPI proxy holding all keys +
single-file frontend). LAN/Tailscale only, never public.

## Current state

**Step 0 — DONE.** Trailer spike (`trailer-test/`) verified on desktop + iPhone: sound-on
autoplay after one Start gesture and auto-advance-keeps-sound, both on iOS. Concept de-risked.

**Step 1 — DONE & VERIFIED ON THE HOST.** Backend live in `app/` on arr-stack
(`discovarr-api`, port 8001). All four upstreams working end to end:
- `/api/health` → all 200 (now hits real MDBList endpoint, not its landing page).
- `/api/title/{id}` → full tile contract incl. **ratings** (`imdb 9.5 · rt_critic 96 ·
  rt_audience 97 · metacritic · trakt`) merged from TMDB + MDBList.
- `/api/themes` → Trakt Trending + the `book-to-movie` MDBList list + the generated reel
  (TMDB Discover: "1980s Sci-Fi", "2020s Crime", …) all populating.
- **Trakt OAuth authed** (device flow), watchlist + watched-exclusion active, tokens in
  SQLite w/ auto-refresh.
- Seerr request path wired (not yet exercised with a real request).

**Step 2** (theatre frontend) — **DESIGN LOCKED 2026-06-27** (full spec in `DECISIONS.md`;
runnable visual mock in `design-proto/`, throwaway — delete once Step 2 ships). It carries a
backend **"discovery slice"** built first so the FE binds to real endpoints.
- **Discovery slice cluster 1–3 DONE & verified live 2026-06-27** (commit `6fb185e`):
  `/api/config` (chips + `trakt_authed`); tile now carries `runtime`/season+episode counts +
  specials-stripped `seasons` list + `credits` (directors + top-10 cast w/ id + w185
  `profile_url`) via one `append_to_response`; `trailer_ok` YouTube-oEmbed probe (cached on
  the tile, fails open). Verified: `/api/config` → chips + `trakt_authed:true`; Inception →
  runtime 148 + Nolan + 10 cast; Breaking Bad → 5 seasons/62 eps, specials excluded.
- **Discovery slice cluster 4 DONE & verified live 2026-06-27** (commit `0eb5014`): items 3,
  4, 5. `GET /api/recommendations` (more-like-this); `GET /api/person/{id}/titles?role=cast|crew`
  (director/cast spawns — via `combined_credits`, a deliberate deviation from discover
  `with_crew/with_cast` which don't exist on `/discover/tv`); `POST /api/watched` → Trakt
  `/sync/history` (+ invalidates the cached watched set); `POST /api/exclude-theme` +
  `excluded_themes` table (ditched `gen:` combos filtered out of the reel). Verified: recs→20,
  Nolan crew→14, DiCaprio cast→22, ditch removes the combo. `/api/watched` not yet run against
  real Trakt (wired like the proven watchlist path).
- **Remaining slice (cluster 5 = NEXT):** *Because you watched* random-seeded rows (item 6);
  endless-feed re-roll (7); randomised theme resolution — quality-bounded random page for
  discover, shuffle for lists/trending (9). Then the theatre `index.html`.

**Step 3** (deploy: Caddy `discov.arr` route in arr-stack repo + Pi-hole record + Tailscale DNS
bounce) — NOT started.

## Gotchas learned this session (will bite again)

- **MDBList ratings** = RESTful `/{provider}/{type}/{id}` (e.g. `/imdb/show/tt0903747`); the
  type MUST match (`imdb/movie` of a show id → 404). The root `?i=` form returns the API
  landing page (200, no data) — that was the empty-`ratings:{}` bug.
- **The SQLite cache masks code changes.** Title/theme responses are cached in the persistent
  volume (24h/12h TTL), so a rebuild alone won't show your fix. Use **`POST /api/admin/flush`**
  or **`GET /api/title/{id}?fresh=1`** to bypass. (This bit us — tiles kept returning stale
  empty ratings after the fix until the cache was cleared.)
- **Compose project name** is pinned to `discovarr` (was deriving `app` from the dir and
  colliding with homelab-dashboard). Volume pinned to `discovarr_db`. Don't let it revert to
  the dir-derived name or `down --remove-orphans` could cross-nuke the dashboard.
  **The live container actually ran under the unpinned `app` project (volume
  `app_discovarr_db`) until 2026-06-27** — migrated to pinned `discovarr`/`discovarr_db` at
  Step-2 build time (Trakt tokens copied across; stale `app_discovarr_db` kept as rollback,
  safe to `docker volume rm` once confident). Full note in `DECISIONS.md` Step-1 gotchas.

## Open items (small)

- **Award Winners** nav theme still a placeholder `list_id` → returns empty. Wire a real
  MDBList Oscar/awards list in `config.toml`.
- **Trakt rating pane** the user liked — surface the Trakt score (already in the MDBList
  ratings as `trakt`, zero extra calls) and optionally the vote distribution
  (`/shows/{id}/ratings`, one extra cached call). Confirm which pane before building.
- Generated reel sometimes returns <10 themes (empty genre×decade combos dropped) — top up if
  it feels thin.

## Deploy & verify (inherited dashboard gotchas — these bite)

- Image **bakes `main.py` + `config.toml` + `web/`** — every backend OR frontend edit needs
  `--build`. No `--reload`.
- After any `.env` change use `up -d` (recreates), **NOT `restart`**.
- `pydantic-settings extra="ignore"` silently drops unmatched env vars — add the `Settings`
  field FIRST, then the env var.
- `from __future__ import annotations` first statement after the docstring.
- `curl localhost:8001/...` on the host: 500 = handler raised (`docker compose logs
  discovarr-api`); **connection-refused = app failed to *start*** (import/syntax).

## Relevant files

- `app/main.py` — backend: `Settings`, SQLite (`/data/discovarr.db`: cache + excludes + Trakt
  tokens), TMDB/MDBList/Trakt/Seerr clients, tile contract, theme engine (generated reel +
  standard nav), routes `/api/{health,title/{id},themes,exclude,watchlist,request,admin/flush,
  trakt/device,trakt/device/poll}`, static mount. Use grep, not line numbers.
- `app/config.toml` — nav (standard) themes, generated genres/decades, rating chips, TTLs,
  per-theme cap. (Award Winners `list_id` still a placeholder.)
- `app/docker-compose.yml` — `name: discovarr`, container `discovarr-api`, port 8001, network
  `arr-stack_media_net` (external), volume `discovarr_db`.
- `app/web/index.html` — placeholder; **Step 2 replaces it** with the theatre UI (per the
  player requirements in `DECISIONS.md`: hide title/share via poster-fade, pause on Space +
  remote OK, clean chrome).
- `trailer-test/` — Step 0 spike (throwaway; keep for re-testing on new devices).
