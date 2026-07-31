from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from anime.anime_checker import get_airing_episodes
from anime.database import subscribe as db_subscribe
from anime.database import unsubscribe as db_unsubscribe
from anime.database import update_last_episode
from web.anime_service import (
    MAX_OFFSET_MINUTES,
    clear_watch_progress,
    list_tracked_anime,
    platform_catalog,
    search_anime_catalog,
    set_airing_offset,
    set_platform,
    set_watch_progress,
)
from web.db import subscriptions


logger = logging.getLogger("web.anime.routes")

router = APIRouter(prefix="/api/anime", tags=["anime"])


@contextmanager
def _upstream_errors(action: str):
    """Turn upstream failures into a status code with a message the UI can show.

    Without this, a Mongo timeout or an AniList hiccup surfaced as a bare 500
    with no `detail`, so the dashboard could only report "Request failed (500)"
    and the cause had to be dug out of the server log.
    """
    try:
        yield
    except HTTPException:
        raise
    except PyMongoError as exc:
        logger.exception("MongoDB error while %s", action)
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable while {action}: {type(exc).__name__}. {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Upstream error while %s", action)
        raise HTTPException(
            status_code=502,
            detail=f"Upstream error while {action}: {type(exc).__name__}. {exc}",
        ) from exc


class SubscribeRequest(BaseModel):
    anime_id: int
    title: str | None = None


class UnsubscribeRequest(BaseModel):
    anime_ids: list[int] = Field(min_length=1)


class ProgressRequest(BaseModel):
    watched_episode: int = Field(ge=0)


class PlatformRequest(BaseModel):
    platform: str | None = None


class OffsetRequest(BaseModel):
    offset_minutes: int = Field(ge=-MAX_OFFSET_MINUTES, le=MAX_OFFSET_MINUTES)


def _default_target() -> tuple[str, str]:
    """Guild/channel to attach a new subscription to.

    Reuses whatever an existing subscription points at — this dashboard serves a
    single Discord server. Falls back to env vars when nothing is subscribed yet.
    """
    existing = subscriptions.find_one({}, {"_id": 0, "guild_id": 1, "channel_id": 1})
    if existing and existing.get("guild_id") and existing.get("channel_id"):
        return str(existing["guild_id"]), str(existing["channel_id"])

    guild_id = os.getenv("DISCORD_GUILD_ID")
    channel_id = os.getenv("DISCORD_CHANNEL_ID")
    if guild_id and channel_id:
        return guild_id, channel_id

    raise HTTPException(
        status_code=400,
        detail=(
            "No existing subscription to copy the Discord target from. "
            "Subscribe once from Discord, or set DISCORD_GUILD_ID and DISCORD_CHANNEL_ID."
        ),
    )


@router.get("")
async def get_tracked() -> dict[str, Any]:
    with _upstream_errors("loading the watchlist"):
        return await list_tracked_anime()


@router.get("/search")
async def search(q: str = Query(min_length=1)) -> dict[str, Any]:
    with _upstream_errors("searching AniList"):
        return {"results": await search_anime_catalog(q)}


@router.get("/platforms")
async def streaming_platforms() -> dict[str, Any]:
    """Options for the "watching on" dropdown.

    Static data — the caller merges in each title's own AniList links, so this
    never has to touch AniList or the database.
    """
    return {"platforms": platform_catalog()}


@router.post("")
async def subscribe_anime(payload: SubscribeRequest) -> dict[str, Any]:
    with _upstream_errors("subscribing"):
        results = await search_anime_catalog(str(payload.anime_id))
        if not results:
            raise HTTPException(status_code=404, detail="Anime id not found on AniList.")

        found = results[0]
        title = payload.title or found["title"]
        guild_id, channel_id = _default_target()

        await run_in_threadpool(db_subscribe, guild_id, channel_id, payload.anime_id, title)

        # Match the Discord flow: record the already-aired episode so subscribing
        # doesn't immediately fire a notification for an episode released earlier.
        latest_episode, _ = await get_airing_episodes(payload.anime_id)
        if latest_episode:
            await run_in_threadpool(update_last_episode, guild_id, payload.anime_id, latest_episode)

        return {"status": "subscribed", "anime_id": payload.anime_id, "title": title}


@router.delete("")
async def unsubscribe_anime(payload: UnsubscribeRequest) -> dict[str, Any]:
    with _upstream_errors("unsubscribing"):
        removed = []
        for anime_id in payload.anime_ids:
            subscriptions_removed = False
            for sub in list(subscriptions.find({"anime_id": anime_id}, {"_id": 0, "guild_id": 1})):
                if await run_in_threadpool(db_unsubscribe, str(sub["guild_id"]), anime_id):
                    subscriptions_removed = True
            if subscriptions_removed:
                await run_in_threadpool(clear_watch_progress, anime_id)
                removed.append(anime_id)

        return {"status": "unsubscribed", "removed": removed}


@router.put("/{anime_id}/progress")
async def update_progress(anime_id: int, payload: ProgressRequest) -> dict[str, Any]:
    with _upstream_errors("saving watch progress"):
        return await run_in_threadpool(set_watch_progress, anime_id, payload.watched_episode)


@router.put("/{anime_id}/platform")
async def update_platform(anime_id: int, payload: PlatformRequest) -> dict[str, Any]:
    with _upstream_errors("saving the platform"):
        return await run_in_threadpool(set_platform, anime_id, payload.platform)


@router.put("/{anime_id}/offset")
async def update_offset(anime_id: int, payload: OffsetRequest) -> dict[str, Any]:
    with _upstream_errors("saving the airing offset"):
        try:
            return await run_in_threadpool(set_airing_offset, anime_id, payload.offset_minutes)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
