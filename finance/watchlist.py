"""DB-backed stock watchlist.

The list used to live in the `STOCK_SYMBOLS` env var, which meant changing it
required a Render redeploy. It now lives in MongoDB so the web dashboard can
edit it — and because the weekly LINE brief reads the same list, adding a symbol
on the web also adds it to the brief.

On first run the env var seeds the collection, so an existing deployment keeps
exactly the symbols it had with no manual migration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo.errors import PyMongoError

from finance.config import get_settings
from finance.services.symbols import resolve_stock_symbol


logger = logging.getLogger("finance.watchlist")


def _collection():
    # Imported lazily: `web.db` pulls in the Mongo connection, and importing it
    # at module scope would make this module unusable in tests without a DB.
    from web.db import stock_watchlist

    return stock_watchlist


def get_watchlist_symbols() -> list[str]:
    """Symbols to track. Falls back to the env var if the DB is unreachable."""
    try:
        symbols = [doc["symbol"] for doc in _collection().find({}, {"_id": 0, "symbol": 1})]
        if symbols:
            return sorted(symbols)
        return _seed_from_env()
    except PyMongoError:
        logger.warning("Watchlist read failed; falling back to STOCK_SYMBOLS.", exc_info=True)
        return get_settings().stock_symbols


def _seed_from_env() -> list[str]:
    """Populate an empty collection from STOCK_SYMBOLS the first time we run."""
    seed = get_settings().stock_symbols
    if not seed:
        return []

    for symbol in seed:
        add_symbol(symbol)
    logger.info("Seeded stock watchlist from STOCK_SYMBOLS: %s", ", ".join(seed))
    return sorted(seed)


def add_symbol(value: str) -> str:
    """Add a symbol (accepts aliases like 'nvidia'). Returns the resolved ticker."""
    symbol = resolve_stock_symbol(value)
    _collection().update_one(
        {"symbol": symbol},
        {"$setOnInsert": {"symbol": symbol, "added_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return symbol


def remove_symbol(value: str) -> bool:
    symbol = resolve_stock_symbol(value)
    return _collection().delete_one({"symbol": symbol}).deleted_count > 0
