# design-proto — throwaway visual preview (Step 2 sign-off)

**Not app code.** A self-contained mock of the theatre frontend so the *look* and *feel*
can be judged before building Step 2 for real. Mirrors the Step 0 spike's pattern: one
HTML file, no backend, no APIs, hardcoded sample trailers, imagery from YouTube thumbnails
(so nothing 404s). Delete once the design is signed off.

## What it's demonstrating

The **"room lit by the screen"** direction:
- **Light-spill signature** — a blurred wash of the current trailer's image bleeds around the
  letterboxed screen (the projector lighting the auditorium). Watch it shift between titles.
- **Billing-block type** — title/credits in ultra-condensed all-caps, lifted from movie posters.
- **Palette** — warm shadow + a sparing incandescent marquee amber (not a fixed neon accent).
- **Programme board** — the start gesture (unlocks sound) *and* the re-summonable jump menu.
- **Icon control bar**, ratings chips, reel-position marker, toasts.

## How to view

**Desktop (quickest):** open `index.html` directly in Firefox/Chrome. Good for the look + the
←/→ ↑/↓ navigation, sound, auto-advance, pause.

**iPhone / TV browser (the real lean-back test):** serve from the arr-stack host like the spike —
```bash
# from this design-proto/ dir, on the host:
python3 -m http.server 8010
```
then open `http://10.13.37.168:8010/` on each device.

## Controls

- Board: **↑/↓** choose · **Enter** start (or click a row)
- Reel: **←/→** titles · **↑/↓** themes · **Space** pause · **M / Esc** programme board
- **W** watchlist · **R** request · other actions = click the icons (they just toast here)
- If the very first trailer doesn't auto-start (YouTube API still loading), press **→** once.

## Known demo-only caveats

- Some trailer IDs are best-guess; a dud just exercises the **skip logic** (a real feature).
- Light-spill here is the blurred thumbnail itself (CORS blocks colour-sampling a YT image);
  the production version sampling TMDB images via the same-origin proxy can tint more precisely.
- Google Fonts load over the network — needs internet on the viewing device (Pi-hole has no
  blocklists, so fine on the LAN/Tailscale).
</content>
