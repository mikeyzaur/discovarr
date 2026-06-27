# discovarr — Decisions log

Outcomes from the concept grilling. Records *what we settled and why*, so the handover's
open assumptions don't get silently re-litigated.

## Build spine
**Step 0** trailer spike ✅ → **Step 1** full backend + all four APIs ✅ → **Step 2** theatre
frontend (**DESIGN LOCKED 2026-06-27**) → **Step 3** deploy (Caddy + Pi-hole + Tailscale).
Decided *not* to stage the APIs —
bring the whole data layer in at Step 1 rather than half-building it.

## Step 0 — DONE (verified on desktop Firefox + iPhone Safari over LAN)
All four verdicts passed:
1. ✅ Trailers embed and play in-page.
2. ✅ **Sound-on autoplay after the single Start-button gesture — on iPhone too** (the
   strictest case; this was the scariest unknown and it passed).
3. ✅ ENDED fires; **auto-advance keeps sound on iPhone** (the second scary unknown — passed,
   so couch-mode works fully on iOS).
4. ✅ Unplayable trailers (removed/region-locked/etc.) detected via `onError` → would skip,
   no dead black box. Owner-disabled embedding turned out rare (probed ~25 popular videos,
   zero blocked); age-restricted is the one case `onError` can't catch (shows an age-gate),
   but TMDB trailers are effectively never age-gated → non-issue, with a load-timeout skip as
   the safety net if it ever happens.

The concept is de-risked. Spike lives in `trailer-test/` (throwaway probe, not app code).

## Step 1 — DONE (backend verified live on the arr-stack host)
All four upstreams working end to end (`discovarr-api`, port 8001):
- `/api/health` all 200; `/api/title/{id}` returns the full tile contract incl. ratings
  (`imdb · rt_critic · rt_audience · metacritic · trakt`); `/api/themes` returns Trakt
  Trending + the `book-to-movie` MDBList list + the generated TMDB-Discover reel.
- Trakt OAuth authed (device flow), watchlist + watched-exclusion live, tokens auto-refresh.

**Operational gotchas discovered (durable):**
- **MDBList ratings** = `/{provider}/{type}/{id}` (e.g. `/imdb/show/{id}`), type must match
  (`imdb/movie` of a show id → 404). The root `?i=` form is the API landing page, not data.
- **The persistent SQLite cache masks code changes** — a rebuild won't show a fix until the
  cached entry's TTL expires. Bypass with `POST /api/admin/flush` or `?fresh=1` on `/api/title`.
- **Compose project name pinned to `discovarr`** (+ volume `discovarr_db`) — the `app/` dir
  otherwise derives project `app` and collides with homelab-dashboard (shared project →
  `down --remove-orphans` cross-nuke risk).

## Sound / autoplay  *(the load-bearing UX decision)*
- **Start splash button** is the entry point. That single tap banks the browser user-gesture →
  **sound-on autoplay for the whole session, every device including iPhone.** No per-device
  permission faff, and it works for guests later.
- Manual advance (arrows/Next) is itself a gesture → **sound guaranteed everywhere**.
- ~~Auto-advance is the one residual unknown on iOS~~ → **RESOLVED in Step 0: iPhone keeps
  sound through auto-advance.** No fallback needed.
- `playsinline` always, so iOS doesn't force fullscreen.
- Pi-hole currently has **no blocklists** → embed DNS-blocking is a non-risk today.

## Themes — two independent systems
- **↑/↓ vertical reel = generated engine.** TMDB **Discover** API composes themes on demand
  (genre × decade × keyword): "80s Sci-Fi", "Korean Thrillers", etc. Random ~10 per startup →
  "fake infinite", fresh every session, no list-curation, consistent quality.
- **Nav bar = fixed standard themes only.** Curated shortlist in `config.toml`: Trakt Trending,
  Your Watchlist, Award Winners, From Book to Movie. The "I know what I want" path.
- Selecting a nav theme drops you into that carousel; ↑/↓ continues through the generated
  stack from there. (Exact post-selection ↑ behaviour = small build-time detail.)
- **Movies + TV interleaved in a single carousel**, `type` carried per tile.

## Player chrome & controls  *(Step 2 requirements, from Step 0 testing)*
- **Clean chrome:** `controls:0` + `iv_load_policy:3` + `disablekb:1` + `fs:0`, plus a
  transparent **cover overlay** over the iframe so hover/tap never reveals YouTube's UI.
- **Title + Share top-bar must go** (`controls:0` does NOT remove them). Approach: the
  poster-instant + lazy-mount **fade-in** (handover §6) hides the load-time title/share flash
  *behind the poster*; YouTube auto-hides the top bar a few seconds into playback, and the
  cover overlay stops it re-revealing. **Fallback if any residual:** oversized-iframe clipped
  by `overflow:hidden` to push the top/bottom chrome outside the visible frame (minor crop).
