# Combined Bot (Anime Discord + Finance LINE + Dashboard API)

A single **FastAPI** app is the only web server. It:

- serves the **LINE webhook** (`/webhook`) and health endpoints,
- runs the **Discord anime bot** as an asyncio task on the same event loop,
- runs the **finance weekly scheduler** (APScheduler) in a background thread, and
- serves the **dashboard API** under `/api/*`.

## Structure

```
main.py               FastAPI app + lifespan that starts Discord + both schedulers
setup_db.py           One-off script: create collections/indexes, seed watchlist
frontend/             Vite + React + Tailwind dashboard (source)
static/               Built dashboard, served at / — commit this, Render can't build it

anime/                Discord anime-notify bot (behaviour unchanged from the original)
  bot.py              commands, 10-min episode-check scheduler, health status
  anime_checker.py    AniList GraphQL queries
  database.py         MongoDB connection + `subscriptions` CRUD (reads MONGO_URI)

finance/              LINE finance bot
  brief.py            fetch stock -> fetch news -> summarize -> send
  summarizer.py       Gemini generateContent call + deterministic no-LLM fallback
  scheduler.py        weekly cron (Mon 10:00 Asia/Bangkok) -> push LINE message
  line_client.py      LINE Messaging API wrapper
  watchlist.py        DB-backed stock watchlist (seeded from STOCK_SYMBOLS)
  config.py           settings (env-driven)
  services/           Yahoo Finance quotes + NewsAPI headlines + symbol resolution

web/                  Dashboard API (single user, no auth)
  routes_anime.py     /api/anime/*
  routes_stocks.py    /api/stocks/*
  anime_service.py    AniList batch fetch + grouping + watch progress
  stock_service.py    EMA, dashboard rows, chart ranges, profile, news
  cache.py            MongoDB TTL cache
  db.py               dashboard collections + index creation
```

## Dashboard API

Single user, no authentication. All responses are JSON.

### Anime

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/anime` | All tracked anime, grouped and sorted |
| `GET` | `/api/anime/search?q=` | Search AniList by title, or fetch by numeric id |
| `POST` | `/api/anime` | Subscribe — body `{anime_id, title?}` |
| `DELETE` | `/api/anime` | Unsubscribe many — body `{anime_ids: [...]}` |
| `GET` | `/api/anime/platforms` | Streaming-service catalogue for the "watching on" dropdown |
| `PUT` | `/api/anime/{id}/progress` | Set watched episode — body `{watched_episode}` |
| `PUT` | `/api/anime/{id}/platform` | Set streaming platform — body `{platform}` |
| `PUT` | `/api/anime/{id}/offset` | Set release delay — body `{offset_minutes}`, ±1440 |

`GET /api/anime` returns `{"groups": {on_air, finished_watching, finished_done}}`.
Each item carries `title`, `cover_image`, `total_episodes`, `latest_episode`,
`latest_episode_at`, `next_episode`, `watched_episode`, `platforms[]`, `platform`,
`offset_minutes`.

`platforms[]` is only what AniList *suggests*, which often misses the service a
title actually airs on in a given region. `/api/anime/platforms` returns the full
catalogue so any service can be selected; the UI merges the two.

`offset_minutes` writes to `subscriptions.offset_minutes` — the same field
Discord's `/setoffset` uses — so bot notifications and the dashboard countdown
stay in agreement. It is the one dashboard field that changes bot behaviour.

**Grouping rule** — decided by whether a next episode exists, *not* by AniList's
`status` field (which avoids CANCELLED/HIATUS edge cases):

```
has nextAiringEpisode?
  yes -> on_air              (watch progress is irrelevant here)
  no  -> watched >= total ?  finished_done : finished_watching
```

Items are sorted by `latest_episode_at` descending (newest release first) before
being split into groups, so each group is independently sorted.

### Stocks

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/stocks` | Watchlist dashboard: last session OHLC, change %, EMA |
| `POST` | `/api/stocks` | Add symbol — body `{symbol}` (accepts aliases: `nvidia` → `NVDA`) |
| `DELETE` | `/api/stocks/{symbol}` | Remove symbol |
| `GET` | `/api/stocks/{symbol}?range=` | Detail for the drawer: price, stats, candles |
| `GET` | `/api/stocks/{symbol}/news` | Company headlines (returns `[]` if unavailable) |

EMA windows are **trading days**: `week_1`=5, `week_2`=10, `month_1`=21.

Chart ranges → intervals: `1d`→5m, `5d`→30m, `1mo`/`6mo`/`ytd`/`1y`→1d,
`5y`→1wk, `max`→1mo.

### Where prices come from

`finance/services/market_data.py` tries two providers and normalises both to the
same candle shape:

1. **Yahoo** chart endpoint — no key, richest data, used whenever it answers.
2. **Twelve Data** — free API key, used when Yahoo refuses.

