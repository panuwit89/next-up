from __future__ import annotations

import logging
from typing import Any

from finance.line_client import LineClient
from finance.services.news import fetch_company_news
from finance.services.stock_quotes import fetch_stock_quotes
from finance.services.symbols import extract_stock_symbols
from finance.summarizer import summarize_company_brief


logger = logging.getLogger("finance_bot.brief")

MAX_RETRIES = 2


def run_weekly_company_brief(query: str | None = None) -> str | None:
    """Scheduled weekly push (Mon 10:00 Asia/Bangkok by default)."""
    summary = _build_brief(query)
    if summary:
        try:
            LineClient().push_message(summary)
        except Exception:
            logger.exception("Failed to push weekly brief to LINE.")
    return summary


# Kept for backwards-compatibility with the old name.
run_daily_brief = run_weekly_company_brief


def run_ondemand_brief(query: str, reply_token: str) -> dict[str, Any]:
    """On-demand reply triggered by a LINE webhook message."""
    summary = _build_brief(query)
    if summary:
        try:
            LineClient().reply_message(reply_token or "", summary)
        except Exception:
            logger.exception("Failed to reply on-demand brief to LINE.")
    return {"summary": summary}


def _build_brief(query: str | None) -> str | None:
    requested_symbols = extract_stock_symbols(query) or None

    stock_data = _fetch_with_retries(
        lambda: fetch_stock_quotes(symbols=requested_symbols, include_unavailable=True),
        label="stock",
    )

    symbols = _symbols_from_stock(stock_data) or extract_stock_symbols(query)
    news_data = _fetch_news(symbols)

    return summarize_company_brief(
        stock_data=stock_data,
        news_data=news_data,
        query=query,
    )


def _fetch_news(symbols: list[str]) -> list[dict[str, Any]] | None:
    if not symbols:
        return []
    try:
        return _fetch_with_retries(lambda: fetch_company_news(symbols), label="news")
    except Exception:
        # Surface per-symbol "unavailable" markers so the brief can still mention them.
        return [{"symbol": symbol, "error": "news unavailable"} for symbol in symbols]


def _fetch_with_retries(fetcher, *, label: str):
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetcher()
        except Exception as exc:
            last_error = exc
            logger.warning("%s fetch attempt %s/%s failed: %s", label, attempt, MAX_RETRIES, exc)
    if last_error and label == "news":
        raise last_error
    logger.error("%s fetch gave up after %s attempts: %s", label, MAX_RETRIES, last_error)
    return None


def _symbols_from_stock(stock_data: Any) -> list[str]:
    symbols: list[str] = []
    for item in stock_data or []:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        if symbol and str(symbol) not in symbols:
            symbols.append(str(symbol))
    return symbols
