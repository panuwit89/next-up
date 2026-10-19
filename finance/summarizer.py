from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests

from finance.brief_format import NOTE_LIMIT, CompanyBrief, build_company_brief
from finance.config import get_settings
from finance.services.symbols import extract_stock_symbols


logger = logging.getLogger("finance_bot.summarizer")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Gemini answers 503 ("model overloaded") in short bursts; a couple of spaced
# retries usually get through before falling back to raw headlines.
GEMINI_RETRY_STATUSES = {429, 500, 502, 503, 504}
GEMINI_RETRY_DELAYS = (3, 8)  # seconds before the 2nd and 3rd attempts

# Gemini no longer writes the message itself: the layout (and every number in
# it) is built in finance.brief_format. Gemini only writes the short notes.
SYSTEM_PROMPT = """
You write short Thai notes for a stock brief in a LINE bot.
The app already shows the reader each stock's price, % change, 20-day range and
moving averages, so do not repeat those numbers.

Use only the provided financial, analyst, and news data.
Do not invent earnings, analyst calls, or news.

Write:
- "notes": for each symbol, one Thai sentence (at most 120 characters) on the
  company-specific news or the point worth watching. Use "" when there is no
  usable company-specific news for that symbol.
- "overview": one Thai sentence (at most 120 characters) on the watchlist as a whole.

If a user query is given, slant the notes toward answering it.
Never give buy/sell instructions. No URLs, no Markdown.

Reply with JSON only, in this shape:
{"overview": "...", "notes": {"SYMBOL": "..."}}
""".strip()

HUMAN_TEMPLATE = """
Mode: {mode}
Symbols: {symbols}
User query: {query}

Stock / financial / analyst / technical data:
{stock_data}

Company news:
{news_data}
""".strip()


def summarize_company_brief(
    *,
    stock_data: Any,
    news_data: Any,
    query: str | None = None,
) -> CompanyBrief:
    """Build the brief. Notes come from Gemini when a key is set, otherwise from raw headlines."""
    settings = get_settings()
    stocks = _filter_stocks(stock_data, extract_stock_symbols(query))
    news_by_symbol = _group_news_by_symbol(news_data)
    symbols = [str(item.get("symbol")) for item in stocks if item.get("symbol")]

    notes = _headline_notes(symbols, news_by_symbol)
    overview = ""
    if settings.has_llm_key and symbols:
        try:
            notes, overview = _gemini_notes(
                settings=settings,
                stocks=stocks,
                news_data=news_data,
                query=query,
                symbols=symbols,
            )
        except Exception as exc:
            # Never let an LLM/network hiccup drop the scheduled brief — fall back to raw headlines.
            logger.warning("Gemini notes failed, using raw headlines: %s", exc)

    return build_company_brief(
        stocks=stocks,
        notes=notes,
        overview=overview,
        title="สรุปหุ้น" if query else "Watchlist ประจำสัปดาห์",
        now=_now(settings.TIMEZONE),
        dashboard_url=settings.dashboard_url,
        news_links=_news_links(news_by_symbol),
    )


summarize_daily_brief = summarize_company_brief


def _gemini_notes(
    *,
    settings: Any,
    stocks: list[dict[str, Any]],
    news_data: Any,
    query: str | None,
    symbols: list[str],
) -> tuple[dict[str, str], str]:
    human_message = HUMAN_TEMPLATE.format(
        mode="on-demand" if query else "weekly-watchlist",
        symbols=", ".join(symbols),
        query=query or "-",
        stock_data=_to_json(stocks),
        news_data=_to_json(news_data),
    )

    request_body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {"role": "user", "parts": [{"text": human_message}]},
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    payload = _post_gemini(settings, request_body)

    candidates = payload.get("candidates") or []
    if not candidates:
        # e.g. prompt blocked by safety filters — let the caller fall back.
        raise RuntimeError(f"Gemini returned no candidates: {payload.get('promptFeedback')}")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    content = "".join(part.get("text", "") for part in parts).strip()
    if not content:
        raise RuntimeError("Gemini returned an empty message.")
    return _parse_notes(content, symbols)


def _post_gemini(settings: Any, request_body: dict[str, Any]) -> dict[str, Any]:
    """POST to Gemini, retrying the transient "overloaded" answers (429/5xx).

    Timeouts are not retried: the on-demand path answers a LINE reply token
    that expires after about a minute, and three 30s timeouts would outlive it.
    """
    for attempt, delay in enumerate((*GEMINI_RETRY_DELAYS, None), start=1):
        try:
            response = requests.post(
                GEMINI_URL.format(model=settings.GEMINI_MODEL),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": settings.gemini_api_key,
                },
                json=request_body,
                timeout=30,
            )
        except requests.ConnectionError as exc:
            # ConnectTimeout is also a ConnectionError; let it fail like any timeout.
            if delay is None or isinstance(exc, requests.Timeout):
                raise
            logger.warning("Gemini attempt %s failed (%s), retrying in %ss.", attempt, exc, delay)
        else:
            if response.status_code not in GEMINI_RETRY_STATUSES or delay is None:
                response.raise_for_status()
                return response.json()
            logger.warning(
                "Gemini attempt %s returned HTTP %s, retrying in %ss.", attempt, response.status_code, delay
            )
        time.sleep(delay)
    raise AssertionError("unreachable")


def _parse_notes(content: str, symbols: list[str]) -> tuple[dict[str, str], str]:
    # JSON mode should return bare JSON, but tolerate a ```json fence anyway.
    cleaned = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise RuntimeError("Gemini notes were not a JSON object.")

    raw_notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    notes = {
        symbol: _clip(raw_notes.get(symbol))
        for symbol in symbols
        if isinstance(raw_notes.get(symbol), str)
    }
    return notes, _clip(data.get("overview"))


def _headline_notes(symbols: list[str], news_by_symbol: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    """Fallback notes: the latest raw headline per symbol."""
    notes: dict[str, str] = {}
    for symbol in symbols:
        headlines = news_by_symbol.get(symbol, [])
        title = next((item.get("title") for item in headlines if item.get("title")), "")
        if title:
            notes[symbol] = _clip(title)
        elif any(item.get("error") for item in headlines):
            notes[symbol] = "ยังดึงข่าวเฉพาะบริษัทไม่ได้ตอนนี้"
    return notes


def _news_links(news_by_symbol: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    links: dict[str, str] = {}
    for symbol, headlines in news_by_symbol.items():
        url = next((item.get("url") for item in headlines if item.get("url")), "")
        if url:
            links[symbol] = str(url)
    return links


def _filter_stocks(stock_data: Any, requested_symbols: list[str]) -> list[dict[str, Any]]:
    stocks = [item for item in stock_data or [] if isinstance(item, dict)]
    if not requested_symbols:
        return stocks
    requested = set(requested_symbols)
    return [item for item in stocks if item.get("symbol") in requested]


def _group_news_by_symbol(news_data: Any) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in news_data or []:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        if not symbol:
            continue
        grouped.setdefault(str(symbol), []).append(item)
    return grouped


def _now(tz_name: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_name))
    except Exception:
        # Windows without the tzdata package has no zone database.
        return datetime.now(timezone(timedelta(hours=7)))


def _clip(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    return text if len(text) <= NOTE_LIMIT else text[: NOTE_LIMIT - 1] + "…"


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