- **Spinner at load is acceptable** (hidden behind the poster anyway).
- **Pause control required:** play/pause toggle on **Spacebar** and the **remote centre/OK
  button**. NOTE this collides with the handover's "Space = toggle auto-advance" — reassign
  auto-advance to another key; settle the full key-map at Step 2.

## Hydration / caching
- On load, hydrate only the **first title of each of the ~10 themes** (vertical preview);
  lazy-hydrate the rest of a carousel as you scroll into it. Keeps random-theme API cost sane.
- Cache theme→ID resolutions and `/api/title/{id}` in SQLite with TTL (24h metadata, shorter
  ratings), per handover §4.

## Ratings
- Default chips: **IMDb + RT critic + RT audience (Popcorn)** via MDBList.
- Render-what-exists; **a title with no ratings yet is normal** (new trailers often have none)
  → just show nothing, never a "0" or error.
- Chip set **configurable in `config.toml`** (add Metacritic/Letterboxd later, no code change).

## Trakt
- Brought in at **Step 1** alongside the others (not deferred).
- Two halves: **public** (trending — `trakt-api-key` header only, no OAuth) and **user**
  (watchlist + watched-history exclusion + add-to-watchlist — OAuth).
- **OAuth uses refresh-token-in-SQLite with auto-refresh on 401**, *not* a static `.env` token
  (a static token silently dies at ~90 days — exactly the kind of silent failure to avoid).
- Watched-history ∪ never-show-again = the exclusion filter applied before any theme serves.

## Infra  *(confirmed against arr-stack / homelab-dashboard repos)*
- Container `discovarr-api`, host port **8001** (dashboard owns 8000).
- Network `arr-stack_media_net` (joined `external: true`, mirrors the dashboard).
- Seerr reachable by-name `seerr:5055` (no published port; in-network only).
- Caddy block in arr-stack's `caddy/Caddyfile`:
  ```
  discov.arr {
      tls internal
      reverse_proxy discovarr-api:8001
  }
  ```
- Pi-hole local DNS `discov.arr → 10.13.37.168` (v6 `pihole.toml dns.hosts`, not `custom.list`).
- Tailscale `.arr` cache gotcha: bounce `accept-dns` on clients after adding the record.
- State: SQLite `/data/discovarr.db` on a persistent volume.

## Step 2 — theatre frontend (DESIGN LOCKED 2026-06-27)
Grilled in full and validated against a runnable visual prototype (`design-proto/` — a
throwaway mock; **delete once Step 2 ships**). This section is canonical and **supersedes the
older scattered Step 2 notes** in "Player chrome & controls" and "Hydration / caching" above
where they differ.

### Navigation & screen model
- **Full-bleed single-trailer reel** — NOT a poster grid. The trailer fills the screen; the
  metadata sits in a persistent lower **letterbox bar**. The whole appeal is lean-back
  *flipping through trailers*, not browsing posters.
- **Two axes:** ←/→ = prev/next **title** within a theme; ↑/↓ = prev/next **theme**.
- **One unified vertical theme list** (no nav bar): standard themes first, then generated,
  with 2–3 **"Because you watched…"** rows interspersed (not clumped).
- **"Tonight's Programme" board** = the start screen (the sound-unlock gesture) AND a
  re-summonable jump menu (M / Esc). ↑/↓ choose, Enter/OK start — that press banks sound.
- **Wrap:** titles within a theme wrap seamlessly (…9, 10, 1, 2…). The theme axis is an
  **endless fresh feed** — ↓ past the last generated theme re-calls `/api/themes` and appends
  a fresh random batch (no loop, no reload); ↑ above the first theme stops gently.

### Playback lifecycle
- **Land = autoplay with sound** (gesture banked at Start).
- **Settle debounce 1s** (tuneable): scrolling shows poster+metadata instantly; the trailer
  only loads after ~1s dwell, so skimming doesn't thrash the player.
- **Poster-instant → cross-fade** to video on `PLAYING`.
- **Auto-advance default ON = "channel" model:** at `ENDED`, advance to the next title in the
  **same theme**, looping forever; it does **not** change theme on its own. Toggle in the bar,
  persisted in `localStorage`.
- **Manual arrows always interrupt** (and being a gesture, guarantee sound on iOS).

### Loading & robustness
- Hydrate the **first title of every theme** on boot; lazy-hydrate the rest; in-session JS
  cache (`Map` keyed `type:id`).
- **Prefetch 2–3 titles each direction** + the first title of **2–3 themes each way**.
- "Preload" = metadata + image only (poster-instant covers the YouTube cue gap; not the video).
- **Never a dead black box:** skip on no-trailer / `onError` (2,5,100,101,150) / an 8s
  load-timeout, advancing in the direction of travel; cap at ~8 consecutive skips then stop
  with a message.

### Per-title actions (surfaced as ICONS in the persistent letterbox bar)
- **Watchlist** → Trakt `/sync/watchlist`; confirm + fill icon; **stay**.
- **Request** → Seerr; confirm + fill icon; **stay**.
- **Mark watched** → Trakt `/sync/history`; **auto-advance** next.
- **Not for me** (hide title) → local SQLite `excluded`; **auto-advance** next.
- **Ditch this category** → local SQLite `excluded_themes` — bans the **exact generated theme
  (combo)**, not the whole genre; **jump to next theme**.
