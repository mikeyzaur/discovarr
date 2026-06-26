# Step 0 — Trailer Playback Spike

Throwaway probe. **No backend, no APIs.** It exists to answer one blocking question before
we build `discovarr`: *do YouTube trailers embed and play the way the whole concept assumes?*

## What it tests (the four verdicts on screen)

1. **Embeds & plays in-page** — trailer plays in theatre mode (not redirected, not blocked).
2. **Sound on** — after the Start button, does audio actually play, or does the browser
   force-mute? (Reports the real `isMuted()` / volume the browser allowed.)
3. **ENDED fires** — the event auto-advance depends on. If it never fires, couch-mode is dead.
4. **Embedding-disabled handled** — paste a known embed-disabled ID and confirm we detect it
   (error 101/150) instead of showing a dead black box.

## How to run it

### Quickest (this machine, desktop only)
Open `index.html` directly in a browser. Good enough for verdicts 1–3 on desktop.

### Proper test (LAN + iPhone over Tailscale + TV browser)
The iPhone/TV are the whole point, so serve it from the arr-stack host:

```bash
# on arr-stack (10.13.37.168), from this trailer-test/ dir:
python3 -m http.server 8009
```

Then open from each device:
- **Desktop (Firefox/Chrome):** `http://10.13.37.168:8009/`
- **iPhone over Tailscale:** `http://10.13.37.168:8009/` (or the host's Tailscale IP)
- **Google TV Streamer browser:** same URL — this is the real lean-back test.

> No Docker, no Caddy, no `.arr` DNS needed for the spike — a bare HTTP server is enough.
> (Pi-hole currently has no blocklists, so embeds shouldn't be DNS-blocked.)

## What to actually do

1. Press **Start the reel**. Confirm verdict 1 + 2 go green (plays, sound on).
2. Let a trailer run to the end → confirm verdict 3 (ENDED fires).
3. Tick **Auto-advance**, let one end, and **watch whether the next trailer keeps sound** —
   this is the one iPhone unknown. Desktop/TV will keep sound; iOS might force-mute the
   auto-advanced one. Note what each device does.
4. Paste an embed-disabled ID into the textarea → **Apply & restart** → confirm verdict 4.

## Heads-up on the IDs

The pre-filled IDs are placeholders (the Breaking Bad one is from the handover; the rest are
best-guess official-trailer IDs). **If any fail to load, just swap them** — grab a real ID
from any YouTube trailer URL (`watch?v=THIS_PART`) and paste it in. A wrong ID failing is
itself useful — it shows the error handling working.

## The result we need

Report back per device:
- sound-on works after Start? (Y/N)
- auto-advance keeps sound? (Y/N — especially iPhone)
- any device where embeds just don't play?

That verdict decides whether Step 1 (full backend + APIs) proceeds as planned or needs a
rethink on the trailer source.
