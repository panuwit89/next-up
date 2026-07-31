"""Anime data for the dashboard: AniList + subscriptions + personal watch progress.

Grouping follows the rule agreed for this dashboard:

    has a next episode?
      yes -> On Air              (watch progress is irrelevant here)
      no  -> Finished
               watched everything -> "done"
               otherwise          -> "watching"
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from anime.anime_checker import query_anilist
from anime.database import set_offset as db_set_offset
from web.db import subscriptions, watch_progress


logger = logging.getLogger("web.anime")

GROUP_ON_AIR = "on_air"
GROUP_FINISHED_WATCHING = "finished_watching"
GROUP_FINISHED_DONE = "finished_done"

# Offsets are stored in minutes; ±24 h is far more than any real release delay.
MAX_OFFSET_MINUTES = 1440

# AniList's `externalLinks` only lists the services *it* knows about, which
# regularly misses where a title is actually watchable in a given region — a
# show may list Crunchyroll only while airing on Bilibili in Southeast Asia.
# This catalogue backs the "watching on" dropdown so any service can be chosen,
# whether or not AniList knows about it. Colours are the brand colours, used to
# draw a fallback badge when there is no icon URL from AniList.
STREAMING_PLATFORMS: list[dict[str, str]] = [
    {"site": "Crunchyroll", "color": "#F47521"},
    {"site": "Netflix", "color": "#E50914"},
    {"site": "Bilibili TV", "color": "#00A1D6"},
    {"site": "Bstation", "color": "#00A1D6"},
    {"site": "YouTube", "color": "#FF0000"},
    {"site": "Amazon Prime Video", "color": "#00A8E1"},
    {"site": "Disney Plus", "color": "#113CCF"},
    {"site": "Muse Asia", "color": "#ED1C24"},
    {"site": "Ani-One Asia", "color": "#FDB913"},
    {"site": "iQIYI", "color": "#00BE06"},
    {"site": "WeTV", "color": "#FF5C00"},
    {"site": "Viu", "color": "#FFCC00"},
    {"site": "TrueID", "color": "#E4022D"},
    {"site": "HIDIVE", "color": "#00A0DF"},
    {"site": "Hulu", "color": "#1CE783"},
    {"site": "Max", "color": "#0026FF"},
    {"site": "Apple TV+", "color": "#333333"},
]

# AniList caps `perPage` at 50.
ANILIST_PAGE_SIZE = 50

LIST_QUERY = """
query ($ids: [Int]) {
    Page(perPage: 50) {
        media(id_in: $ids, type: ANIME) {
            id
            title { romaji english }
            episodes
            status
            siteUrl
            coverImage { large }
            nextAiringEpisode { episode airingAt }
            airingSchedule(notYetAired: false, perPage: 50) {
                nodes { episode airingAt }
            }
            externalLinks { site url type icon color }
        }
    }
}
"""

SEARCH_QUERY = """
query ($search: String) {
    Page(perPage: 10) {
        media(search: $search, type: ANIME, format_in: [TV, TV_SHORT, ONA, OVA, MOVIE]) {
            id
            title { romaji english }
            episodes
            status
            coverImage { large }
            averageScore
            startDate { year }
        }
    }
}
"""

BY_ID_QUERY = """
query ($id: Int) {
    Media(id: $id, type: ANIME) {
        id
        title { romaji english }
        episodes
        status
        coverImage { large }
        averageScore
        startDate { year }
    }
}
"""


async def list_tracked_anime() -> dict[str, Any]:
    """Every subscribed anime, enriched and split into the three display groups."""
    subs = list(subscriptions.find({}, {"_id": 0}))
    if not subs:
        return {"groups": {GROUP_ON_AIR: [], GROUP_FINISHED_WATCHING: [], GROUP_FINISHED_DONE: []}}

    anime_ids = sorted({int(sub["anime_id"]) for sub in subs})
    media_by_id = await _fetch_media(anime_ids)
    progress_by_id = _progress_map(anime_ids)

    # One card per anime even if it were subscribed more than once.
    seen: set[int] = set()
    items: list[dict[str, Any]] = []
    for sub in subs:
        anime_id = int(sub["anime_id"])
        if anime_id in seen:
            continue
        seen.add(anime_id)
        items.append(
            _build_item(
                anime_id=anime_id,
                subscription=sub,
                media=media_by_id.get(anime_id),
                progress=progress_by_id.get(anime_id),
            )
        )

    # Most recently released episode first.
    items.sort(key=lambda item: item.get("latest_episode_at") or 0, reverse=True)

    groups: dict[str, list[dict[str, Any]]] = {
        GROUP_ON_AIR: [],
        GROUP_FINISHED_WATCHING: [],
        GROUP_FINISHED_DONE: [],
    }
    for item in items:
        groups[item["group"]].append(item)
    return {"groups": groups}


async def _fetch_media(anime_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Fetch every tracked anime in as few AniList calls as possible."""
    media_by_id: dict[int, dict[str, Any]] = {}
    for start in range(0, len(anime_ids), ANILIST_PAGE_SIZE):
        chunk = anime_ids[start : start + ANILIST_PAGE_SIZE]
        data = await query_anilist(LIST_QUERY, {"ids": chunk})
        if not data:
            logger.warning("AniList returned no data for ids %s", chunk)
            continue
        for media in data.get("Page", {}).get("media", []) or []:
            media_by_id[int(media["id"])] = media
    return media_by_id