Yahoo rate-limits **by IP**, and Render's egress addresses are shared with
thousands of other services, so in production every Yahoo request returns HTTP
429 while the identical request from a home connection succeeds. Headers and
retries make no difference — it is the address, not the request.

After one 429 the module stops calling Yahoo for 30 minutes (process-local), so
production settles on Twelve Data without paying a timeout per symbol, while
local development keeps using Yahoo. A restart re-probes, in case the block lifts.

Without `TWELVEDATA_API_KEY` the finance tab and the weekly LINE brief both fail
on Render — the error names the missing key.

The 52-week range costs one extra Twelve Data request, so it is only fetched for
the detail drawer (`range=1d`/`5d`), never for the dashboard.

### Other

`GET /health` (uptime pinger), `GET /health/anime` (detailed bot status),
`POST /webhook` (LINE), `POST /trigger` (manually fire the weekly brief).

`GET /` serves the dashboard SPA from `static/` when it has been built.

## Data model (MongoDB)

| Collection | Owner | Notes |
|---|---|---|
| `subscriptions` | Discord bot | **Schema never changed.** `last_episode` = latest episode the bot *notified about* |
| `watch_progress` | dashboard | `{anime_id, watched_episode, platform, updated_at}` |
| `stock_watchlist` | dashboard | `{symbol, added_at}` — seeded from `STOCK_SYMBOLS` |
| `cache` | dashboard | `{key, value, expires_at}` with a TTL index |

> **Important invariant:** `watch_progress.watched_episode` and
> `subscriptions.last_episode` are deliberately separate. Writing watch progress
> into `last_episode` would make the bot re-notify every past episode (on reset)
> or go silent (on "mark finished"). Never merge them.

Collections and indexes are created automatically at startup by
`web.db.ensure_indexes()`. Run `python setup_db.py` to do it ahead of a deploy
and print a report — it only reads `subscriptions` and verifies the count is
unchanged before exiting.

Cache TTLs: intraday charts 60 s, daily charts 15 min, company profile 24 h,
news 6 h. These exist mainly to protect NewsAPI's ~100 requests/day free tier.

## What changed vs. the two original projects

- **Anime bot**: behaviour identical. Only the web server was removed
  (`keep_alive.py`) — FastAPI now provides `/health` and `/health/anime`.
  The unused `IPython` import/dependency was dropped.
- **Finance bot**: the LangChain / LangGraph / LangSmith stack was **removed**
  to cut memory use (it was the heaviest thing in the app). The message content
  is still generated by **Gemini**, but via a direct REST call to the Google
  Generative Language API (`finance/summarizer.py`) instead of LangChain.
  Stock/analyst/financial data still comes from **Yahoo Finance** and headlines
  from **NewsAPI** — those services are unchanged. If `GEMINI_API_KEY` is unset
  or Gemini fails, it falls back to a deterministic Thai brief built from the raw data.
- **Moving-average fix**: quotes were fetched with `range=5d`, so the reported
  "20-day" and "50-day" averages were both really 5-day averages and always
  identical. History is now `3mo`, and an average is reported only when there is
  enough data for it (otherwise `None`). Support/resistance is a real 20-session range.
- **Stock watchlist moved from env var to MongoDB** so the dashboard can edit it.
  `STOCK_SYMBOLS` now only *seeds* an empty collection on first run.
- **pymongo** bumped 3.12 → 4.8 (old `[srv]` extra conflicted with FastAPI's
  dnspython requirement); `dnspython` is now listed explicitly for Atlas URIs.

## Environment variables

See `.env.example`. Required in production:

| Variable | Used by |
|---|---|
| `DISCORD_TOKEN` | anime bot |
| `MONGO_URI` | everything (note: the code reads `MONGO_URI`, not `MONGODB_URI`) |
| `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID` | finance bot |
| `GEMINI_API_KEY` | finance message generation |
| `NEWSAPI_KEY` | finance news |
| `TWELVEDATA_API_KEY` | stock prices — **required in production**, see below |

Optional (have defaults): `GEMINI_MODEL`, `SCHEDULE_*`, `TIMEZONE`, `NEWS_QUERY`.

`STOCK_SYMBOLS` seeds the watchlist on first run only; after that the database
is the source of truth and editing the env var has no effect.

`DISCORD_GUILD_ID` / `DISCORD_CHANNEL_ID` are only needed if you subscribe from
the web while **zero** subscriptions exist — normally the target is copied from
an existing subscription.

> The whole app imports `anime/` at startup, and `database.py` requires
> `MONGO_URI` to be set even before the Discord bot starts. Set it in Render.

## Run locally

### First-time setup

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

Then copy `.env.example` to `.env` and fill in the values.

### Start the backend (development)

```bash
.venv/Scripts/python -m uvicorn main:app --reload --port 8080
```

