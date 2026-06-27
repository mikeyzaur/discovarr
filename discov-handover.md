# `discov` — Claude Code Handover

> **HISTORICAL — the original concept brief (pre-build).** discovarr shipped **v1.0 (tagged
> 2026-06-27, maintenance-only)**; this is kept for provenance only. For current truth see
> [`DECISIONS.md`](DECISIONS.md) (grilled design + as-built), [`handoff.md`](handoff.md)
> (current-state pointer), and the operations manual
> [`homelab-kb/apps/discovarr-operations.md`](https://github.com/mikeyzaur/homelab-kb/blob/main/apps/discovarr-operations.md).
> The name settled as `discovarr` (`discov.arr`), not `discov`.

A trailer-first discovery app for the homelab. **Theatre-mode trailer reel**, organised as
a 2-axis grid you navigate with arrow keys / a TV remote. The whole point: replace the
"Netflix browsing" experience (find new TV/movies to watch) without a subscription, and feed
straight into the existing arr-stack acquisition pipeline.

> **This is a NEW repo (`discov`), built in the same shape as `homelab-dashboard`.** It is
> *discovery only* — it never streams or plays media. It surfaces trailers + metadata and,
> on request, hands a title to **Seerr** which drives Sonarr/Radarr as normal. Do **not**
> add Stremio/Torrentio-style streaming addons or any acquisition path that bypasses
> Gluetun.

---

## 1. The concept (what the user actually wants)

A full-screen browser page (later: iPhone, then Android TV) showing **one title at a time**:

- **~⅔ of the screen** = the trailer playing (YouTube embed, "theatre mode" — *not* full-screen).
- **~⅓** = poster, title, synopsis, ratings, awards-if-any, and action buttons.

Navigation is a **2-D grid (themes × titles)**:

- **← / →** = previous / next title *within the current theme* (carousel).
- **↑ / ↓** = switch *theme* (Watchlist → Top 10 → From Book to Movie → Award-winning → …),
  keeping roughly the same horizontal position.
- **Actions** (buttons + key shortcuts): **Add to Watchlist**, **Never show again**,
  **Request via Seerr**.

Two modes, toggleable:

- **Manual advance** (default): the current trailer plays; the user presses → for the next.
- **Auto-advance**: when a trailer finishes, roll to the next title automatically (couch mode).

**Smoothness requirement:** preload the **metadata + poster** of the neighbours in all four
directions so the panel paints instantly on move. (See §6 for the important caveat: preload
*metadata/posters*, lazy-load the *trailer video* — do not attempt to pre-buffer multiple
YouTube players.)

**Filtering requirement:** never show titles the user has **already watched** (Trakt watched
history) or has marked **never show again** (local SQLite). Both feed one exclusion filter
applied before any theme is served.

---

## 2. Where it runs / fits (match the `homelab-dashboard` pattern exactly)

| Thing | Value |
|---|---|
| Repo | `discov` (new) |
| Host | `arr-stack` VM `10.13.37.168` |
| URL | `http://discov.arr/` via Caddy · `127.0.0.1:8000` direct (pick a free host port; dashboard uses 8000 — use a different one, e.g. **8001**, to avoid clashing) |
| Exposure | **LAN/Tailscale only, never public.** No Cloudflare tunnel. |
| Backend | FastAPI proxy (holds all API keys server-side) |
| Frontend | Single-file `app/web/index.html` (vanilla JS, no build step) |
| State | SQLite at `/data/discov.db` (persistent volume) — "never show again" + cache |
| Deploy | Manual on arr-stack: `git pull && docker compose -f app/docker-compose.yml up -d --build` |

**Caddy route** — add to the `arr-stack` repo's `caddy/Caddyfile` (the version-controlled one,
mounted `./caddy:/etc/caddy:ro`), mirroring the `info.arr` route:

```
discov.arr {
    reverse_proxy discov-api:8001
    tls internal
}
```

Then add the **Pi-hole local DNS record** `discov.arr → 10.13.37.168` (Settings → Local DNS
records / `pihole.toml` `dns.hosts` in v6 — *not* the legacy `custom.list`). Remember the
**Tailscale `.arr` cache gotcha**: a new `*.arr` name won't resolve on Tailscale clients until
`sudo tailscale set --accept-dns=false && sudo tailscale set --accept-dns=true` on the client.

**Docker network:** the container must share the network that Caddy and Seerr are on (same as
the dashboard / arr-stack compose) so `discov-api` is reachable by name from Caddy and `discov`
can reach `seerr:5055` by name. Confirm against the arr-stack compose before wiring.

---

## 3. Data sources (all confirmed — keys are free)

