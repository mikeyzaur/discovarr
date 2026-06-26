"""
discov — backend proxy (Step 1).

The only holder of API keys. Fans out to TMDB / MDBList / Trakt / Seerr and
normalises every title into ONE shape (the tile contract in §4 of the handover)
so the single-file front-end stays dumb.

Architecture mirrors homelab-dashboard/app/main.py: a thin async proxy.

Run locally:   uvicorn main:app --reload --port 8001   (needs app/.env)
In Docker:     docker compose -f app/docker-compose.yml up -d --build

NOTHING here streams or plays media. It surfaces trailers + metadata and, on
request, hands a TMDB id to Seerr which drives Sonarr/Radarr as normal.

NOTE: the upstream request shapes (esp. MDBList list endpoints + Trakt sync
bodies) are written from the documented APIs but UNTESTED against live keys —
verify each with `curl` on the host (handover §9) and adjust if a 4xx comes back.
Every upstream call logs on failure (handover §8: silent failures were the
dashboard's worst time-sink).
"""

from __future__ import annotations

import logging
import random
import sqlite3
import time
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

MediaType = Literal["movie", "tv"]
DB_PATH = Path("/data/discov.db")
APP_DIR = Path(__file__).parent

# Piggyback uvicorn's logger so output lands in `docker compose logs discov-api`.
log = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------------------------
# Settings — EVERY key needs a field here FIRST. pydantic-settings with
# extra="ignore" silently DROPS unmatched env vars (this bit the dashboard
# build repeatedly — handover §3/§8). Trakt OAuth tokens are NOT here: they're
# minted via device-flow and stored in SQLite (auto-refreshed) so they survive
# the 90-day access-token expiry without manual babysitting.
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tmdb_token: str = ""          # TMDB v4 read token (Bearer)
    mdblist_api_key: str = ""     # MDBList ?apikey=
    trakt_client_id: str = ""     # Trakt app client id (also the public api-key header)
    trakt_client_secret: str = "" # Trakt app secret (device-flow + refresh)
    seerr_base: str = "http://seerr:5055"
    seerr_api_key: str = ""


settings = Settings()


def load_config() -> dict:
    """Version-controlled config.toml: nav-bar (standard) themes, the generated
    theme dimensions, rating chip order, cache TTLs, per-theme title cap.
    Missing/malformed values fall back to built-in defaults at each call site."""
    try:
        with open(APP_DIR / "config.toml", "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        log.warning("config.toml not found — using built-in defaults")
        return {}
    except Exception as e:  # noqa: BLE001
        log.error("config.toml malformed (%s) — using built-in defaults", e)
        return {}


CONFIG = load_config()


# ---------------------------------------------------------------------------
# SQLite — cache (title + theme-resolution), never-show-again excludes, and the
# Trakt token store. WAL so reads don't block the single-writer.
# ---------------------------------------------------------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS excluded "
            "(tmdb_id INTEGER, type TEXT, added REAL, PRIMARY KEY (tmdb_id, type))"
        )
        # Single-user app (handover §3) → one row, id=1.
        c.execute(
            "CREATE TABLE IF NOT EXISTS trakt_tokens "
            "(id INTEGER PRIMARY KEY CHECK (id = 1), access TEXT, refresh TEXT, expires REAL)"
        )


def cache_get(key: str):
    import json
    with db() as c:
        row = c.execute("SELECT value, expires FROM cache WHERE key = ?", (key,)).fetchone()
    if row and row["expires"] > time.time():
        return json.loads(row["value"])
    return None


def cache_set(key: str, value, ttl: float) -> None:
    import json
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time() + ttl),
        )


def excluded_set() -> set[tuple[int, str]]:
    with db() as c:
        return {(r["tmdb_id"], r["type"]) for r in c.execute("SELECT tmdb_id, type FROM excluded")}


# TTLs (seconds) — config-overridable.
_ttl = CONFIG.get("cache", {})
TTL_TITLE = _ttl.get("title_seconds", 24 * 3600)
TTL_RATINGS = _ttl.get("ratings_seconds", 6 * 3600)
TTL_THEME = _ttl.get("theme_seconds", 12 * 3600)