- **More like this** → TMDB recommendations → spawn *"Because you liked X"* row + **jump in**.
- **More from director** → credits → `discover?with_crew=` → spawn + jump in.
- **More with cast** → credits → **visual cast picker** (top ~10, circular headshots from
  `profile_path`) → `discover?with_cast=` → spawn + jump in.

### Key-map (browser; TV-remote optimisation is BACKLOGGED — browser + iPhone first)
**Space = pause** (the collision is resolved: auto-advance is a toggle, not a key). ←/→ titles
· ↑/↓ themes · Esc/M board · **W** watchlist · **R** request · **F** fullscreen. All other
actions = click/tap the icon. iPhone: tap video = pause; tap icons.

### Data model — the architectural split (signed off; hard to undo later)
- **Trakt = canonical for shared taste signals:** watchlist (add), watched (mark via
  `/sync/history` + read for the exclusion set and "Because you watched"), trending.
- **Local SQLite = discovarr-only prefs Trakt can't express:** hide-title (`excluded`),
  ditch-theme (`excluded_themes`).
- **Seerr = the request.**

### Metadata shown
Theme name (eyebrow, above title) · title (billing block) · year · **runtime** (movies, e.g.
"2h 46m") / **season count** (TV, or **episode count** if a single season) · full TMDB
paragraph overview (4-line clamp) · ratings chips.

### Ratings
Config-driven (`config.toml [ratings].chips`) exposed via a new **`/api/config`**. Icons: IMDb
badge, RT tomato (critic), popcorn (audience). **Light** good/ok/bad quality tint on values
(IMDb 7.5 / 6; RT 75 / 60). Render-what-exists; show nothing when absent (never "0").

### Visual direction — "the room lit by the screen"
- **Signature (the one risk): light-spill** — a heavily blurred copy of the title's backdrop
  bleeds around the letterboxed screen (the projector lighting the auditorium), tints the
  chrome, and cross-fades per title. The trailer is the hero; the UI defers to it.
- **Palette (warm shadow, NOT neon-on-black):** `--auditorium #0B0A09`, `--house #15120F`,
  `--ink #F2EBDF`, `--ink-dim #968C7F`, `--marquee #E9B44C` (incandescent amber, sparing),
  `--spill` = dynamic per title.
- **Type (cinema printing):** billing-block ultra-condensed all-caps (Saira Extra Condensed)
  for title/credits; marquee condensed (Saira Condensed) for theme names + the board; humanist
  body (Mulish); tabular figures for ratings.
- **Motion (restrained):** "house lights down" boot sequence; cross-dissolve per title; ambient
  spill colour-shift; `prefers-reduced-motion` → instant. Nothing else moves.
- **Images:** production uses TMDB — `backdrop_url` (w1280) for the spill, poster (`w780`/
  `original`) for the still. Not `original` everywhere (multi-MB). Never YouTube thumbnails for
  stills (sharp-but-texty vs clean-but-soft — only TMDB gives clean + sharp).

### Build-time backend additions surfaced by the grill (Step 2 is NOT frontend-only)
A small **"discovery slice"** rides alongside the frontend:
1. **`/api/config`** — ratings chips (+ any display config the FE needs).
2. **Tile contract:** add `runtime` (movie) + `number_of_seasons`/`number_of_episodes` (tv) —
   `append_to_response` already returns them.
3. **Discovery actions:** recommendations endpoint (more-like-this); credits-based spawns
   (director via `with_crew`, cast via `with_cast`) + return the cast list (`profile_path`) for
   the picker.
4. **Mark watched:** `/api/watched` → Trakt `/sync/history` POST.
5. **Theme exclusion:** `excluded_themes` table + `/api/exclude-theme` + a filter in
   `generated_themes()`.
6. **"Because you watched":** fetch recent Trakt history → recommendations → 2–3 seeded themes
   interspersed in the `/api/themes` reel.
7. **Endless feed:** a re-call of `/api/themes` appends a fresh generated batch (consider
   excluding already-seen / ditched themes).

### Open / deferred (NOT part of this lock)
- **Top-5 standard themes** — to be grilled separately. Award Winners still needs a real
  MDBList `list_id`; decide whether Trakt Trending includes TV.
- **TV-remote** button-cramming optimisation — backlogged (browser + iPhone are fine for v1).
- **`design-proto/`** is throwaway — delete once Step 2 ships.

## Explicitly deferred
- iPhone PWA polish / native iOS app — after browser proves out.
- Android TV native app — validate the Google TV browser first.
- Awards as a per-title badge (awards-as-a-theme covers most of it).
- Multi-user / sharing with mates (implies per-user Trakt tokens).
- True trailer pre-buffering (poster-instant + lazy-mount first; only revisit if it grates).
