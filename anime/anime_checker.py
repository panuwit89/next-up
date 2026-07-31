import aiohttp
import time

ANILIST_URL = "https://graphql.anilist.co"

async def query_anilist(query: str, variables: dict):
    async with aiohttp.ClientSession() as session:
        async with session.post(ANILIST_URL, json={"query": query, "variables": variables}) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("data")

async def search_anime(query: str):
    gql = """
    query ($search: String) {
        Page(perPage: 5) {
            media(search: $search, type: ANIME, format: TV) {
                id
                title { romaji english }
                episodes
                status
                coverImage { large }
                averageScore
                nextAiringEpisode { episode airingAt }
            }
        }
    }
    """
    data = await query_anilist(gql, {"search": query})
    if not data:
        return []
    return data["Page"]["media"]

async def get_anime_by_id(anime_id: int):
    gql = """
    query ($id: Int) {
        Media(id: $id, type: ANIME) {
            id
            title { romaji english }
            episodes
            status
            coverImage { large }
            nextAiringEpisode { episode airingAt }
        }
    }
    """
    data = await query_anilist(gql, {"id": anime_id})
    if not data:
        return None
    return data["Media"]

async def get_next_airing_episode(anime_id: int):
    now = int(time.time())

    gql = """
    query ($id: Int) {
        Media(id: $id, type: ANIME) {
            nextAiringEpisode { episode airingAt }
            airingSchedule(notYetAired: true, perPage: 10) {
                nodes { episode airingAt }
            }
        }
    }
    """
    data = await query_anilist(gql, {"id": anime_id})
    if not data or not data.get("Media"):
        return None

    media = data["Media"]
    next_ep = media.get("nextAiringEpisode")
    if next_ep and next_ep.get("episode") and next_ep.get("airingAt"):
        return next_ep

    nodes = media.get("airingSchedule", {}).get("nodes", [])
    future = [
        n for n in nodes
        if n.get("episode") and n.get("airingAt") and n["airingAt"] > now
    ]
    if not future:
        gql = """
        query ($id: Int, $now: Int) {
            Page(perPage: 1) {
                airingSchedules(
                    mediaId: $id
                    airingAt_greater: $now
                    sort: TIME
                ) {
                    episode
                    airingAt
                }
            }
        }
        """
        data = await query_anilist(gql, {"id": anime_id, "now": now})
        if not data:
            return None

        schedules = data.get("Page", {}).get("airingSchedules", [])
        valid_schedules = [
            s for s in schedules
            if s.get("episode") and s.get("airingAt")
        ]
        if not valid_schedules:
            return None

        return valid_schedules[0]

    return min(future, key=lambda n: n["airingAt"])

async def get_seasonal_anime(limit: int = 20):
    gql = """
    query ($perPage: Int) {
        Page(perPage: $perPage) {
            media(status: RELEASING, type: ANIME, format: TV, sort: SCORE_DESC) {
                id
                title { romaji english }
                episodes
                status
                averageScore
                nextAiringEpisode { episode airingAt }
            }
        }
    }
    """
    data = await query_anilist(gql, {"perPage": limit})
    if not data:
        return []
    return data["Page"]["media"]

async def get_airing_episodes(anime_id: int, offset_minutes: int = 0):
    now = int(time.time())

    gql = """
    query ($id: Int) {
        Media(id: $id, type: ANIME) {
            airingSchedule(notYetAired: false, perPage: 50) {
                nodes { episode airingAt }
            }
        }
    }
    """
    data = await query_anilist(gql, {"id": anime_id})
    if not data:
        return None, None
    nodes = data["Media"]["airingSchedule"]["nodes"]

    # กรองตอนที่ออกจริงๆ แล้วเท่านั้น
    aired = [
        n for n in nodes
        if n.get("episode") and n.get("airingAt")
        and n["airingAt"] + (offset_minutes * 60) <= now
    ]

    if not aired:
        return None, None

    latest = max(aired, key=lambda n: n["episode"])
    return latest["episode"], None

async def get_episode_list(anime_id: int):
    now = int(time.time())  # unix timestamp ปัจจุบัน

    gql = """
    query ($id: Int) {
        Media(id: $id, type: ANIME) {
            id
            title { romaji english }
            episodes
            status
            coverImage { large }
            averageScore
            siteUrl
            airingSchedule(
                notYetAired: false
                perPage: 50
            ) {
                nodes { episode airingAt }
            }
        }
    }
    """
    data = await query_anilist(gql, {"id": anime_id})
    if not data:
        return None, []
    media = data["Media"]
    all_nodes = media.get("airingSchedule", {}).get("nodes", [])

    # กรองเฉพาะตอนที่ airingAt น้อยกว่าเวลาปัจจุบัน = ออกไปแล้วจริงๆ
    aired = [
        n for n in all_nodes
        if n.get("episode") and n.get("airingAt") and n["airingAt"] <= now
    ]

    return media, aired

async def get_latest_episode(anime_id: int):
    now = int(time.time())

    gql = """
    query ($id: Int) {
        Media(id: $id, type: ANIME) {
            id
            title { romaji english }
            episodes
            status
            coverImage { large }
            averageScore
            siteUrl
            airingSchedule(notYetAired: false, perPage: 50) {
                nodes { episode airingAt }
            }
        }
    }
    """
    data = await query_anilist(gql, {"id": anime_id})
    if not data:
        return None
    media = data["Media"]

    all_nodes = media.get("airingSchedule", {}).get("nodes", [])
    aired = [
        n for n in all_nodes
        if n.get("episode") and n.get("airingAt") and n["airingAt"] <= now
    ]
    latest_ep = max(aired, key=lambda n: n["episode"])["episode"] if aired else None

    return {
        "title": media["title"]["romaji"],
        "episode_count": media.get("episodes"),
        "image": media["coverImage"]["large"],
        "url": media.get("siteUrl"),
        "score": media.get("averageScore"),
        "latest_episode": latest_ep,
    }
