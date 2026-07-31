from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from linebot.v3.exceptions import InvalidSignatureError
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from anime.bot import bot as anime_bot, get_health_status as anime_health_status
from finance.brief import run_ondemand_brief, run_weekly_company_brief
from finance.line_client import LineClient
from finance.scheduler import create_scheduler
from web.db import ensure_indexes
from web.routes_anime import router as anime_router
from web.routes_stocks import router as stocks_router


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("combined_bot")


class TriggerRequest(BaseModel):
    query: str | None = None


USER_ID_COMMANDS = {
    "id",
    "user id",
    "userid",
    "line user id",
    "line_user_id",
}


async def _run_discord_bot(token: str) -> None:
    """Run the Discord anime bot on the FastAPI event loop.

    A crash here is logged but must NOT take down the LINE webhook / finance side.
    """
    try:
        await anime_bot.start(token)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Anime Discord bot stopped unexpectedly.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dashboard collections: unique keys plus the TTL index that expires cache.
    try:
        ensure_indexes()
    except Exception:
        logger.exception("Could not create dashboard indexes — the API may be slower.")

    # Finance weekly scheduler runs in its own background thread.
    finance_scheduler = create_scheduler()
    finance_scheduler.start()
    app.state.finance_scheduler = finance_scheduler
    logger.info("Finance scheduler started (weekly LINE brief).")

    # Discord anime bot runs as a task on this event loop; its own 10-min
    # AsyncIOScheduler is started inside on_ready() -> ensure_scheduler_running().
    discord_task: asyncio.Task | None = None
    token = os.getenv("DISCORD_TOKEN")
    if token:
        discord_task = asyncio.create_task(_run_discord_bot(token))
        logger.info("Anime Discord bot task created.")
    else:
        logger.warning("DISCORD_TOKEN not set — anime bot is disabled for this run.")

    try:
        yield
    finally:
        finance_scheduler.shutdown(wait=False)
        if discord_task is not None:
            try:
                await anime_bot.close()
            except Exception:
                logger.exception("Error while closing the anime Discord bot.")
            discord_task.cancel()


app = FastAPI(title="Combined Bot (Anime + Finance)", lifespan=lifespan)
line_client = LineClient()

# Dashboard API. Registered before any future static-file mount so the SPA
# catch-all can never swallow /api, /webhook or /health.
app.include_router(anime_router)
app.include_router(stocks_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple always-200 endpoint for the external uptime pinger."""
    return {"status": "ok"}


@app.get("/health/anime")
async def health_anime() -> dict[str, Any]:
    """Detailed anime-bot status (equivalent to the old keep_alive /health)."""
    return anime_health_status()


@app.post("/trigger")
async def trigger(payload: TriggerRequest | None = None) -> dict[str, Any]:
    """Manually fire the finance weekly brief (useful for testing the schedule)."""
    query = payload.query if payload else None
    summary = await run_in_threadpool(run_weekly_company_brief, query)
    return {"status": "completed", "summary": summary}


@app.post("/webhook")
async def webhook(request: Request) -> dict[str, Any]:
    signature = request.headers.get("x-line-signature")
    body = await request.body()

    try:
        events = line_client.parse_webhook_events(body, signature)
    except InvalidSignatureError as exc:
        logger.warning("Rejected webhook request with invalid LINE signature.")
        raise HTTPException(status_code=400, detail="Invalid LINE signature.") from exc

    logger.info("Received %s LINE webhook event(s).", len(events))
    results = []
    for event in events:
        logger.info("LINE message received: text=%r user_id=%r", event.text, event.user_id)
        if _is_user_id_command(event.text):
            user_id = event.user_id or "User ID was not included in this event."
            try:
                await run_in_threadpool(
                    line_client.reply_message,
                    event.reply_token,
                    f"LINE_USER_ID={user_id}",
                )
            except Exception:
                logger.exception("Failed to reply with LINE_USER_ID.")
                raise
            results.append({"user_id": event.user_id, "summary_sent": False, "command": "user_id"})
            continue

        result = await run_in_threadpool(
            run_ondemand_brief,
            event.text,
            event.reply_token,
        )
        results.append({"user_id": event.user_id, "summary_sent": bool(result.get("summary"))})

    return {"status": "ok", "handled": len(results), "results": results}


def _is_user_id_command(text: str) -> bool:
    return text.strip().lower() in USER_ID_COMMANDS


# --- Dashboard SPA ----------------------------------------------------------
# Mounted last, so every route declared above is matched first.
#
# The frontend uses hash routing (#/anime, #/finance/NVDA), which means the
# server is only ever asked for "/" — no SPA catch-all route is needed, and
# therefore nothing can swallow /api, /webhook or /health.
#
# Build it with `cd frontend && npm run build`; the output lands in ./static.
STATIC_DIR = Path(__file__).parent / "static"

if (STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
else:

    @app.get("/")
    async def root() -> dict[str, str]:
        logger.warning("No dashboard build found in %s — serving the API only.", STATIC_DIR)
        return {
            "status": "ok",
            "service": "combined-bot",
            "dashboard": "not built (run: cd frontend && npm run build)",
            "health": "/health",
            "anime_health": "/health/anime",
            "webhook": "/webhook",
        }
