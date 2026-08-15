from __future__ import annotations

import re


SYMBOL_PATTERN = re.compile(r"\$?[A-Za-z][A-Za-z0-9.-]{0,9}")
ALIAS_PATTERN = re.compile(r"[A-Za-z0-9]+")

QUERY_STOP_WORDS = {
    "A",
    "ABOUT",
    "AND",
    "BRIEF",
    "CHECK",
    "COMPANY",
    "DAILY",
    "EARNINGS",
    "FINANCIAL",
    "FINANCIALS",
    "FOR",
    "INVEST",
    "INVESTING",
    "INVESTMENT",
    "LATEST",
    "MARKET",
    "ME",
    "NEWS",
    "OF",
    "ON",
    "PLEASE",
    "PRICE",
    "QUOTE",
    "REPORT",
    "RESISTANCE",
    "SHOW",
    "STOCK",
    "STOCKS",
    "SUMMARY",
    "SUMMARIZE",
    "SUPPORT",
    "THE",
    "TODAY",
    "UPDATE",
    "UPDATES",
    "WHAT",
}

COMPANY_ALIASES = {
    "APPLE": "AAPL",
    "AAPL": "AAPL",
    "GOOGLE": "GOOGL",
    "ALPHABET": "GOOGL",
    "GOOGL": "GOOGL",
    "MICROSOFT": "MSFT",
    "MSFT": "MSFT",
    "NVIDIA": "NVDA",
    "NVDA": "NVDA",
    "TESLA": "TSLA",
    "TSLA": "TSLA",
    "TSM": "TSM",
    "TSMC": "TSM",
    "TAIWANSEMICONDUCTOR": "TSM",
    "TAIWANSEMICONDUCTORMANUFACTURING": "TSM",
}

COMPANY_NAMES = {
    "AAPL": "Apple",
    "GOOGL": "Alphabet",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "TSM": "Taiwan Semiconductor Manufacturing",
}

COMPANY_NEWS_QUERIES = {
    "AAPL": '"Apple" OR AAPL',
    "GOOGL": '"Alphabet" OR Google OR GOOGL',
    "MSFT": '"Microsoft" OR MSFT',
    "NVDA": '"NVIDIA" OR NVDA',
    "TSLA": '"Tesla" OR TSLA',
    "TSM": '"Taiwan Semiconductor" OR TSMC OR TSM',
}

MAX_QUERY_SYMBOLS = 5


def extract_stock_symbols(query: str | None) -> list[str]:
    if not query:
        return []

    symbols: list[str] = []
    _add_alias_matches(query, symbols)

    for match in SYMBOL_PATTERN.finditer(query):
        try:
            symbol = resolve_stock_symbol(match.group(0))
        except ValueError:
            continue
        if symbol in QUERY_STOP_WORDS or symbol in symbols:
            continue
        symbols.append(symbol)
        if len(symbols) >= MAX_QUERY_SYMBOLS:
            break
    return symbols


def resolve_stock_symbol(value: str) -> str:
    normalized = _normalize_alias_key(value)
    alias = COMPANY_ALIASES.get(normalized)
    if alias:
        return alias
    return normalize_stock_symbol(value)


def normalize_stock_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper().lstrip("$")
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", normalized):
        raise ValueError(f"Invalid stock symbol: {symbol!r}")
    return normalized


def is_stock_symbol_query(query: str | None) -> bool:
    return bool(extract_stock_symbols(query))


def company_name_for_symbol(symbol: str) -> str:
    resolved = resolve_stock_symbol(symbol)
    return COMPANY_NAMES.get(resolved, resolved)


# Legal-entity suffixes that never appear in a headline. "Group" is deliberately
# absent — it is part of the brand often enough that dropping it loses meaning.
# Compared with dots removed, so "N.V." and "NV" both match the same entry.
CORPORATE_SUFFIXES = (
    "incorporated", "inc", "corporation", "corp", "company", "co",
    "limited", "ltd", "plc", "llc", "holdings", "holding",
    "nv", "sa", "ag", "a/s", "se", "ab", "oyj",
)


def company_news_query(symbol: str, company_name: str | None = None) -> str:
    """Build a NewsAPI query that actually filters to this company.

    The old fallback was `"SYM" OR SYM stock`. The second half is unquoted, so
    NewsAPI matched it loosely and returned generic market coverage — 39,000
    results for QQQM, none of it about QQQM. Showing unrelated headlines under a
    ticker is worse than showing none, so the fallback is now an exact match on
    the ticker alone, and a company name is used whenever one is known.
    """
    resolved = resolve_stock_symbol(symbol)

    known = COMPANY_NEWS_QUERIES.get(resolved)
    if known:
        return known

    trimmed = strip_corporate_suffix(company_name or "")
    if trimmed and trimmed.casefold() != resolved.casefold():
        return f'"{trimmed}" OR {resolved}'

    return f'"{resolved}"'


def strip_corporate_suffix(name: str) -> str:
    """'SanDisk Corporation' -> 'SanDisk'. Headlines use the short form."""
    words = name.replace(",", " ").split()
    while words and words[-1].replace(".", "").casefold() in CORPORATE_SUFFIXES:
        words.pop()
    return " ".join(words).strip()


def _add_alias_matches(query: str, symbols: list[str]) -> None:
    alias_key = _normalize_alias_key(query)
    matches = []
    for alias, symbol in COMPANY_ALIASES.items():
        position = alias_key.find(alias)
        if position >= 0:
            matches.append((position, symbol))

    for _, symbol in sorted(matches, key=lambda item: item[0]):
        if symbol not in symbols:
            symbols.append(symbol)
            if len(symbols) >= MAX_QUERY_SYMBOLS:
                return


def _normalize_alias_key(value: str) -> str:
    return "".join(ALIAS_PATTERN.findall(value.upper().lstrip("$")))