def _progress_map(anime_ids: list[int]) -> dict[int, dict[str, Any]]:
    docs = watch_progress.find({"anime_id": {"$in": anime_ids}}, {"_id": 0})
    return {int(doc["anime_id"]): doc for doc in docs}


def _build_item(
    *,
    anime_id: int,
    subscription: dict[str, Any],
    media: dict[str, Any] | None,
    progress: dict[str, Any] | None,
) -> dict[str, Any]:
    watched = int((progress or {}).get("watched_episode") or 0)
    platform_override = (progress or {}).get("platform")
    fallback_title = subscription.get("anime_title") or "Unknown"
    # Lives on the subscription because the Discord bot uses it to delay
    # notifications; the dashboard shows the same adjusted airing time.
    offset_minutes = int(subscription.get("offset_minutes") or 0)

    if not media:
        # AniList didn't return this id — still show the card so it can be removed.
        return {
            "anime_id": anime_id,
            "title": fallback_title,
            "cover_image": None,
            "site_url": None,
            "total_episodes": None,
            "latest_episode": None,
            "latest_episode_at": None,
            "next_episode": None,
            "watched_episode": watched,
            "platforms": [],
            "platform": platform_override,
            "offset_minutes": offset_minutes,
            "group": GROUP_FINISHED_WATCHING,
            "unavailable": True,
        }

    next_airing = media.get("nextAiringEpisode") or None
    aired_nodes = ((media.get("airingSchedule") or {}).get("nodes")) or []
    latest_episode, latest_episode_at = _latest_aired(next_airing, aired_nodes, media.get("episodes"))
    total_episodes = media.get("episodes") or latest_episode

    if next_airing:
        group = GROUP_ON_AIR
    elif total_episodes and watched >= total_episodes:
        group = GROUP_FINISHED_DONE
    else:
        group = GROUP_FINISHED_WATCHING

    title = (media.get("title") or {}).get("romaji") or fallback_title

    return {
        "anime_id": anime_id,
        "title": title,
        "title_english": (media.get("title") or {}).get("english"),
        "cover_image": (media.get("coverImage") or {}).get("large"),
        "site_url": media.get("siteUrl"),
        "status": media.get("status"),
        "total_episodes": total_episodes,
        "latest_episode": latest_episode,
        "latest_episode_at": latest_episode_at,
        "next_episode": (
            {"episode": next_airing["episode"], "airing_at": next_airing["airingAt"]}
            if next_airing
            else None
        ),
        "watched_episode": watched,
        "platforms": _streaming_links(media.get("externalLinks")),
        "platform": platform_override,
        "offset_minutes": offset_minutes,
        "group": group,
    }


def _latest_aired(
    next_airing: dict[str, Any] | None,
    aired_nodes: list[dict[str, Any]],
    total_episodes: int | None,
) -> tuple[int | None, int | None]:
    """Latest aired episode number and when it aired.

    `nextAiringEpisode.episode - 1` is used rather than max() over the schedule
    because AniList caps the schedule at 50 nodes — for a long-running series
    those 50 are the *earliest* episodes, not the most recent ones.
    """
    if next_airing and next_airing.get("episode"):
        latest = int(next_airing["episode"]) - 1
    elif total_episodes:
        latest = int(total_episodes)
    elif aired_nodes:
        latest = max(int(node["episode"]) for node in aired_nodes if node.get("episode"))
    else:
        return None, None

    if latest <= 0:
        return None, None

    aired_at = next(
        (node.get("airingAt") for node in aired_nodes if node.get("episode") == latest),
        None,
    )
    return latest, aired_at


