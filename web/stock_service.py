"""Stock data for the dashboard and the detail drawer.

Everything here goes through the TTL cache — NewsAPI's free tier is roughly 100
requests a day, and yfinance's `.info` call is slow.
"""

from __future__ import annotations

import logging
from typing import Any

from finance.services.market_data import get_chart
from finance.services.symbols import company_name_for_symbol
from web.cache import cache_get, cache_set, cached


logger = logging.getLogger("web.stocks")

# 6 months of daily candles: enough warm-up for a meaningful 21-day EMA.
DASHBOARD_RANGE = "6mo"

# EMA windows in *trading* days.
EMA_WINDOWS = {"week_1": 5, "week_2": 10, "month_1": 21}

# Yahoo only accepts certain range/interval pairings.
RANGE_INTERVALS = {
    "1d": "5m",
    "5d": "30m",
    "1mo": "1d",
    "6mo": "1d",
    "ytd": "1d",
    "1y": "1d",
    "5y": "1wk",
    "max": "1mo",
}

CACHE_TTL_INTRADAY = 60
CACHE_TTL_DAILY = 900
CACHE_TTL_PROFILE = 86_400
CACHE_TTL_NEWS = 21_600

# Yahoo rate-limits the quoteSummary endpoint yfinance uses for `.info` (HTTP
# 429). Caching that failure for the full profile TTL would hide market cap and
# P/E for a whole day over a blip, so failures are remembered only briefly —
# long enough to stop hammering Yahoo, short enough to recover on its own.
CACHE_TTL_PROFILE_ERROR = 600


def fetch_dashboard(symbols: list[str]) -> list[dict[str, Any]]:
    rows = []
    for symbol in symbols:
        try:
            rows.append(_dashboard_row(symbol))
        except Exception as exc:
            logger.warning("Dashboard row failed for %s: %s", symbol, exc)
            rows.append(
                {
                    "symbol": symbol,
                    "company_name": company_name_for_symbol(symbol),
                    "error": str(exc),
                }
            )
    return rows


def _dashboard_row(symbol: str) -> dict[str, Any]:
    candles = _daily_candles(symbol)
    closes = [candle["close"] for candle in candles if candle.get("close") is not None]
    latest = candles[-1] if candles else {}
    previous_close = closes[-2] if len(closes) > 1 else None
    price = closes[-1] if closes else None

    change_pct = None
    if price is not None and previous_close:
        change_pct = round(((price - previous_close) / previous_close) * 100, 2)

    return {
        "symbol": symbol,
        "company_name": company_name_for_symbol(symbol),
        "price": price,
        "change_pct": change_pct,
        "previous_close": previous_close,
        "last_session": {
            "date": latest.get("timestamp"),
            "open": latest.get("open"),
            "high": latest.get("high"),
            "low": latest.get("low"),
            "close": latest.get("close"),
            "volume": latest.get("volume"),
        },
        "ema": {name: _ema(closes, window) for name, window in EMA_WINDOWS.items()},
    }


def _daily_candles(symbol: str) -> list[dict[str, Any]]:
    return cached(
        f"chart:{symbol}:{DASHBOARD_RANGE}:1d",
        CACHE_TTL_DAILY,
        lambda: _fetch_chart(symbol, DASHBOARD_RANGE, "1d")["candles"],
    )


def _ema(closes: list[float], span: int) -> float | None:
    """Exponential moving average, seeded with the SMA of the first `span` points."""
    if len(closes) < span:
        return None

    multiplier = 2 / (span + 1)
    value = sum(closes[:span]) / span
    for close in closes[span:]:
        value = close * multiplier + value * (1 - multiplier)
    return round(value, 2)


def fetch_detail(symbol: str, range_key: str) -> dict[str, Any]:
    interval = RANGE_INTERVALS.get(range_key)
    if interval is None:
        raise ValueError(f"Unsupported range '{range_key}'. Use one of: {', '.join(RANGE_INTERVALS)}")

    ttl = CACHE_TTL_INTRADAY if range_key in ("1d", "5d") else CACHE_TTL_DAILY
    chart = cached(
        f"chart:{symbol}:{range_key}:{interval}",
        ttl,
        lambda: _fetch_chart(symbol, range_key, interval),
    )
    meta = chart.get("meta") or {}
    candles = chart.get("candles") or []
    closes = [candle["close"] for candle in candles if candle.get("close") is not None]

    price = meta.get("regular_market_price")
    if price is None and closes:
        price = closes[-1]
    previous_close = meta.get("previous_close")

    change = change_pct = None
    if price is not None and previous_close:
        change = round(price - previous_close, 2)
        change_pct = round((change / previous_close) * 100, 2)

    return {
        "symbol": symbol,
        "company_name": company_name_for_symbol(symbol),
        "range": range_key,
        "interval": interval,
        "currency": meta.get("currency"),
        "exchange": meta.get("exchange"),
        "market_state": meta.get("market_state"),
        "price": price,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "day_high": meta.get("day_high"),
        "day_low": meta.get("day_low"),
        "fifty_two_week_high": meta.get("fifty_two_week_high"),
        "fifty_two_week_low": meta.get("fifty_two_week_low"),
        "open": candles[0].get("open") if candles else None,
        "candles": candles,
        "profile": _profile(symbol),
    }


def _profile(symbol: str) -> dict[str, Any]:
    """Market cap / P/E — the two figures Yahoo's chart endpoint doesn't carry."""
    cache_key = f"profile:{symbol}"
    hit = cache_get(cache_key)
    if hit is not None:
        return hit

    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        profile = {
            "market_cap": info.get("marketCap"),
            "pe_ratio": _round_optional(info.get("trailingPE")),
            "forward_pe": _round_optional(info.get("forwardPE")),
            "dividend_yield": _round_optional(info.get("dividendYield"), 4),
            "sector": info.get("sector"),
        }
    except Exception as exc:
        logger.warning("Profile lookup failed for %s: %s", symbol, exc)
        cache_set(cache_key, {}, CACHE_TTL_PROFILE_ERROR)
        return {}

    cache_set(cache_key, profile, CACHE_TTL_PROFILE)
    return profile


def fetch_symbol_news(symbol: str, limit: int = 5) -> list[dict[str, Any]]:
    """Company news. Returns [] instead of raising so the drawer still renders."""

    def load() -> list[dict[str, Any]]:
        try:
            from finance.services.news import fetch_company_news

            return fetch_company_news([symbol], page_size_per_symbol=limit)
        except Exception as exc:
            logger.warning("News lookup failed for %s: %s", symbol, exc)
            return []

    return cached(f"news:{symbol}:{limit}", CACHE_TTL_NEWS, load) or []


def _fetch_chart(symbol: str, range_key: str, interval: str) -> dict[str, Any]:
    """Delegates to the provider chain (Yahoo, falling back to Twelve Data)."""
    return get_chart(symbol, range_key, interval, with_quote=range_key in ("1d", "5d"))


def _round_optional(value: Any, digits: int = 2) -> float | None:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None
