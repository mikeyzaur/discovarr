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

**Step 2** (theatre frontend) — **BUILT & LIVE 2026-06-27** (full spec in `DECISIONS.md`). It carries a
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
- **Discovery slice cluster 5 DONE & verified live 2026-06-27** (commit `a52b044`): items 6,
  7, 9. *Because you watched* random-seeded rows (cached 12h, interspersed); endless-feed
  `GET /api/reel/more?limit&seen=`; randomised theme resolution (random discover page + shuffle,
  trending/list/watchlist sampling). Plus dev `POST /api/admin/unexclude-theme`. Verified:
  two pulls differ; byw rows labelled from real history; reel/more honours `seen`; unexclude clears.
- **BACKEND DISCOVERY SLICE COMPLETE (all 11 items).**
- **THEATRE FRONTEND BUILT & LIVE 2026-06-27** (`app/web/index.html`, commit `89ffef9` + verify
  pass `d141bef`→`395fbf4`, then `/code-review high` fixes `b1cbc7e`). Full theatre UI on the live
  API, **deployed at `https://discov.arr/` and working end to end** incl. the favicon. The throwaway
  `design-proto/` visual mock was deleted on sign-off.

## API surface the frontend binds to (all live + verified)

- `GET /api/config` → `{ratings_chips, trakt_authed}`.
- `GET /api/themes?limit=10` → `{nav:[{id,label,titles:[{tmdb_id,type}]}], reel:[…incl. byw:* rows]}`.
- `GET /api/reel/more?limit=5&seen=<csv theme ids>` → `{reel:[…]}` (endless feed).
- `GET /api/title/{tmdb_id}?type=movie|tv&fresh=` → the tile contract (title/year/overview/poster/
  backdrop/trailer_youtube_key/**trailer_ok**/**runtime**/**number_of_seasons**/**number_of_episodes**/
  **seasons**/**credits{directors,cast[id,name,profile_url]}**/ratings/awards/requested).
- `GET /api/recommendations?tmdb_id&type` → `{titles:[…]}` (more like this).
- `GET /api/person/{person_id}/titles?role=cast|crew` → `{titles:[…]}` (cast / director spawn).
- `POST /api/watchlist` · `POST /api/request` (body now accepts optional `seasons:[…]` for TV;
  omitted/empty → all — the season picker sends a list) · `POST /api/watched` ·
  `POST /api/exclude` (hide title) · `POST /api/exclude-theme` — body `{tmdb_id,type}` except
  exclude-theme `{theme_id}`.
- `POST /api/admin/flush` · `POST /api/admin/unexclude-theme[?theme_id=]` (dev).
- `POST /api/trakt/device` + `/poll` (one-time auth, already done).

## Frontend — built & live (`app/web/index.html`)

Single-file theatre UI to the locked spec, bound to the live API. Built then iterated over a long
verify pass with Mikey (`89ffef9`, then `d141bef`→`395fbf4`), plus a `/code-review high` pass
(`b1cbc7e` — see "Post-build code review" below). What's in it:
- Full-bleed reel; **"Tonight's Programme" board** = start gesture + re-summonable jump menu
  (M/Esc); ←/→ titles, ↑/↓ themes; **endless feed** at the bottom; channel-loop auto-advance
  (localStorage); **icon action bar** wired to every live endpoint; **cast / co-director / TV-season
  pickers**; **spawned rows**; **idle chrome auto-hide** (13s → cursor hidden, chrome → ~20%).
- **Hydration:** tiles on demand + in-session cache + **image preload**; first-of-each-theme on
  boot; prefetch ±2 + neighbouring themes; **drop-on-load** of no-trailer / `trailer_ok:false`.
- **Layout (verify):** theme name (amber) top-left above the position dots; genre line below the title.
- **Transitions (verify):** preloaded **double-buffered cross-dissolve** between titles (still +
  blurred spill); metadata fades in; **2s minimum still-hold** for consistent pacing; **pause the
  outgoing trailer on nav** (clean cut); **iframe forced black + overscanned ~9%** to clip YouTube's
  title/share chrome; still held **~1.1s into playback** so YT's startup play/pause flash stays
  behind the poster.
- **Robust cold load (verify):** init **auto-retries 6×/~7s**; backend `/api/themes` resolves
  upstreams **CONCURRENTLY** (cold ~4s vs old ~15s) and degrades per-theme instead of 500-ing;
  oEmbed probe **fails open** except 401/404 (a 429 burst was wrongly dropping good trailers).

**Tuning knobs (all one-liners in `index.html`; Mikey is dialling these):** dissolve `.5s`;
still-hold floor `2000` + post-playing `1100`; idle `13000`; overscan `9%`/`118%`; settle `650`.

**Still to confirm (not blocking):** iPhone sound-through-auto-advance on real data; TV season
picker → Seerr round-trip; whether the overscan `9%` fully hides the title bar / over-crops;
trailer-quality (YouTube adaptive ramp vs bandwidth — streams device→YouTube, not via discovarr).

**Post-build code review (`/code-review high`, discovarr `b1cbc7e`).** All findings fixed:
shared `current_block()` Trakt-watched guard now wraps every feed endpoint (was only `/api/themes`,
so a Trakt blip used to 500 the endless feed + spawn rows); empty *because-you-watched* no longer
negative-cached for 12h; season picker no longer hard-codes a "Season 1" (duplicate / phantom-season
→ Seerr 422); oEmbed 429/5xx and the `doHide`/`doDitch` persistence failures now logged; tile cache
key bumped to `title:v2:` (Step-1-shaped tiles no longer served without the new fields); cleanups
(concurrent ratings+oEmbed in `build_tile`, reuse `key()` helper).

## Step 3 — DEPLOYED & LIVE 2026-06-27

`https://discov.arr/` serving end to end. Caddy `discov.arr` route (arr-stack `022c569`,
`tls internal` → `discovarr-api:8001` over `media_net`) + Pi-hole record `discov.arr → 10.13.37.168`
+ `--build` rebuild — all deployed. The temp host-side test bridge (`0.0.0.0:8011 → 127.0.0.1:8001`)
is retired. **Gotcha hit:** the arr-stack Caddyfile is bind-mounted `:ro`, so a new route needs
`docker compose exec caddy caddy reload …`, NOT `up -d` (else `SSL_ERROR_INTERNAL_ERROR_ALERT`).

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
- `app/web/index.html` — **the built theatre UI** (was the placeholder). Single-file HTML/CSS/JS;
  state machine + double-buffered crossfade + YT IFrame player + the pickers/board. Grep, not lines.
- `app/main.py` routes now also include `/api/{config,recommendations,person/{id}/titles,watched,
  exclude-theme,reel/more,admin/unexclude-theme}` (the discovery slice) — the earlier route list
  above is Step-1-only.
- `trailer-test/` — Step 0 spike (throwaway; keep for re-testing on new devices).