def _streaming_links(external_links: Any) -> list[dict[str, Any]]:
    links = []
    for link in external_links or []:
        if not isinstance(link, dict) or link.get("type") != "STREAMING":
            continue
        links.append(
            {
                "site": link.get("site"),
                "url": link.get("url"),
                "icon": link.get("icon"),
                "color": link.get("color"),
            }
        )
    return links


async def search_anime_catalog(query: str) -> list[dict[str, Any]]:
    """Search AniList by title, or fetch directly when given a numeric id."""
    trimmed = query.strip()
    if not trimmed:
        return []

    if trimmed.isdigit():
        data = await query_anilist(BY_ID_QUERY, {"id": int(trimmed)})
        media = (data or {}).get("Media")
        return [_search_result(media)] if media else []

    data = await query_anilist(SEARCH_QUERY, {"search": trimmed})
    results = (data or {}).get("Page", {}).get("media", []) or []
    return [_search_result(media) for media in results]


def _search_result(media: dict[str, Any]) -> dict[str, Any]:
    return {
        "anime_id": int(media["id"]),
        "title": (media.get("title") or {}).get("romaji") or "Unknown",
        "title_english": (media.get("title") or {}).get("english"),
        "cover_image": (media.get("coverImage") or {}).get("large"),
        "episodes": media.get("episodes"),
        "status": media.get("status"),
        "score": media.get("averageScore"),
        "year": (media.get("startDate") or {}).get("year"),
    }


def set_watch_progress(anime_id: int, watched_episode: int) -> dict[str, Any]:
    watched = max(0, int(watched_episode))
    watch_progress.update_one(
        {"anime_id": anime_id},
        {
            "$set": {
                "watched_episode": watched,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    return {"anime_id": anime_id, "watched_episode": watched}


def set_platform(anime_id: int, platform: str | None) -> dict[str, Any]:
    watch_progress.update_one(
        {"anime_id": anime_id},
        {"$set": {"platform": platform, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"anime_id": anime_id, "platform": platform}


def clear_watch_progress(anime_id: int) -> None:
    watch_progress.delete_one({"anime_id": anime_id})


def platform_catalog(items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every service that can be chosen in the "watching on" dropdown.

    The built-in catalogue plus any extra site names AniList has returned or the
    user has already saved, so a previously-picked service never disappears from
    the list just because it isn't built in.
    """
    catalog: dict[str, dict[str, Any]] = {
        entry["site"].casefold(): dict(entry) for entry in STREAMING_PLATFORMS
    }

    for item in items or []:
        for link in item.get("platforms") or []:
            site = link.get("site")
            if not site:
                continue
            entry = catalog.setdefault(site.casefold(), {"site": site, "color": None})
            # AniList ships real favicons; prefer them over a colour swatch.
            if link.get("icon") and not entry.get("icon"):
                entry["icon"] = link["icon"]
            if link.get("color") and not entry.get("color"):
                entry["color"] = link["color"]

        saved = item.get("platform")
        if saved:
            catalog.setdefault(saved.casefold(), {"site": saved, "color": None})

    return sorted(catalog.values(), key=lambda entry: entry["site"].casefold())


def set_airing_offset(anime_id: int, offset_minutes: int) -> dict[str, Any]:
    """Delay used for titles that reach a streaming service after AniList says.

    Written to `subscriptions.offset_minutes` — the same field `/setoffset` uses
    in Discord — so the bot's notification timing and the dashboard countdown
    stay in agreement.
    """
    offset = max(-MAX_OFFSET_MINUTES, min(MAX_OFFSET_MINUTES, int(offset_minutes)))

    updated = False
    for sub in subscriptions.find({"anime_id": anime_id}, {"_id": 0, "guild_id": 1}):
        if db_set_offset(str(sub["guild_id"]), anime_id, offset):
            updated = True

    if not updated:
        raise LookupError(f"Anime {anime_id} is not in the watchlist.")

    return {"anime_id": anime_id, "offset_minutes": offset}
