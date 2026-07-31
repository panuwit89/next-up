from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from finance.watchlist import add_symbol, get_watchlist_symbols, remove_symbol
from web.cache import cache_invalidate
from web.stock_service import RANGE_INTERVALS, fetch_dashboard, fetch_detail, fetch_symbol_news


router = APIRouter(prefix="/api/stocks", tags=["stocks"])


class AddSymbolRequest(BaseModel):
    symbol: str = Field(min_length=1)


@router.get("")
async def dashboard() -> dict[str, Any]:
    symbols = await run_in_threadpool(get_watchlist_symbols)
    rows = await run_in_threadpool(fetch_dashboard, symbols)
    return {"symbols": symbols, "stocks": rows}


@router.post("")
async def add_stock(payload: AddSymbolRequest) -> dict[str, Any]:
    try:
        symbol = await run_in_threadpool(add_symbol, payload.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "added", "symbol": symbol}


@router.delete("/{symbol}")
async def remove_stock(symbol: str) -> dict[str, Any]:
    try:
        removed = await run_in_threadpool(remove_symbol, symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not removed:
        raise HTTPException(status_code=404, detail=f"{symbol} is not in the watchlist.")

    await run_in_threadpool(cache_invalidate, f"chart:{symbol.upper()}")
    return {"status": "removed", "symbol": symbol.upper()}


@router.get("/{symbol}")
async def stock_detail(
    symbol: str,
    range: str = Query(default="1d", description=f"One of: {', '.join(RANGE_INTERVALS)}"),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(fetch_detail, symbol.upper(), range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream data error: {exc}") from exc


@router.get("/{symbol}/news")
async def stock_news(symbol: str, limit: int = Query(default=5, ge=1, le=10)) -> dict[str, Any]:
    articles = await run_in_threadpool(fetch_symbol_news, symbol.upper(), limit)
    return {"symbol": symbol.upper(), "articles": articles}
