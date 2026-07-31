"""Collections used by the personal web dashboard.

Reuses the MongoClient already created in `anime.database` so the process keeps
a single connection pool. The bot's own `subscriptions` collection is imported
read/write here but its *schema is never changed* — watch progress lives in a
separate collection so the Discord notification logic stays untouched.
"""

from __future__ import annotations

from anime.database import collection as subscriptions
from anime.database import db


watch_progress = db["watch_progress"]
stock_watchlist = db["stock_watchlist"]
cache_entries = db["cache"]

_indexes_ready = False


def ensure_indexes() -> None:
    """Create indexes once at startup. Safe to call repeatedly."""
    global _indexes_ready
    if _indexes_ready:
        return

    watch_progress.create_index("anime_id", unique=True)
    stock_watchlist.create_index("symbol", unique=True)
    cache_entries.create_index("key", unique=True)
    # TTL index: Mongo removes entries once expires_at passes.
    cache_entries.create_index("expires_at", expireAfterSeconds=0)
    _indexes_ready = True


__all__ = [
    "subscriptions",
    "watch_progress",
    "stock_watchlist",
    "cache_entries",
    "ensure_indexes",
]
