"""Price history with an automatic provider fallback.

Yahoo's chart endpoint is free and needs no key, but it rate-limits by IP and
Render's egress addresses are shared with thousands of other services — in
practice every request from there returns HTTP 429 while the identical request
from a home connection succeeds. Changing headers or retrying does not help.

So: try Yahoo, and when it refuses, switch to Twelve Data (free API key) and
stop asking Yahoo for a while. Development on a home connection keeps using
Yahoo; production quietly settles on Twelve Data after one failed attempt.

Both providers are normalised to the same shape:

    {"candles": [{timestamp, open, high, low, close, volume}, ...],  # oldest first
     "meta":    {currency, exchange, previous_close, day_high, ...},
     "source":  "yahoo" | "twelvedata"}
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from finance.config import get_settings
from finance.services.symbols import COMPANY_NAMES, resolve_stock_symbol


logger = logging.getLogger("finance.market_data")

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_HEADERS = {
    "accept": "application/json",
    # A browser UA does not lift the IP block, but it costs nothing and avoids
    # being the most obvious bot on the wire.
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}
# Short, because a blocked Yahoo should not delay the fallback for long.
YAHOO_TIMEOUT = 6

TWELVEDATA_URL = "https://api.twelvedata.com"
TWELVEDATA_TIMEOUT = 15

# How long to stop trying Yahoo after it rate-limits us. Process-local: a
# restart re-probes, which is what we want if the block ever lifts.
YAHOO_COOLDOWN_SECONDS = 1800
_yahoo_blocked_until = 0.0

# Yahoo range/interval -> Twelve Data interval, and how many bars to ask for.
TWELVEDATA_INTERVALS = {
    "5m": ("5min", 78),
    "30m": ("30min", 70),
    "1d": ("1day", 300),
    "1wk": ("1week", 300),
    "1mo": ("1month", 400),
}


class MarketDataError(RuntimeError):
    """No provider could supply data for this symbol."""


# Company names, so news queries can search the brand rather than the ticker.
# Filled opportunistically from responses we already fetch; process-local, since
# a name changes about as often as the company is renamed.
_company_names: dict[str, str | None] = {}


def get_company_name(symbol: str) -> str | None:
    """Human-readable name for `symbol`, or None if no provider knows it."""
    resolved = resolve_stock_symbol(symbol)

    static = COMPANY_NAMES.get(resolved)
    if static:
        return static
    if resolved in _company_names:
        return _company_names[resolved]

    try:
        quote = _twelvedata_get("quote", {"symbol": resolved})
        name = (quote.get("name") or "").strip() or None
    except Exception as exc:
        # Not cached: a missing key or a transient error would otherwise pin the
        # weaker ticker-only query for the whole life of the process. Callers
        # cache their own results, so this cannot turn into a hot loop.
        logger.warning("Company-name lookup failed for %s: %s", resolved, exc)
        return None

    if name:
        _company_names[resolved] = name
    return name


def _remember_name(symbol: str, name: Any) -> None:
    """Cache a name seen in a price response — saves a dedicated lookup later."""
    cleaned = str(name).strip() if name else ""
    if cleaned:
        _company_names.setdefault(symbol, cleaned)


def get_chart(
    symbol: str,
    range_key: str,
    interval: str,
    *,
    with_quote: bool = False,
) -> dict[str, Any]:
    resolved = resolve_stock_symbol(symbol)
    errors: list[str] = []

    if _yahoo_available():
        try:
            return _from_yahoo(resolved, range_key, interval)
        except _RateLimited as exc:
            _mark_yahoo_blocked()
            errors.append(f"yahoo: {exc}")
        except Exception as exc:
            errors.append(f"yahoo: {exc}")

    try:
        return _from_twelvedata(resolved, interval, with_quote=with_quote)
    except Exception as exc:
        errors.append(f"twelvedata: {exc}")

    raise MarketDataError(f"{resolved}: " + " | ".join(errors))


# ----------------------------------------------------------------- cooldown --


class _RateLimited(RuntimeError):
    pass


def _yahoo_available() -> bool:
    return time.monotonic() >= _yahoo_blocked_until


def _mark_yahoo_blocked() -> None:
    global _yahoo_blocked_until
    _yahoo_blocked_until = time.monotonic() + YAHOO_COOLDOWN_SECONDS
    logger.warning(
        "Yahoo rate-limited this host; using Twelve Data for the next %s minutes.",
        YAHOO_COOLDOWN_SECONDS // 60,
    )


def reset_yahoo_cooldown() -> None:
    """Test hook."""
    global _yahoo_blocked_until
    _yahoo_blocked_until = 0.0


# ------------------------------------------------------------------- yahoo --


def _from_yahoo(symbol: str, range_key: str, interval: str) -> dict[str, Any]:
    response = requests.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params={"range": range_key, "interval": interval, "includePrePost": "false"},
        headers=YAHOO_HEADERS,
        timeout=YAHOO_TIMEOUT,
    )
    if response.status_code == 429:
        raise _RateLimited("429 Too Many Requests")
    response.raise_for_status()

    chart = (response.json() or {}).get("chart") or {}
    if chart.get("error"):
        error = chart["error"]
        raise RuntimeError(error.get("description") or error.get("code") or "unknown error")

    result = (chart.get("result") or [None])[0]
    if not result:
        raise RuntimeError("no chart result")

    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    timestamps = result.get("timestamp") or []
    meta = result.get("meta") or {}
    _remember_name(symbol, meta.get("longName") or meta.get("shortName"))

    candles = []
    for index, stamp in enumerate(timestamps):
        close = _at(quote.get("close"), index)
        if close is None:
            continue  # holidays and halted sessions arrive as nulls
        candles.append(
            {
                "timestamp": int(stamp),
                "open": _round(_at(quote.get("open"), index)),
                "high": _round(_at(quote.get("high"), index)),
                "low": _round(_at(quote.get("low"), index)),
                "close": _round(close),
                "volume": _at(quote.get("volume"), index) or 0,
            }
        )

    return {
        "candles": candles,
        "source": "yahoo",
        "meta": {
            "currency": meta.get("currency"),
            "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
            "market_state": meta.get("marketState"),
            "regular_market_price": _round(meta.get("regularMarketPrice")),
            "previous_close": _round(meta.get("chartPreviousClose") or meta.get("previousClose")),
            "day_high": _round(meta.get("regularMarketDayHigh")),
            "day_low": _round(meta.get("regularMarketDayLow")),
            "fifty_two_week_high": _round(meta.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": _round(meta.get("fiftyTwoWeekLow")),
        },
    }


# ------------------------------------------------------------- twelve data --


def _twelvedata_key() -> str:
    key = get_settings().TWELVEDATA_API_KEY
    if not key:
        raise RuntimeError("TWELVEDATA_API_KEY is not set")
    return key


def _twelvedata_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        f"{TWELVEDATA_URL}/{path}",
        params={**params, "apikey": _twelvedata_key()},
        timeout=TWELVEDATA_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    # Errors arrive as a JSON body, sometimes with HTTP 200.
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise RuntimeError(f"{payload.get('code')}: {payload.get('message')}")
    return payload


def _from_twelvedata(symbol: str, interval: str, *, with_quote: bool) -> dict[str, Any]:
    td_interval, outputsize = TWELVEDATA_INTERVALS.get(interval, ("1day", 300))

    payload = _twelvedata_get(
        "time_series",
        {
            "symbol": symbol,
            "interval": td_interval,
            "outputsize": outputsize,
            "timezone": "UTC",  # so datetimes convert without exchange-tz guessing
            "order": "ASC",
        },
    )

    candles = []
    for row in payload.get("values") or []:
        close = _float(row.get("close"))
        stamp = _epoch(row.get("datetime"))
        if close is None or stamp is None:
            continue
        candles.append(
            {
                "timestamp": stamp,
                "open": _round(row.get("open")),
                "high": _round(row.get("high")),
                "low": _round(row.get("low")),
                "close": _round(close),
                "volume": int(_float(row.get("volume")) or 0),
            }
        )

    if not candles:
        raise RuntimeError("no candles returned")

    td_meta = payload.get("meta") or {}
    latest = candles[-1]
    meta: dict[str, Any] = {
        "currency": td_meta.get("currency"),
        "exchange": td_meta.get("exchange"),
        "market_state": None,
        "regular_market_price": latest["close"],
        "previous_close": candles[-2]["close"] if len(candles) > 1 else None,
        "day_high": latest["high"],
        "day_low": latest["low"],
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
    }

    # The 52-week range is only shown in the detail drawer, so it costs an extra
    # request only when that is open.
    if with_quote:
        try:
            quote = _twelvedata_get("quote", {"symbol": symbol})
            _remember_name(symbol, quote.get("name"))
            window = quote.get("fifty_two_week") or {}
            meta.update(
                {
                    "previous_close": _round(quote.get("previous_close")) or meta["previous_close"],
                    "day_high": _round(quote.get("high")) or meta["day_high"],
                    "day_low": _round(quote.get("low")) or meta["day_low"],
                    "fifty_two_week_high": _round(window.get("high")),
                    "fifty_two_week_low": _round(window.get("low")),
                    "market_state": "OPEN" if quote.get("is_market_open") else "CLOSED",
                }
            )
        except Exception as exc:
            logger.warning("Twelve Data quote lookup failed for %s: %s", symbol, exc)

    return {"candles": candles, "meta": meta, "source": "twelvedata"}


# ------------------------------------------------------------------ helpers --


def _epoch(value: Any) -> int | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            continue
    return None


def _at(values: Any, index: int) -> Any:
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 2) -> float | None:
    numeric = _float(value)
    return round(numeric, digits) if numeric is not None else None
