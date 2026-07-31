from __future__ import annotations

import json
import logging
from typing import Any

import requests

from finance.config import get_settings
from finance.services.symbols import extract_stock_symbols


logger = logging.getLogger("finance_bot.summarizer")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """
You are a careful financial brief writer for a LINE bot.
Write in Thai, concise and practical.

Use only the provided stock, financial, analyst, technical, and news data.
Do not invent prices, earnings, analyst calls, or news.
If data is missing, say it is unavailable.

Output rules:
- Use bullet points (•)
- Group the answer by company when multiple symbols are present
- Include price, % change, support/resistance when available
- Include financial and analyst snapshot when available
- Include company-specific news only
- Do not give direct buy/sell instructions
- Use "ประเด็นที่ต้องติดตาม" or "มุมมองประกอบ" instead of investment advice
- End with one short risk/disclaimer sentence
- Do NOT include URLs
""".strip()

HUMAN_TEMPLATE = """
Mode: {mode}
Focus symbols: {focus_symbols}
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
) -> str:
    """Build the Thai brief. Uses Gemini when a key is set, otherwise a deterministic fallback."""
    requested_symbols = extract_stock_symbols(query)
    settings = get_settings()

    if not settings.has_llm_key:
        return fallback_company_brief(
            stock_data=stock_data,
            news_data=news_data,
            requested_symbols=requested_symbols,
        )

    try:
        return _gemini_company_brief(
            settings=settings,
            stock_data=stock_data,
            news_data=news_data,
            query=query,
            requested_symbols=requested_symbols,
        )
    except Exception as exc:
        # Never let an LLM/network hiccup drop the scheduled brief — fall back to raw data.
        logger.warning("Gemini summary failed, using fallback brief: %s", exc)
        return fallback_company_brief(
            stock_data=stock_data,
            news_data=news_data,
            requested_symbols=requested_symbols,
        )


summarize_daily_brief = summarize_company_brief


def _gemini_company_brief(
    *,
    settings: Any,
    stock_data: Any,
    news_data: Any,
    query: str | None,
    requested_symbols: list[str],
) -> str:
    human_message = HUMAN_TEMPLATE.format(
        mode="on-demand" if query else "weekly-watchlist",
        focus_symbols=", ".join(requested_symbols) if requested_symbols else "configured watchlist",
        query=query or "-",
        stock_data=_to_json(stock_data),
        news_data=_to_json(news_data),
    )

    response = requests.post(
        GEMINI_URL.format(model=settings.GEMINI_MODEL),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        },
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {"role": "user", "parts": [{"text": human_message}]},
            ],
            "generationConfig": {"temperature": 0.2},
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    candidates = payload.get("candidates") or []
    if not candidates:
        # e.g. prompt blocked by safety filters — let the caller fall back.
        raise RuntimeError(f"Gemini returned no candidates: {payload.get('promptFeedback')}")

    parts = (candidates[0].get("content") or {}).get("parts") or []
    content = "".join(part.get("text", "") for part in parts).strip()
    if not content:
        raise RuntimeError("Gemini returned an empty message.")
    return content


def fallback_company_brief(
    *,
    stock_data: Any,
    news_data: Any,
    requested_symbols: list[str] | None = None,
) -> str:
    stocks = _filter_stocks(stock_data, requested_symbols or [])
    news_by_symbol = _group_news_by_symbol(news_data)
    bullets: list[str] = []

    for item in stocks:
        symbol = item.get("symbol")
        company = item.get("company_name") or symbol
        price = item.get("price")
        if symbol is None:
            continue

        if price is None:
            bullets.append(f"• {symbol}: ยังดึงราคาล่าสุดไม่ได้ตอนนี้")
            continue

        technical = item.get("technical") or {}
        support = _format_price(technical.get("support"))
        resistance = _format_price(technical.get("resistance"))
        bullets.append(
            f"• {symbol} ({company}): ราคา {_format_price(price)} ({_format_pct(item.get('change_pct'))}), "
            f"แนวรับ {support}, แนวต้าน {resistance}"
        )

        financial_text = _financial_line(item.get("financials"))
        analyst_text = _analyst_line(item.get("analyst"))
        if financial_text or analyst_text:
            parts = [part for part in (financial_text, analyst_text) if part]
            bullets.append(f"• {symbol}: " + " | ".join(parts))

        headlines = news_by_symbol.get(str(symbol), [])[:2]
        if headlines:
            news_text = "; ".join(headline.get("title", "") for headline in headlines if headline.get("title"))
            if news_text:
                bullets.append(f"• {symbol} ข่าว: {news_text}")
            elif any(headline.get("error") for headline in headlines):
                bullets.append(f"• {symbol} ข่าว: ยังดึงข่าวเฉพาะบริษัทไม่ได้ตอนนี้")

    if not bullets:
        bullets.append("• ยังไม่มีข้อมูลหุ้นหรือข่าวสำหรับ watchlist ตอนนี้")

    bullets = bullets[:8]
    bullets.append("มุมมองประกอบ: ข้อมูลนี้ไม่ใช่คำสั่งซื้อขาย ควรตรวจสอบความเสี่ยงและแหล่งข้อมูลเพิ่มเติม")
    return "\n".join(bullets)


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


def _financial_line(financials: Any) -> str:
    if not isinstance(financials, dict):
        return ""
    revenue = _format_large_number(financials.get("revenue"))
    revenue_change = _format_pct(financials.get("revenue_change_pct"))
    net_income = _format_large_number(financials.get("net_income"))
    net_income_change = _format_pct(financials.get("net_income_change_pct"))
    return f"งบล่าสุด รายได้ {revenue} ({revenue_change}), กำไรสุทธิ {net_income} ({net_income_change})"


def _analyst_line(analyst: Any) -> str:
    if not isinstance(analyst, dict):
        return ""
    recommendation = analyst.get("recommendation") or "n/a"
    target = _format_price(analyst.get("target_mean_price"))
    count = analyst.get("analyst_count") or "n/a"
    return f"consensus นักวิเคราะห์ {recommendation}, ราคาเป้าหมายเฉลี่ย {target}, จำนวน {count} ราย"


def _format_price(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _format_large_number(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if abs(numeric) >= 1_000_000_000:
        return f"${numeric / 1_000_000_000:,.2f}B"
    if abs(numeric) >= 1_000_000:
        return f"${numeric / 1_000_000:,.2f}M"
    return f"${numeric:,.0f}"


def _format_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
