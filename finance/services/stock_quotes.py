from __future__ import annotations

from typing import Any

import requests
import yfinance as yf

from finance.config import get_settings
from finance.services.market_data import get_chart
from finance.services.symbols import company_name_for_symbol, resolve_stock_symbol


YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
REQUEST_HEADERS = {"accept": "application/json", "user-agent": "finance-bot/1.0"}

# 3 months of daily candles (~63 trading days). Needed so the 20/50-day moving
# averages are actually computed over 20/50 points — with the previous "5d"
# range both collapsed to a 5-day average and reported identical numbers.
HISTORY_RANGE = "3mo"


def fetch_stock_quotes(
    symbols: list[str] | None = None,
    *,
    include_unavailable: bool = False,
) -> list[dict[str, Any]]:
    selected_symbols = symbols
    if not selected_symbols:
        # Watchlist now lives in MongoDB so the web dashboard can edit it;
        # it falls back to the STOCK_SYMBOLS env var if the DB is unreachable.
        from finance.watchlist import get_watchlist_symbols

        selected_symbols = get_watchlist_symbols()

    quotes = []
    failures: list[tuple[str, str]] = []

    for symbol in selected_symbols:
        try:
            resolved_symbol = resolve_stock_symbol(symbol)
        except ValueError as exc:
            failures.append((str(symbol), str(exc)))
            continue

        try:
            quotes.append(_enrich_quote(_fetch_one_symbol(resolved_symbol)))
        except Exception as exc:
            failures.append((resolved_symbol, str(exc)))

    if include_unavailable and failures:
        quotes.extend(_unavailable_quote(symbol, reason) for symbol, reason in failures)

    if not quotes:
        details = "; ".join(f"{symbol}: {reason}" for symbol, reason in failures)
        raise RuntimeError(f"No stock quotes returned. {details}".strip())
    return quotes


def _fetch_one_symbol(symbol: str) -> dict[str, Any]:
    """Daily history via the shared provider chain (Yahoo -> Twelve Data).

    yfinance is kept only as a last resort: it also talks to Yahoo, so it fails
    for the same reason whenever the chart endpoint does.
    """
    errors = []

    try:
        chart = get_chart(symbol, HISTORY_RANGE, "1d")
        closes = [candle["close"] for candle in chart["candles"] if candle.get("close") is not None]
        if not closes:
            raise RuntimeError("no closing prices returned")

        meta = chart.get("meta") or {}
        price = meta.get("regular_market_price") or closes[-1]
        previous_close = meta.get("previous_close")
        if previous_close is None and len(closes) > 1:
            previous_close = closes[-2]

        change_pct = None
        if previous_close:
            change_pct = ((price - previous_close) / previous_close) * 100

        return {
            "symbol": symbol,
            "price": round(price, 2),
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "volume": chart["candles"][-1].get("volume") or 0,
            "technical": _technical_snapshot(closes),
        }
    except Exception as exc:
        errors.append(str(exc))

    try:
        return _fetch_one_symbol_from_yfinance(symbol)
    except Exception as exc:
        errors.append(f"yfinance: {exc}")

    raise RuntimeError(" | ".join(errors))


def _fetch_one_symbol_from_yfinance(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(symbol)
    history = ticker.history(period=HISTORY_RANGE, interval="1d", auto_adjust=False)
    if history.empty:
        raise RuntimeError(f"No price history returned for {symbol}.")

    latest = history.iloc[-1]
    previous_close = None
    if len(history) > 1:
        previous_close = float(history.iloc[-2]["Close"])

    price = float(latest["Close"])
    closes = [float(value) for value in history["Close"].tolist() if value is not None]
    change_pct = None
    if previous_close and previous_close != 0:
        change_pct = ((price - previous_close) / previous_close) * 100

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "volume": int(latest.get("Volume", 0) or 0),
        "technical": _technical_snapshot(closes),
    }


def _fetch_one_symbol_from_yahoo_chart(symbol: str) -> dict[str, Any]:
    response = requests.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        params={"range": HISTORY_RANGE, "interval": "1d", "includePrePost": "false"},
        headers=REQUEST_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()

    chart = payload.get("chart") or {}
    error = chart.get("error")
    if error:
        description = error.get("description") or error.get("code") or "unknown error"
        raise RuntimeError(description)

    result = (chart.get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"No chart result returned for {symbol}.")

    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    meta = result.get("meta") or {}

    latest_index = _latest_value_index(closes)
    if latest_index is None:
        regular_price = meta.get("regularMarketPrice")
        if regular_price is None:
            raise RuntimeError(f"No closing price returned for {symbol}.")
        price = float(regular_price)
        previous_close = _safe_float(meta.get("previousClose"))
        volume = int(meta.get("regularMarketVolume") or 0)
    else:
        price = float(closes[latest_index])
        previous_index = _latest_value_index(closes[:latest_index])
        previous_close = (
            float(closes[previous_index])
            if previous_index is not None
            else _safe_float(meta.get("previousClose"))
        )
        volume = (
            int(volumes[latest_index] or 0)
            if latest_index < len(volumes)
            else int(meta.get("regularMarketVolume") or 0)
        )

    change_pct = None
    if previous_close and previous_close != 0:
        change_pct = ((price - previous_close) / previous_close) * 100

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "volume": volume,
        "technical": _technical_snapshot(closes),
    }