# ---------------------------------------------------------------------------
# Shared async HTTP client (created in lifespan).
# ---------------------------------------------------------------------------
client: httpx.AsyncClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    init_db()
    client = httpx.AsyncClient(timeout=12.0)
    log.info("discov backend up. TMDB=%s MDBList=%s Trakt=%s Seerr=%s",
             bool(settings.tmdb_token), bool(settings.mdblist_api_key),
             bool(settings.trakt_client_id), bool(settings.seerr_api_key))
    yield
    await client.aclose()


app = FastAPI(title="discov", lifespan=lifespan)


# ---------------------------------------------------------------------------
# TMDB — one call per title (append_to_response collapses sub-requests).
# ---------------------------------------------------------------------------
TMDB = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p"


def _tmdb_headers() -> dict:
    return {"Authorization": f"Bearer {settings.tmdb_token}", "accept": "application/json"}


def _pick_trailer(videos: dict) -> Optional[str]:
    """Prefer official YouTube Trailer → any YouTube Trailer → Teaser. Source
    selection is the only lever on trailer quality (you can't trim YouTube)."""
    results = (videos or {}).get("results", [])
    yt = [v for v in results if v.get("site") == "YouTube"]
    for pred in (
        lambda v: v.get("type") == "Trailer" and v.get("official"),
        lambda v: v.get("type") == "Trailer",
        lambda v: v.get("type") == "Teaser",
    ):
        for v in yt:
            if pred(v):
                return v.get("key")
    return yt[0]["key"] if yt else None


async def tmdb_title(tmdb_id: int, mtype: MediaType) -> dict:
    sub = "videos,external_ids,release_dates" if mtype == "movie" else "videos,external_ids,content_ratings"
    r = await client.get(f"{TMDB}/{mtype}/{tmdb_id}", headers=_tmdb_headers(),
                          params={"append_to_response": sub})
    if r.status_code != 200:
        log.error("TMDB %s/%s -> %s %s", mtype, tmdb_id, r.status_code, r.text[:200])
        raise HTTPException(status_code=502, detail=f"TMDB {r.status_code}")
    d = r.json()
    title = d.get("title") or d.get("name") or "?"
    date = d.get("release_date") or d.get("first_air_date") or ""
    poster = d.get("poster_path")
    backdrop = d.get("backdrop_path")
    return {
        "tmdb_id": tmdb_id,
        "type": mtype,
        "title": title,
        "year": int(date[:4]) if date[:4].isdigit() else None,
        "overview": d.get("overview", ""),
        "poster_url": f"{IMG}/w500{poster}" if poster else None,
        "backdrop_url": f"{IMG}/w1280{backdrop}" if backdrop else None,
        "trailer_youtube_key": _pick_trailer(d.get("videos")),
        "imdb_id": (d.get("external_ids") or {}).get("imdb_id"),
    }


async def tmdb_discover(mtype: MediaType, params: dict, cap: int) -> list[dict]:
    """Resolve a generated theme (genre × decade × …) to [{tmdb_id, type}]."""
    q = {"sort_by": "popularity.desc", "vote_count.gte": 50, "include_adult": "false", **params}
    r = await client.get(f"{TMDB}/discover/{mtype}", headers=_tmdb_headers(), params=q)
    if r.status_code != 200:
        log.error("TMDB discover/%s -> %s %s", mtype, r.status_code, r.text[:200])
        return []
    return [{"tmdb_id": x["id"], "type": mtype} for x in r.json().get("results", [])[:cap]]


# ---------------------------------------------------------------------------
# MDBList — ratings (lookup by imdb id, fall back to tmdb).
# ---------------------------------------------------------------------------
MDBLIST = "https://api.mdblist.com"

# MDBList rating `source` -> our chip key. Defensive on the RT-audience naming.
_RATING_MAP = {
    "imdb": "imdb", "tomatoes": "rt_critic", "tomatoesaudience": "rt_audience",
    "audience": "rt_audience", "popcorn": "rt_audience",
    "metacritic": "metacritic", "trakt": "trakt", "letterboxd": "letterboxd",
}