Calling `.venv/Scripts/python` directly avoids activating the virtualenv, which
sidesteps PowerShell's execution-policy prompt. `--reload` restarts on save —
leave it off in production.

| URL | |
|---|---|
| `http://localhost:8080` | dashboard (served from `static/`) |
| `http://localhost:8080/docs` | interactive API docs |
| `http://localhost:8080/health` | liveness check |

> **Running locally starts the real Discord bot.** With a live `DISCORD_TOKEN`
> in `.env` it connects, answers slash commands and *sends episode
> notifications* — so while the Render service is also running you get two bots
> replying and duplicate alerts. To work on the API or UI only, blank the token:
>
> ```
> DISCORD_TOKEN=
> ```
>
> `main.py` skips the bot when it is empty; the API and schedulers still run.

### Build the frontend

```bash
cd frontend && npm install && npm run build
```

Outputs to `../static/`, which the backend serves at `/`. Re-run after any
frontend change — the dev server does not rebuild it. See
[Frontend](#frontend) for why `static/` is committed.

### Database setup script

`setup_db.py` needs only the light dependencies, not the full stack:

```bash
.venv/Scripts/python -m pip install pymongo dnspython pydantic-settings python-dotenv
```

```bash
.venv/Scripts/python setup_db.py
```

## Frontend

**Vite + React + Tailwind v4**, built to `static/` and served by this same
FastAPI app, so it stays **one Render service**. Not Next.js — that needs a live
Node server, which would mean a second service and blow the free-tier budget.

```
frontend/
  src/index.css         Design tokens (@theme) — the source of truth for BOTH tabs
  src/App.jsx           Shell: header, tab nav, hash router
  src/lib/              api.js (fetch wrappers), format.js, hooks.js
  src/components/       Shared primitives: Button, Input, Overlay, Feedback, Toast
  src/anime/            AnimePage, AnimeCard, EpisodePicker, AddAnimeDialog
  src/finance/          FinancePage, StockTable, StockDrawer, PriceChart
```

### Build

Node is not reliably available on Render's Python runtime, so **build locally
and commit `static/`**:

```bash
cd frontend && npm install && npm run build   # outputs to ../static
```

If `static/index.html` is missing, `GET /` falls back to the old JSON service
descriptor and the API keeps working — the dashboard is simply absent.

For local development, run the API on `:8080` and the Vite dev server
separately; `vite.config.js` proxies `/api` to it:

```bash
cd frontend && npm run dev     # http://localhost:5173
```

### Routing

Navigation is **hash-based** (`#/anime`, `#/anime/21`, `#/finance`,
`#/finance/NVDA`). The server is therefore only ever asked for `/`, which means
**no SPA catch-all route exists at all** — `/api`, `/webhook` and `/health` can
never be shadowed. The mount is still registered last in `main.py`. Open drawers
and episode pickers are in the URL, so every view is deep-linkable.

### Design system

One token set drives both tabs — same surfaces, radii, motion curves and type
scale; only content density differs. Dark-mode only, deep navy rather than pure
black. Fira Sans for prose, Fira Code (tabular figures) for every number that
sits in a column: prices, EMA values, episode numbers, countdowns.

Two conventions worth knowing:

- **Episode progress is a high-water mark.** `watched_episode` is a single
  integer, so the picker means "watched *through* episode N" — the AniList/MAL
  model — not an arbitrary set of ticked episodes. Tapping the current mark
  steps back by one. Writes are debounced ~400 ms and flushed on close.
- **Reversible deletes get undo; irreversible ones get a confirm.** Removing a
  stock is undoable from the toast (re-adding restores it). Removing an anime
  also drops its `watch_progress`, which cannot be restored, so it asks first.

EMA overlays on the detail chart are shown **only** on ranges that use daily
candles (`1mo`/`6mo`/`ytd`/`1y`). The windows are defined in trading days, so on
5-minute or weekly bars "EMA 5" would silently mean something else.

`.claude/skills/` contains the ui-ux-pro-max skill set used for this work.

## Deploy on Render

1. Push this folder to a repo (or point Render at it via `render.yaml`).
2. Create **one** free Web Service. Build: `pip install -r requirements.txt`.
   Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
3. Add the environment variables above.
4. Point your LINE channel webhook at `https://<service>.onrender.com/webhook`.
5. Allow `0.0.0.0/0` in MongoDB Atlas Network Access — Render's egress IP is not static.

### Keeping it awake

Render's free tier sleeps a service after ~15 min with no HTTP traffic, which
would stop both the Discord connection and the Monday-10:00 finance cron. Add an
external uptime pinger (e.g. UptimeRobot / cron-job.org) hitting
`https://<service>.onrender.com/health` every ~10 minutes.

One always-on service ≈ 730 h/month, under the 750 h free cap — but with little
headroom, so don't run a second free service on the same account alongside it.