def _enrich_quote(quote: dict[str, Any]) -> dict[str, Any]:
    symbol = str(quote.get("symbol") or "")
    enriched = dict(quote)
    enriched["company_name"] = company_name_for_symbol(symbol)
    enriched.update(_fetch_fundamental_snapshot(symbol))
    return enriched


def _fetch_fundamental_snapshot(symbol: str) -> dict[str, Any]:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return {
            "financials": _extract_financials(ticker),
            "analyst": {
                "recommendation": info.get("recommendationKey"),
                "target_mean_price": _round_optional(info.get("targetMeanPrice")),
                "target_high_price": _round_optional(info.get("targetHighPrice")),
                "target_low_price": _round_optional(info.get("targetLowPrice")),
                "analyst_count": info.get("numberOfAnalystOpinions"),
            },
        }
    except Exception as exc:
        return {
            "financials": None,
            "analyst": None,
            "fundamentals_error": str(exc),
        }


def _extract_financials(ticker: Any) -> dict[str, Any] | None:
    statement = getattr(ticker, "quarterly_income_stmt", None)
    if statement is None or getattr(statement, "empty", True):
        statement = getattr(ticker, "quarterly_financials", None)
    if statement is None or getattr(statement, "empty", True):
        return None

    latest_revenue = _statement_value(statement, "Total Revenue", 0)
    previous_revenue = _statement_value(statement, "Total Revenue", 1)
    latest_net_income = _statement_value(statement, "Net Income", 0)
    previous_net_income = _statement_value(statement, "Net Income", 1)

    return {
        "period": str(statement.columns[0]) if len(statement.columns) else None,
        "revenue": _round_optional(latest_revenue),
        "revenue_change_pct": _pct_change(latest_revenue, previous_revenue),
        "net_income": _round_optional(latest_net_income),
        "net_income_change_pct": _pct_change(latest_net_income, previous_net_income),
    }


def _statement_value(statement: Any, row: str, column_index: int) -> float | None:
    try:
        if row not in statement.index or len(statement.columns) <= column_index:
            return None
        return _safe_float(statement.loc[row].iloc[column_index])
    except Exception:
        return None


def _technical_snapshot(closes: list[Any]) -> dict[str, Any] | None:
    valid_closes = [_safe_float(value) for value in closes]
    valid_closes = [value for value in valid_closes if value is not None]
    if not valid_closes:
        return None

    # Support/resistance = the last 20 sessions' range.
    recent = valid_closes[-20:]
    return {
        "support": round(min(recent), 2),
        "resistance": round(max(recent), 2),
        "moving_average_20": _simple_moving_average(valid_closes, 20),
        "moving_average_50": _simple_moving_average(valid_closes, 50),
    }


def _simple_moving_average(closes: list[float], window: int) -> float | None:
    """Average of the last `window` closes, or None when there isn't enough history.

    Returning None rather than averaging whatever is available keeps the label
    honest — a "50-day average" built from 5 points is not a 50-day average.
    """
    if len(closes) < window:
        return None
    return round(sum(closes[-window:]) / window, 2)


def _latest_value_index(values: list[Any]) -> int | None:
    for index in range(len(values) - 1, -1, -1):
        if values[index] is not None:
            return index
    return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_optional(value: Any, digits: int = 2) -> float | None:
    numeric = _safe_float(value)
    return round(numeric, digits) if numeric is not None else None


def _pct_change(current: Any, previous: Any) -> float | None:
    current_value = _safe_float(current)
    previous_value = _safe_float(previous)
    if current_value is None or previous_value in (None, 0):
        return None
    return round(((current_value - previous_value) / previous_value) * 100, 2)


def _unavailable_quote(symbol: str, reason: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "company_name": company_name_for_symbol(symbol),
        "price": None,
        "change_pct": None,
        "volume": 0,
        "technical": None,
        "financials": None,
        "analyst": None,
        "error": reason,
    }