async def mdblist_ratings(imdb_id: Optional[str], tmdb_id: int, mtype: MediaType) -> dict:
    if not settings.mdblist_api_key:
        return {}
    params = {"apikey": settings.mdblist_api_key}
    if imdb_id:
        params["i"] = imdb_id
    else:
        params["tm"] = tmdb_id
        params["m"] = "movie" if mtype == "movie" else "show"
    r = await client.get(f"{MDBLIST}/", params=params)
    if r.status_code != 200:
        log.warning("MDBList %s -> %s %s", imdb_id or tmdb_id, r.status_code, r.text[:120])
        return {}
    out: dict = {}
    for rt in r.json().get("ratings", []) or []:
        key = _RATING_MAP.get(str(rt.get("source", "")).lower())
        if key and rt.get("value") is not None:
            out[key] = rt["value"]
    return out


async def mdblist_list_items(list_id: str, cap: int) -> list[dict]:
    """Resolve a curated MDBList list -> [{tmdb_id, type}]. Verify the path/shape
    against your list on the host — MDBList has shifted these around."""
    r = await client.get(f"{MDBLIST}/lists/{list_id}/items", params={"apikey": settings.mdblist_api_key})
    if r.status_code != 200:
        log.warning("MDBList list %s -> %s %s", list_id, r.status_code, r.text[:120])
        return []
    items = r.json()
    rows = items if isinstance(items, list) else items.get("movies", []) + items.get("shows", [])
    out = []
    for it in rows[:cap]:
        tmdb = it.get("tmdb_id") or it.get("id")
        mt = "tv" if it.get("mediatype") in ("show", "tv") else "movie"
        if tmdb:
            out.append({"tmdb_id": tmdb, "type": mt})
    return out


# ---------------------------------------------------------------------------
# Trakt — public (trending, api-key header only) + user (OAuth: watchlist,
# watched-exclusion, add-to-watchlist). Token store in SQLite, auto-refresh.
# ---------------------------------------------------------------------------
TRAKT = "https://api.trakt.tv"


def _trakt_public_headers() -> dict:
    return {"Content-Type": "application/json", "trakt-api-version": "2",
            "trakt-api-key": settings.trakt_client_id}


def _trakt_tokens() -> Optional[sqlite3.Row]:
    with db() as c:
        return c.execute("SELECT access, refresh, expires FROM trakt_tokens WHERE id = 1").fetchone()


def _store_trakt(access: str, refresh: str, expires_in: int) -> None:
    with db() as c:
        c.execute("INSERT OR REPLACE INTO trakt_tokens (id, access, refresh, expires) VALUES (1, ?, ?, ?)",
                  (access, refresh, time.time() + expires_in))


