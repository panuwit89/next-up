# NextUp

A personal tracker for the two things I check every day: **which anime episode
is out**, and **what my stocks did**.

The same data reaches me three ways — a Discord bot that pings a channel when an
episode drops, a LINE bot that sends a weekly market brief written by an LLM, and
a web dashboard for browsing both. All three are one Python process, deployed as
a single service.

> **Why one process?** Render's free tier allows 750 instance-hours a month.
> One always-on service uses ~730. Two use ~1,460 and get suspended halfway
> through the month — which is exactly what happened before these were merged.

---

## What it does

### 📺 Anime notifications (Discord)

Subscribe to a show and the bot posts to your channel when a new episode airs.
It polls [AniList](https://anilist.co) every 10 minutes and only announces
episodes it hasn't announced before.

| Command | What it does |
|---|---|
| `/subscribe <query \| anime_id>` | Search by title and pick from a dropdown, or subscribe by AniList ID |
| `/unsubscribe <anime_id>` | Stop tracking a show |
| `/list` | Everything you track, with the next airing time for each |
| `/onair [limit]` | Currently airing shows, best-rated first |
| `/episodes <anime_id>` | How many episodes have aired, plus the five most recent |
| `/setoffset <anime_id> <minutes>` | Delay notifications for shows that reach your streaming service late |

**About `/setoffset`:** AniList lists the *Japanese broadcast* time. If a show
appears on your streaming service an hour later, `/setoffset <id> 60` shifts both
the notification and the countdown shown everywhere else.

### 💹 Market brief (LINE)

**Every Monday at 10:00** (Asia/Bangkok) the bot pushes a brief covering your
watchlist. Each entry is built from real data — never generated from memory:

- **Prices** — last close, % change, 20-day support/resistance, 20/50-day
  moving averages
- **Fundamentals** — latest quarterly revenue and net income with % change
- **Analyst view** — consensus rating, mean/high/low target, number of analysts
- **News** — recent headlines for that specific company

Those figures go to **Gemini**, which writes a short Thai summary with a fixed
set of rules: bullet points, grouped by company, no invented numbers, no buy/sell
advice, and a closing risk note. If the LLM is unavailable the bot falls back to
a deterministic Thai summary assembled directly from the same data, so a brief
always arrives.

**You can also just message it.** Send `NVDA` or `tsmc` and it replies with a
brief for that symbol on the spot. Send `id` and it replies with your LINE user
ID — handy during setup, since that value is needed for scheduled pushes.

### 🖥️ Dashboard (web)

Single-user, no login. Two tabs sharing one design system.

**Anime tab** — a poster grid split into three sections:

1. **On Air** — has a next episode scheduled
2. **Catching Up** — finished airing, still episodes left to watch
3. **Completed** — finished airing, watched to the end

Click a card to open the episode picker: tap episode *N* to mark everything
through *N* as watched, tap it again to step back one. Progress saves
automatically. You can also set which service you actually watch on and adjust
the airing offset here.

**Finance tab** — a table of prices, % change, and EMA over 5, 10 and 21 trading
days. Click a row for a drawer with an interactive price chart (1D through Max),
open/high/low, 52-week range, and company news. Symbols added here also change
what the Monday LINE brief covers.

---

## How it fits together

```
                    ┌──────────────────────────────┐
   Discord  ◀──────▶│                              │
   gateway          │      FastAPI (one process)   │◀──── browser
                    │                              │
   LINE     ──────▶ │  /webhook   /api/*   /       │
   webhook          └───────────────┬──────────────┘
                                    │
                    ┌───────────────┴──────────────┐
                    │  MongoDB Atlas               │
                    │  AniList · Yahoo · Twelve    │
                    │  Data · NewsAPI · Gemini     │
                    └──────────────────────────────┘
```

The Discord bot holds a WebSocket to Discord's gateway, so it can't run on
serverless — but it doesn't need an inbound port either. The LINE webhook does.
FastAPI provides the port, the Discord bot rides along as an asyncio task on the
same event loop, and two schedulers run alongside: a 10-minute episode check and
a weekly cron for the brief.

### Provider fallback for prices

Yahoo Finance rate-limits **by IP**, and cloud hosts share egress addresses with
thousands of other services. In practice every Yahoo request from the deployed
app returns HTTP 429 while the identical request from a home connection
succeeds — headers and retries make no difference.

So `finance/services/market_data.py` tries Yahoo, and on a 429 switches to
**Twelve Data** and stops asking Yahoo for 30 minutes. Local development keeps
using Yahoo; production settles on the fallback after one failed attempt. Both
providers are normalised to the same candle shape, so nothing downstream knows
which one answered.

---

## Project layout

```
main.py               FastAPI app. Starts the Discord bot, both schedulers,
                      mounts the API routers and serves the built dashboard.
setup_db.py           One-off: create collections/indexes, seed the watchlist,
                      print a report. Only reads `subscriptions`.

anime/                Discord bot — behaviour unchanged from the original project
  bot.py              6 slash commands, 10-minute episode check, health status
  anime_checker.py    AniList GraphQL queries
  database.py         MongoDB connection + `subscriptions` CRUD

finance/              LINE bot
  brief.py            fetch prices → fetch news → summarise → send
  summarizer.py       Gemini REST call, plus the no-LLM fallback summary
  scheduler.py        weekly cron (Mon 10:00 Asia/Bangkok)
  line_client.py      LINE Messaging API wrapper (push, reply, verify signature)
  watchlist.py        DB-backed stock watchlist
  config.py           env-driven settings
  services/
    market_data.py    price history: Yahoo → Twelve Data fallback
    stock_quotes.py   quotes + fundamentals + analyst data for the brief
    news.py           NewsAPI headlines
    symbols.py        ticker aliases, company names, news query building

web/                  Dashboard API (single user, no auth)
  routes_anime.py     /api/anime/*
  routes_stocks.py    /api/stocks/*
  anime_service.py    AniList batch fetch, grouping, watch progress
  stock_service.py    EMA, dashboard rows, chart ranges, profile, news
  cache.py            MongoDB TTL cache
  db.py               dashboard collections + index creation

frontend/             Vite + React + Tailwind v4 (source)
  src/index.css       design tokens — the single source of truth for both tabs
  src/App.jsx         shell: header, tab nav, hash router
  src/lib/            api.js (fetch wrappers), format.js, hooks.js
  src/components/     Button, Input, Overlay, Feedback, Toast, Logo
  src/anime/          AnimePage, AnimeCard, EpisodePicker, AddAnimeDialog
  src/finance/        FinancePage, StockTable, StockDrawer, PriceChart

static/               Built dashboard — committed on purpose, see below
```

### Why `static/` is committed

Render's Python runtime has no Node, so the frontend can't be built during
deploy. It's built locally and the output committed. Re-run after any frontend
change:

```bash
cd frontend && npm install && npm run build
```

---

## Data model (MongoDB)

| Collection | Written by | Contents |
|---|---|---|
| `subscriptions` | Discord bot | `guild_id`, `channel_id`, `anime_id`, `anime_title`, `last_episode`, `offset_minutes` |
| `watch_progress` | dashboard | `anime_id`, `watched_episode`, `platform`, `updated_at` |
| `stock_watchlist` | dashboard | `symbol`, `added_at` |
| `cache` | dashboard | `key`, `value`, `expires_at` (TTL index) |

> **One rule worth knowing before changing anything here.**
> `subscriptions.last_episode` means *"the latest episode the bot has already
> announced"* — it is not watch progress. `watch_progress.watched_episode` is.
> Merging them breaks the bot in both directions: resetting progress makes it
> re-announce every past episode, and marking a show finished makes it go
> silent. They stay separate on purpose.

Collections and indexes are created at startup, or ahead of time with
`python setup_db.py`.

---

## API

Single user, no authentication. All JSON.

**Anime** — `GET /api/anime` (grouped list) · `GET /api/anime/search?q=` ·
`GET /api/anime/platforms` · `POST /api/anime` · `DELETE /api/anime` ·
`PUT /api/anime/{id}/progress` · `PUT /api/anime/{id}/platform` ·
`PUT /api/anime/{id}/offset`

**Stocks** — `GET /api/stocks` · `POST /api/stocks` · `DELETE /api/stocks/{symbol}` ·
`GET /api/stocks/{symbol}?range=` · `GET /api/stocks/{symbol}/news`

**Other** — `GET /health` (uptime pinger) · `GET /health/anime` (bot status) ·
`POST /webhook` (LINE) · `POST /trigger` (fire the weekly brief manually)

Interactive docs at `/docs` when running.

EMA windows are trading days: 5, 10, 21. Chart ranges map `1d`→5m, `5d`→30m,
`1mo`/`6mo`/`ytd`/`1y`→1d, `5y`→1wk, `max`→1mo.

---

## Running it

### Setup

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill it in.

### Start

```bash
.venv/Scripts/python -m uvicorn main:app --reload --port 8080
```

Dashboard at `http://localhost:8080`, API docs at `/docs`.

> **Running locally starts the real Discord bot.** With a live `DISCORD_TOKEN`
> it connects, answers commands and sends notifications — so while a deployed
> copy is also running you get duplicates. To work on the API or UI only, leave
> `DISCORD_TOKEN=` empty; everything else still runs.

### Environment variables

| Variable | Used by |
|---|---|
| `DISCORD_TOKEN` | Discord bot |
| `MONGO_URI` | everything (note: `MONGO_URI`, not `MONGODB_URI`) |
| `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_USER_ID` | LINE bot |
| `GEMINI_API_KEY` | brief summarisation |
| `NEWSAPI_KEY` | headlines |
| `TWELVEDATA_API_KEY` | prices — required in production, see the fallback note above |

Optional: `GEMINI_MODEL`, `SCHEDULE_DAY_OF_WEEK` / `SCHEDULE_HOUR` /
`SCHEDULE_MINUTE`, `TIMEZONE`, `NEWS_QUERY`.

`STOCK_SYMBOLS` seeds the watchlist on first run only — after that the database
is the source of truth. `DISCORD_GUILD_ID` / `DISCORD_CHANNEL_ID` are needed
only to subscribe from the web while zero subscriptions exist; normally the
target is copied from an existing one.

Paste values **without quotes**. `python-dotenv` strips them from a `.env` file,
but a hosting dashboard passes whatever was typed — a quoted key produced a
production-only 401 once. Settings now strips them defensively.

---

## Deploying

1. Push to a repo and create **one** free Web Service on Render.
2. Build `pip install -r requirements.txt`, start
   `uvicorn main:app --host 0.0.0.0 --port $PORT`.
3. Add the environment variables above.
4. Point the LINE channel webhook at `https://<service>.onrender.com/webhook`.
5. Allow `0.0.0.0/0` in MongoDB Atlas network access — Render's egress IP isn't static.
6. Add an uptime pinger (UptimeRobot, cron-job.org) hitting
   `https://<service>.onrender.com/health` every ~10 minutes.

Step 6 matters: the free tier sleeps a service after 15 minutes without traffic,
which drops the Discord connection and stops both schedulers.

One always-on service is ~744 hours in a 31-day month against a 750-hour cap.
It fits, but there's no room for a second free service alongside it.

---

## Notes

- **Episode counts** — AniList leaves `episodes` empty for some currently-airing
  shows. The dashboard falls back to the number aired, so a show can read
  "5 episodes" while episode 6 is scheduled.
- **Market cap and P/E** are blank in production: they come from a Yahoo
  endpoint that the price fallback doesn't cover, and it's rate-limited from
  cloud IPs like the rest.
- **Free tier limits worth respecting** — NewsAPI ~100 requests/day, Twelve Data
  ~800/day and 8/minute. The TTL cache exists mainly to stay under them.