All keys live in `app/.env` (git-ignored, host-only, `chmod 600`). **Add the matching
`Settings` field in `main.py` BEFORE adding the env var** — `pydantic-settings` with
`extra="ignore"` silently drops unmatched vars (this bit the dashboard build repeatedly).

| Source | Used for | Auth | Notes |
|---|---|---|---|
| **TMDB** | catalog detail, **trailer video IDs**, posters/backdrops, IMDb ID cross-ref | `Authorization: Bearer <v4 token>` or `api_key=` | One call gets it all — see below |
| **Trakt** | the user's **watchlist** + **watched history** (the exclusion set), trending/popular themes | `trakt-api-key: <client_id>` + OAuth bearer for user data | Trakt's own community rating is available; **external IMDb/RT/etc are NOT exposed via Trakt API** — use MDBList for those |
| **MDBList** | **ratings** (IMDb, RT Tomatometer, RT audience/Popcorn, Metacritic, Letterboxd, Trakt) + curated **lists** (themes) | `?apikey=` | Single lookup by TMDB or IMDb ID returns all ratings in JSON. This is the three-ratings source. |
| **Seerr** | submit a **request** (the acquisition hand-off) | `X-Api-Key: <key>` | Already running at `seerr:5055`; Overseerr-compatible API |

### TMDB — one call per title

`append_to_response` collapses sub-requests into a single HTTP call:

```
GET https://api.themoviedb.org/3/movie/{id}?append_to_response=videos,external_ids,release_dates
GET https://api.themoviedb.org/3/tv/{id}?append_to_response=videos,external_ids,content_ratings
```

- **Trailer:** from `videos.results[]`, prefer `type == "Trailer"` + `site == "YouTube"` +
  `official == true`; fall back to the first YouTube "Trailer", then "Teaser". Store the
  `key` (YouTube video ID). Preferring *official* trailers is what gets you the clean
  ~1.5–2.5 min cut and avoids the "30-minute fan upload" problem — you can't trim YouTube,
  so source selection is the lever.
- **`external_ids.imdb_id`** → use as the MDBList lookup key (most reliable cross-ref).

### MDBList — ratings + lists