async def trakt_access_token() -> Optional[str]:
    """Return a valid user access token, refreshing via the stored refresh token
    if it's expired (or near-expiry). None if the user hasn't authed yet."""
    row = _trakt_tokens()
    if not row:
        return None
    if row["expires"] > time.time() + 60:
        return row["access"]
    # Refresh.
    r = await client.post(f"{TRAKT}/oauth/token", json={
        "refresh_token": row["refresh"], "client_id": settings.trakt_client_id,
        "client_secret": settings.trakt_client_secret,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob", "grant_type": "refresh_token"})
    if r.status_code != 200:
        log.error("Trakt token refresh -> %s %s", r.status_code, r.text[:200])
        return None
    t = r.json()
    _store_trakt(t["access_token"], t["refresh_token"], t.get("expires_in", 7776000))
    log.info("Trakt token refreshed.")
    return t["access_token"]


async def _trakt_user_headers() -> Optional[dict]:
    tok = await trakt_access_token()
    if not tok:
        return None
    return {**_trakt_public_headers(), "Authorization": f"Bearer {tok}"}


async def trakt_trending(mtype: MediaType, cap: int) -> list[dict]:
    path = "movies" if mtype == "movie" else "shows"
    r = await client.get(f"{TRAKT}/{path}/trending", headers=_trakt_public_headers(), params={"limit": cap})
    if r.status_code != 200:
        log.warning("Trakt trending %s -> %s", mtype, r.status_code)
        return []
    out = []
    for x in r.json():
        node = x.get("movie") or x.get("show") or {}
        tmdb = (node.get("ids") or {}).get("tmdb")
        if tmdb:
            out.append({"tmdb_id": tmdb, "type": mtype})
    return out


async def trakt_watchlist() -> list[dict]:
    h = await _trakt_user_headers()
    if not h:
        return []
    out = []
    for mtype, path in (("movie", "movies"), ("tv", "shows")):
        r = await client.get(f"{TRAKT}/sync/watchlist/{path}", headers=h)
        if r.status_code == 200:
            for x in r.json():
                node = x.get("movie") or x.get("show") or {}
                tmdb = (node.get("ids") or {}).get("tmdb")
                if tmdb:
                    out.append({"tmdb_id": tmdb, "type": mtype})
    return out


async def trakt_watched_ids() -> set[tuple[int, str]]:
    """The watched exclusion set. Cached — refreshed periodically, not per-request."""
    cached = cache_get("trakt:watched")
    if cached is not None:
        return {(i, t) for i, t in cached}
    h = await _trakt_user_headers()
    if not h:
        return set()
    out: set[tuple[int, str]] = set()
    for mtype, path in (("movie", "movies"), ("tv", "shows")):
        r = await client.get(f"{TRAKT}/sync/watched/{path}", headers=h)
        if r.status_code == 200:
            for x in r.json():
                node = x.get("movie") or x.get("show") or {}
                tmdb = (node.get("ids") or {}).get("tmdb")
                if tmdb:
                    out.add((tmdb, mtype))
    cache_set("trakt:watched", [list(t) for t in out], TTL_THEME)
    return out


# ---------------------------------------------------------------------------
# Tile contract — merge TMDB + MDBList into the ONE shape the frontend knows.
# ---------------------------------------------------------------------------
async def build_tile(tmdb_id: int, mtype: MediaType) -> dict:
    ckey = f"title:{mtype}:{tmdb_id}"
    cached = cache_get(ckey)
    if cached:
        return cached
    base = await tmdb_title(tmdb_id, mtype)
    ratings = await mdblist_ratings(base.pop("imdb_id", None), tmdb_id, mtype)
    tile = {
        "tmdb_id": base["tmdb_id"], "type": base["type"], "title": base["title"],
        "year": base["year"], "overview": base["overview"],
        "poster_url": base["poster_url"], "backdrop_url": base["backdrop_url"],
        "trailer_youtube_key": base["trailer_youtube_key"],
        "ratings": ratings, "awards": None, "requested": False,
    }
    cache_set(ckey, tile, TTL_TITLE)
    return tile


# ---------------------------------------------------------------------------
# Theme engine — generated (↑/↓ reel) + standard (nav bar). Both post-filtered
# by watched ∪ excluded before serving.
# ---------------------------------------------------------------------------
def _decade_params(decade: int) -> dict:
    return {"primary_release_date.gte": f"{decade}-01-01", "primary_release_date.lte": f"{decade + 9}-12-31",
            "first_air_date.gte": f"{decade}-01-01", "first_air_date.lte": f"{decade + 9}-12-31"}


async def generated_themes(n: int, cap: int) -> list[dict]:
    """Random session pool from TMDB Discover dimensions (config-driven). This is
    the 'fake infinite' vertical axis."""
    gen = CONFIG.get("generated", {})
    genres: dict = gen.get("genres", {})            # {label: tmdb_genre_id}
    decades: list[int] = gen.get("decades", [])
    themes = []
    keys = list(genres.keys())
    random.shuffle(keys)
    for label in keys[:n]:
        gid = genres[label]
        params = {"with_genres": str(gid)}
        title = label
        if decades and random.random() < 0.5:
            dec = random.choice(decades)
            params = {**params, **_decade_params(dec)}
            title = f"{dec}s {label}"
        mtype: MediaType = random.choice(["movie", "tv"])
        themes.append({"id": f"gen:{title}", "label": title, "mtype": mtype, "params": params})
    return themes


async def resolve_standard(theme: dict, cap: int) -> list[dict]:
    src = theme.get("source")
    if src == "trakt_trending":
        return await trakt_trending(theme.get("mtype", "movie"), cap)
    if src == "trakt_watchlist":
        return await trakt_watchlist()
    if src == "mdblist":
        return await mdblist_list_items(theme["list_id"], cap)
    if src == "tmdb_discover":
        return await tmdb_discover(theme.get("mtype", "movie"), theme.get("params", {}), cap)
    return []


def _filter(ids: list[dict], block: set[tuple[int, str]]) -> list[dict]:
    return [x for x in ids if (x["tmdb_id"], x["type"]) not in block]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class ActionBody(BaseModel):
    tmdb_id: int
    type: MediaType


@app.get("/api/health")
async def health():
    out = {}
    checks = {
        "tmdb": (f"{TMDB}/configuration", _tmdb_headers()),
        "trakt": (f"{TRAKT}/movies/trending?limit=1", _trakt_public_headers()),
        "mdblist": (f"{MDBLIST}/?apikey={settings.mdblist_api_key}&i=tt0903747", {}),
        "seerr": (f"{settings.seerr_base}/api/v1/status", {"X-Api-Key": settings.seerr_api_key}),
    }
    for name, (url, headers) in checks.items():
        try:
            r = await client.get(url, headers=headers)
            out[name] = r.status_code
        except Exception as e:  # noqa: BLE001
            out[name] = f"err: {e}"
    return out


@app.get("/api/title/{tmdb_id}")
async def get_title(tmdb_id: int, type: MediaType = "movie"):
    return await build_tile(tmdb_id, type)


@app.get("/api/themes")
async def get_themes(limit: int = 10):
    cap = CONFIG.get("themes", {}).get("titles_per_theme", 30)
    block = excluded_set() | await trakt_watched_ids()

    standard = CONFIG.get("standard_themes", [])
    generated = await generated_themes(limit, cap)

    out = []
    # Nav-bar standard themes (resolved to first-title preview; rest lazy on the client).
    nav = []
    for th in standard:
        ids = _filter(await resolve_standard(th, cap), block)
        nav.append({"id": th.get("id", th.get("label")), "label": th["label"], "titles": ids})

    # ↑/↓ generated reel.
    for th in generated:
        ids = _filter(await tmdb_discover(th["mtype"], th["params"], cap), block)
        if ids:
            out.append({"id": th["id"], "label": th["label"], "titles": ids})

    return {"nav": nav, "reel": out}


@app.post("/api/exclude")
async def exclude(b: ActionBody):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO excluded (tmdb_id, type, added) VALUES (?, ?, ?)",
                  (b.tmdb_id, b.type, time.time()))
    return {"ok": True}


@app.post("/api/watchlist")
async def add_watchlist(b: ActionBody):
    h = await _trakt_user_headers()
    if not h:
        raise HTTPException(status_code=401, detail="Trakt not authorised — run device flow")
    key = "movies" if b.type == "movie" else "shows"
    r = await client.post(f"{TRAKT}/sync/watchlist", headers=h,
                          json={key: [{"ids": {"tmdb": b.tmdb_id}}]})
    if r.status_code not in (200, 201):
        log.error("Trakt add watchlist -> %s %s", r.status_code, r.text[:200])
        raise HTTPException(status_code=502, detail="Trakt watchlist failed")
    return {"ok": True}


@app.post("/api/request")
async def request_title(b: ActionBody):
    body = {"mediaType": b.type, "mediaId": b.tmdb_id}
    if b.type == "tv":
        body["seasons"] = "all"
    r = await client.post(f"{settings.seerr_base}/api/v1/request",
                          headers={"X-Api-Key": settings.seerr_api_key}, json=body)
    if r.status_code == 409:
        return {"ok": True, "already": True}   # already requested/available — not an error
    if r.status_code not in (200, 201):
        log.error("Seerr request -> %s %s", r.status_code, r.text[:200])
        raise HTTPException(status_code=502, detail="Seerr request failed")
    return {"ok": True}


# --- Trakt one-time device-flow auth (run once on the host; tokens -> SQLite) ---
@app.post("/api/trakt/device")
async def trakt_device():
    r = await client.post(f"{TRAKT}/oauth/device/code", json={"client_id": settings.trakt_client_id})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Trakt device code {r.status_code}")
    return r.json()  # {device_code, user_code, verification_url, interval, expires_in}


@app.post("/api/trakt/device/poll")
async def trakt_device_poll(device_code: str):
    r = await client.post(f"{TRAKT}/oauth/device/token", json={
        "code": device_code, "client_id": settings.trakt_client_id,
        "client_secret": settings.trakt_client_secret})
    if r.status_code == 200:
        t = r.json()
        _store_trakt(t["access_token"], t["refresh_token"], t.get("expires_in", 7776000))
        return {"ok": True, "authorised": True}
    return JSONResponse({"ok": False, "pending": r.status_code}, status_code=202)


# Static single-file frontend LAST so /api/* wins. Step 2 replaces web/index.html.
app.mount("/", StaticFiles(directory=str(APP_DIR / "web"), html=True), name="web")
