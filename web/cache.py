"""Tiny MongoDB-backed TTL cache.

Exists mainly to protect the free API quotas: NewsAPI allows only ~100 requests
a day, and `yfinance`'s `.info` call is slow enough that hitting it on every
page view makes the dashboard feel broken.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pymongo.errors import PyMongoError

from web.db import cache_entries


logger = logging.getLogger("web.cache")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cache_get(key: str) -> Any | None:
    try:
        entry = cache_entries.find_one({"key": key})
    except PyMongoError:
        logger.warning("Cache read failed for %s", key, exc_info=True)
        return None

    if not entry:
        return None

    # Mongo's TTL monitor only sweeps about once a minute, so expired entries
    # can still be present — check the timestamp rather than trusting the sweep.
    expires_at = entry.get("expires_at")
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= _now():
            return None

    return entry.get("value")


def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        cache_entries.replace_one(
            {"key": key},
            {
                "key": key,
                "value": value,
                "expires_at": _now() + timedelta(seconds=ttl_seconds),
            },
            upsert=True,
        )
    except PyMongoError:
        logger.warning("Cache write failed for %s", key, exc_info=True)


def cached(key: str, ttl_seconds: int, producer: Callable[[], Any]) -> Any:
    """Return the cached value for `key`, otherwise call `producer` and store it."""
    hit = cache_get(key)
    if hit is not None:
        return hit

    value = producer()
    if value is not None:
        cache_set(key, value, ttl_seconds)
    return value


def cache_invalidate(prefix: str) -> None:
    """Drop every entry whose key starts with `prefix`."""
    try:
        cache_entries.delete_many({"key": {"$regex": f"^{prefix}"}})
    except PyMongoError:
        logger.warning("Cache invalidate failed for %s*", prefix, exc_info=True)
