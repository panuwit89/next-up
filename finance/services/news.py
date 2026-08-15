from __future__ import annotations

import requests

from finance.config import get_settings
from finance.services.market_data import get_company_name
from finance.services.symbols import company_news_query, resolve_stock_symbol


NEWSAPI_URL = "https://newsapi.org/v2/everything"
REQUEST_HEADERS = {"accept": "application/json", "user-agent": "finance-bot/1.0"}


def fetch_company_news(symbols: list[str], page_size_per_symbol: int = 3) -> list[dict[str, str]]:
    headlines = []
    for symbol in symbols:
        resolved_symbol = resolve_stock_symbol(symbol)
        # The company name makes the query search the brand ("SanDisk") instead
        # of only the ticker, which rarely appears in a headline.
        for item in fetch_news_headlines(
            query=company_news_query(resolved_symbol, get_company_name(resolved_symbol)),
            page_size=page_size_per_symbol,
        ):
            item["symbol"] = resolved_symbol
            headlines.append(item)
    return headlines


def fetch_news_headlines(query: str | None = None, page_size: int = 5) -> list[dict[str, str]]:
    settings = get_settings()
    if not settings.NEWSAPI_KEY:
        raise ValueError("NEWSAPI_KEY is required.")

    response = requests.get(
        NEWSAPI_URL,
        params={
            "q": query or settings.NEWS_QUERY,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": settings.NEWSAPI_KEY,
        },
        headers=REQUEST_HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    articles = payload.get("articles", [])[:page_size]

    headlines = []
    for article in articles:
        source = article.get("source") or {}
        headlines.append(
            {
                "title": article.get("title") or "",
                "source": source.get("name") or "Unknown",
                "url": article.get("url") or "",
            }
        )

    if not headlines:
        raise RuntimeError("No news headlines returned.")
    return headlines
