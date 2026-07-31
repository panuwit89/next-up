"""One-off MongoDB setup/verification for the dashboard.

Creates the collections and indexes the web API needs and seeds the stock
watchlist — the same thing that happens automatically on startup, just runnable
ahead of a deploy so you can confirm the result in Compass.

The `subscriptions` collection is only ever READ here; the script asserts its
document count is unchanged before exiting.

Run from the Combined Bot directory:

    python setup_db.py

Only needs the lightweight dependencies:

    pip install pymongo dnspython pydantic-settings python-dotenv
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()

    if not os.getenv("MONGO_URI"):
        print("ERROR: MONGO_URI is not set. Put it in .env or export it first.")
        return 1

    # Imported after the env check so the failure message stays readable.
    from anime.database import client, db
    from finance.watchlist import get_watchlist_symbols
    from web.db import ensure_indexes, subscriptions

    print("=" * 62)
    print("MongoDB setup / verification")
    print("=" * 62)

    # ---- connection -------------------------------------------------
    try:
        client.admin.command("ping")
    except Exception as exc:
        print(f"\nERROR: could not reach the cluster.\n  {exc}")
        return 1
    print(f"\n[1] Connected to database: {db.name}")

    before = sorted(db.list_collection_names())
    print(f"    Existing collections: {', '.join(before) or '(none)'}")

    # ---- existing bot data (read-only) -------------------------------
    sub_count_before = subscriptions.count_documents({})
    print(f"\n[2] Existing subscriptions: {sub_count_before}")

    targets = {
        (str(doc.get("guild_id")), str(doc.get("channel_id")))
        for doc in subscriptions.find({}, {"_id": 0, "guild_id": 1, "channel_id": 1})
    }
    for guild_id, channel_id in sorted(targets):
        print(f"    guild {guild_id}  ->  channel {channel_id}")

    if len(targets) == 1:
        print("    OK: single Discord target — no DISCORD_GUILD_ID env var needed.")
    elif len(targets) > 1:
        print("    NOTE: more than one guild/channel found. New subscriptions made from")
        print("          the web will use whichever one Mongo returns first.")

    # ---- create collections + indexes --------------------------------
    print("\n[3] Creating dashboard collections and indexes...")
    ensure_indexes()
    print("    done")

    # ---- seed the stock watchlist ------------------------------------
    print("\n[4] Stock watchlist")
    symbols = get_watchlist_symbols()
    print(f"    Symbols: {', '.join(symbols) if symbols else '(empty)'}")
    print("    (seeded from STOCK_SYMBOLS on first run; edited via the web API after that)")

    # ---- report -------------------------------------------------------
    print("\n[5] Final state")
    for name in sorted(db.list_collection_names()):
        count = db[name].count_documents({})
        marker = "  (existing)" if name in before else "  (new)"
        print(f"    {name:<18} {count:>4} docs{marker}")
        for index_name, spec in db[name].index_information().items():
            keys = ", ".join(f"{field}:{direction}" for field, direction in spec["key"])
            flags = []
            if spec.get("unique"):
                flags.append("unique")
            if "expireAfterSeconds" in spec:
                flags.append(f"TTL={spec['expireAfterSeconds']}s")
            suffix = f"  [{', '.join(flags)}]" if flags else ""
            print(f"        - {index_name}: {{{keys}}}{suffix}")

    # ---- safety check --------------------------------------------------
    sub_count_after = subscriptions.count_documents({})
    print("\n" + "=" * 62)
    if sub_count_after != sub_count_before:
        print(f"WARNING: subscriptions changed ({sub_count_before} -> {sub_count_after})")
        return 1

    print(f"subscriptions untouched ({sub_count_after} documents). Setup complete.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