- **Ratings:** lookup by IMDb or TMDB ID returns a `ratings[]` array with `source` +
  `value` for imdb, tomatoes (critic), audience (Popcorn), metacritic, letterboxd, trakt.
  Map the three the user cares about (default: **IMDb, RT critic, RT audience/Popcorn** — but
  the panel should render whatever's present and degrade gracefully when a source is null).
- **Lists / themes:** MDBList hosts curated public lists (Trakt Trending, IMDb Most Popular,
  "Oscar winners", "based on a book", etc.) that return TMDB/IMDb IDs. These ARE the editorial
  themes ("From Book to Movie", "Award-winning…"). Each theme = one MDBList (or Trakt) list URL
  resolved to a list of IDs, then each ID hydrated via TMDB + MDBList ratings.

### Trakt — watchlist + the exclusion set

- **Watchlist** (`GET /users/me/watchlist`, OAuth) → one of the themes, and the target of the
  "Add to Watchlist" action (`POST /sync/watchlist`).
- **Watched history / watched set** (`GET /sync/watched/movies`, `GET /sync/watched/shows`,
  OAuth) → the **already-watched exclusion list**. Pull once, cache in SQLite, refresh
  periodically. Filter every theme against `watched ∪ never_show_again` before serving.
- OAuth: standard Trakt device/OAuth flow; store the user token in `.env` / SQLite (host-only).
  This is a single-user app for v1 — no multi-user auth needed yet.

### Seerr — the request hand-off

```
POST http://seerr:5055/api/v1/request
X-Api-Key: <seerr_api_key>
Content-Type: application/json

# movie:
{ "mediaType": "movie", "mediaId": <tmdbId> }
# tv (request all seasons; adjust if season-picking is added later):
{ "mediaType": "tv", "mediaId": <tmdbId>, "seasons": "all" }
```

`mediaId` is the **TMDB id** (Seerr is TMDB-keyed). Handle the case where the title is already
requested/available (Seerr returns a 409/relevant status) — surface "already requested" rather
than erroring. Generate the API key in Seerr → Settings → General.

---

## 4. Backend shape (FastAPI proxy)

Same architecture as `homelab-dashboard/app/main.py`: a thin proxy that holds keys, normalises
upstreams to one contract, and serves the single-file frontend.

```
discov-api  (FastAPI, 127.0.0.1:8001)
  ├── GET  /                         → static app/web/index.html
  ├── GET  /api/themes               → ordered list of themes + their title-ID lists
  │                                     (resolved from configured MDBList/Trakt lists,
  │                                      post-filtered by watched ∪ excluded)
  ├── GET  /api/title/{tmdb_id}       → normalised tile: title, year, overview, poster,
  │                                     backdrop, trailer youtube key, ratings{}, awards?
  │                                     (TMDB append_to_response + MDBList ratings, merged)
  ├── POST /api/watchlist             → add to Trakt watchlist  {tmdb_id, type}
  ├── POST /api/exclude               → "never show again" → SQLite  {tmdb_id, type}
  ├── POST /api/request               → POST to Seerr  {tmdb_id, type}
  └── GET  /api/health                → upstream reachability (TMDB/Trakt/MDBList/Seerr)
```

**Normalised title contract** (the only thing the frontend knows about):

```jsonc
{
  "tmdb_id": 1396,
  "type": "tv",                       // "movie" | "tv"
  "title": "Breaking Bad",
  "year": 2008,
  "overview": "…",                    // keep it short in the panel; full on demand
  "poster_url": "https://image.tmdb.org/t/p/w500/…",
  "backdrop_url": "https://image.tmdb.org/t/p/w1280/…",
  "trailer_youtube_key": "XZ8daibM3AE",  // null if none found
  "ratings": {                        // any may be null → render only what's present
    "imdb": 9.5,
    "rt_critic": 96,
    "rt_audience": 97,
    "metacritic": 87,
    "trakt": 90
  },
  "awards": null,                     // v2 — see §7; null for v1
  "requested": false                  // optional: known Seerr state, if cheap to fetch
}
```

**Caching (important for rate limits + snappiness):** cache `/api/title/{id}` responses in
SQLite or in-memory with a TTL (e.g. 24h for metadata, shorter for ratings). TMDB's soft
ceiling is ~40 req/s but you'll hit it fast hydrating themes if uncached. Cache theme→IDs
resolutions too (lists change slowly).

---

## 5. Frontend shape (single-file, no build)

`app/web/index.html` — one file, vanilla JS, theatre layout. Mirror the dashboard's
single-file approach (`dataFor`/`liveDetail` style), but the core here is a small **state
machine over a 2-D index**:

```
state = {
  themes: [...],            // from /api/themes
  t: 0,                     // current theme index (↑/↓)
  i: 0,                     // current title index within theme (←/→)
  autoAdvance: false,       // toggle (space)
  cache: Map<tmdb_id, title>  // hydrated titles + prefetched neighbours
}
```

- **Layout:** CSS grid, ~⅔ left/top = trailer `<iframe>` (YouTube embed, `enablejsapi=1`,
  `mute=1` for autoplay-policy compliance, `controls` minimal), ~⅓ = info panel (poster,
  title, year, ratings chips, overview, action buttons). Collapse to stacked single-column at
  a phone breakpoint (trailer on top, panel below) — that's the iPhone path for free.
- **Key handlers:** `←/→` change `i`, `↑/↓` change `t`, `W`=watchlist, `X`=never-show,
  `R`=request, `Space`=toggle auto-advance, `Esc`/back behaves sanely. These map cleanly to a
  TV remote's D-pad + a couple of buttons — which is exactly why this concept dodges the
  spatial-navigation tar pit that a full grid UI would hit.
- **On move:** repaint panel instantly from `cache` (poster shows immediately), then
  (re)mount the trailer iframe for the new title. Debounce trailer mounting (~250–400ms) so
  rapid scrolling doesn't spawn/kill players on every keypress.
- **Auto-advance:** use the YouTube IFrame API `onStateChange` → on `ENDED`, if
  `autoAdvance`, advance `i`.
- **Ratings chips:** render IMDb / RT critic / RT audience as small labelled chips; only show
  the ones present. This is the at-a-glance quality signal.

**No browser storage APIs beyond what the backend persists** — keep `autoAdvance` etc. in JS
state (or POST a tiny pref to the backend if persistence across reloads is wanted later). The
dashboard learned this; same constraint applies.

---

## 6. The one genuine hard part — directional preload (read before building)

The "preload 1–2 in each direction" want is the smart-feeling feature and the only real trap.

- **DO preload metadata + posters** for neighbours (`i±1`, and the `i`-th title of `t±1`):
  prefetch their `/api/title` into `cache`. Cheap JSON; makes the panel paint instantly on
  move. Be aggressive here.
- **DO NOT try to pre-buffer multiple YouTube trailer videos.** Hidden iframes get throttled
  by the browser and stacking players is a mess. Instead: on landing, show the poster in the
  trailer area immediately and **lazy-mount the trailer iframe**, fading the video in when it's
  ready (~0.5–1s spin-up). This *feels* smooth even though the video isn't truly pre-buffered.
- Truly pre-buffered video in four directions is a rabbit hole — **explicitly out of scope for
  v1.** Ship poster-instant + lazy-trailer, measure whether it actually feels janky on the
  real devices, and only revisit (e.g. self-hosted trailer caching) if it genuinely grates.

---

## 7. Scope — build v1, defer the rest

**v1 (browser, prove the concept):**
- Theatre layout, 3–4 themes (start hardcoded list of MDBList/Trakt list URLs in
  `config.toml`): **Watchlist · Top 10 (Trakt trending/most-watched) · From Book to Movie ·
  Award-winning**.
- 2-D arrow-key navigation; poster-instant + lazy-trailer; manual advance + auto-advance toggle.
- Ratings: IMDb + RT critic + RT audience (Popcorn) via MDBList — render what's present.
- Actions: Add to Watchlist · Never show again · Request via Seerr.
- Watched-history + never-show-again filtering.
- Caching + `/api/health`.

**v2 (only if v1 earns it):**
- **Awards** as a *per-title badge* (the data is the awkward bit — no clean free awards API;
  awards-as-a-theme via an MDBList "winners" list already covers most of the need in v1, so a
  per-title badge is genuinely optional). If pursued, source via a curated list membership
  rather than a per-title awards lookup.
- iPhone responsive polish / installable PWA; optional native iOS app "for fun".
- Configurable themes via a small UI (vs editing `config.toml`).
- "Keep playing"/auto-advance refinements; true trailer pre-buffering *iff* lazy-mount proves
  janky on the TV.

**v3 (nice-to-have):** Android TV APK / native app. Validate the browser experience on the
Google TV Streamer's browser first — do not invest in a native TV app until the browser
version proves the concept lands lean-back.

**Sharing with mates:** explicitly deferred. It implies multi-user auth + per-user Trakt
tokens — a separate increment, only worth it once the single-user app is a confirmed keeper.

---

## 8. Deploy & gotchas (inherited from the dashboard — these bite)

- **Image bakes `main.py` + `web/` in — every backend OR frontend edit needs `--build`.**
  There is no `--reload`. A `git pull` without `--build` deploys nothing.
- **After any `.env` change use `up -d` (recreates the container), NOT `restart`** — `restart`
  reuses cached config and silently ignores the new `.env`. `restart` *is* right only for
  clearing an in-memory cache without changing `.env`.
- **`pydantic-settings` `extra="ignore"` silently drops unmatched env vars** — add the
  `Settings` field first, then the env var.
- **`from __future__ import annotations` must be the first statement** in any `.py` file
  (after the module docstring) or it's a hard `SyntaxError`.
- **Verify a tile on the host:** `curl localhost:8001/api/title/<id>` — `500` = the handler
  raised (`docker compose logs discov-api`); **connection-refused = the app failed to *start*
  (import/syntax error), not a handler bug.**
- **`export COMPOSE_BAKE=false`** in `~/.bashrc` silences the cosmetic buildx "Bake" warning.
- Add logging around every upstream call — the dashboard's worst time-sinks were *silent*
  failures (empty key, wrong digest casing, shadowed `fetch`). Log on failure, don't swallow.
- Secrets: `app/.env` git-ignored + `chmod 600`; `app/config.toml` (themes list, rating
  display order, cache TTLs) version-controlled; `/data/discov.db` on a persistent volume.

---

## 9. First-session plan for Claude Code

1. Scaffold the repo in the dashboard's shape: `app/{main.py, web/index.html, config.toml,
   docker-compose.yml, requirements.txt, .env.example}`, `/data` volume, host port **8001**.
2. `Settings` (pydantic) with fields for every key FIRST: `tmdb_token`, `trakt_client_id`,
   `trakt_oauth_token`, `mdblist_api_key`, `seerr_base` (`http://seerr:5055`), `seerr_api_key`.
3. Implement `/api/title/{id}` end-to-end for one hardcoded TMDB id (TMDB append_to_response +
   MDBList ratings merge → the contract in §4). `curl` it on the host until the shape is right.
   **Build one thing, verify with curl, move on** — don't wire the frontend until the title
   contract returns real data.
4. Implement `/api/themes` for one theme (Trakt trending or one MDBList list), with the
   watched/excluded filter stubbed, then real.
5. Minimal frontend: one title, theatre layout, trailer iframe + ratings chips. Then add the
   2-D navigation + neighbour metadata preload. Then the three actions.
6. Caddy route + Pi-hole record + Tailscale DNS bounce. Confirm `http://discov.arr/` loads on
   LAN, then on an iPhone over Tailscale.
7. Only after browser is good: evaluate on the Google TV Streamer browser before any TV-app work.

**Definition of done for v1:** the user can sit at the browser, arrow through 3–4 themes of
not-yet-watched titles, watch clean trailers in theatre mode with IMDb/RT-critic/RT-audience
chips, and Watchlist / Never-show / Request each — with watched titles never appearing.
