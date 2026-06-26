# discov — Decisions log

Outcomes from the concept grilling. Records *what we settled and why*, so the handover's
open assumptions don't get silently re-litigated.

## Build spine
**Step 0** trailer spike ✅ → **Step 1** full backend + all four APIs (TMDB, MDBList, Trakt,
Seerr) wired together → **Step 2** theatre frontend → **Step 3** deploy (Caddy + Pi-hole +
Tailscale). Decided *not* to stage the APIs — bring the whole data layer in at Step 1 rather
than half-building it.

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
- Container `discov-api`, host port **8001** (dashboard owns 8000).
- Network `arr-stack_media_net` (joined `external: true`, mirrors the dashboard).
- Seerr reachable by-name `seerr:5055` (no published port; in-network only).
- Caddy block in arr-stack's `caddy/Caddyfile`:
  ```
  discov.arr {
      tls internal
      reverse_proxy discov-api:8001
  }
  ```
- Pi-hole local DNS `discov.arr → 10.13.37.168` (v6 `pihole.toml dns.hosts`, not `custom.list`).
- Tailscale `.arr` cache gotcha: bounce `accept-dns` on clients after adding the record.
- State: SQLite `/data/discov.db` on a persistent volume.

## Explicitly deferred
- iPhone PWA polish / native iOS app — after browser proves out.
- Android TV native app — validate the Google TV browser first.
- Awards as a per-title badge (awards-as-a-theme covers most of it).
- Multi-user / sharing with mates (implies per-user Trakt tokens).
- True trailer pre-buffering (poster-instant + lazy-mount first; only revisit if it grates).
