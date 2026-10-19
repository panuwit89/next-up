"""Lay out a stock brief as a LINE Flex carousel.

The first card is an overview of the whole watchlist, then one swipeable card
per stock, biggest movers first.

Every number shown here comes straight from the quote data. Gemini only
supplies the one-line notes, so a model slip can't put a wrong price in front
of the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


UP = "#16A34A"
DOWN = "#DC2626"
FLAT = "#6B7280"
MUTED = "#6B7280"
SUBTLE = "#9CA3AF"
TRACK = "#E5E7EB"
RANGE_FILL = "#2563EB"

ALT_TEXT_LIMIT = 400  # LINE's cap for a Flex message's altText
MAX_STOCK_CARDS = 11  # a carousel holds 12 bubbles; the first is the overview
NOTE_LIMIT = 160

THAI_MONTHS = (
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
)
DISCLAIMER = "การลงทุนมีความเสี่ยง ข้อมูลนี้ไม่ใช่คำแนะนำซื้อขาย"


@dataclass(frozen=True)
class CompanyBrief:
    # One-line summary: the carousel's notification text, or the whole message
    # when there is no carousel.
    alt_text: str
    # Flex carousel container, or None when there is no stock to show a card for.
    flex: dict[str, Any] | None


def build_company_brief(
    *,
    stocks: list[dict[str, Any]],
    notes: dict[str, str],
    overview: str,
    title: str,
    now: datetime,
    dashboard_url: str = "",
    news_links: dict[str, str] | None = None,
) -> CompanyBrief:
    ordered = _order_by_move(stocks)
    date_label = _thai_date(now)
    news_links = news_links or {}
    return CompanyBrief(
        alt_text=_build_alt_text(ordered, title, date_label),
        flex=_build_carousel(ordered, notes, overview, title, date_label, dashboard_url, news_links),
    )


def _build_alt_text(stocks: list[dict[str, Any]], title: str, date_label: str) -> str:
    if not stocks:
        return f"📊 {title} · {date_label}\nยังไม่มีข้อมูลหุ้นสำหรับ watchlist ตอนนี้"
    parts = []
    for item in stocks:
        _, pct = _headline_change(item)
        parts.append(f"{item.get('symbol')} {_pct(pct)}" if item.get("price") is not None else str(item.get("symbol")))
    text = f"{title}: " + ", ".join(parts)
    return text if len(text) <= ALT_TEXT_LIMIT else text[: ALT_TEXT_LIMIT - 1] + "…"


# ------------------------------------------------------------------ flex --


def _build_carousel(
    stocks: list[dict[str, Any]],
    notes: dict[str, str],
    overview: str,
    title: str,
    date_label: str,
    dashboard_url: str,
    news_links: dict[str, str],
) -> dict[str, Any] | None:
    if not stocks:
        return None
    shown = stocks[:MAX_STOCK_CARDS]
    bubbles = [_overview_bubble(stocks, overview, title, date_label)]
    for item in shown:
        symbol = str(item.get("symbol"))
        bubbles.append(
            _stock_bubble(item, notes.get(symbol, ""), dashboard_url, news_links.get(symbol, ""))
        )
    return {"type": "carousel", "contents": bubbles}


def _overview_bubble(
    stocks: list[dict[str, Any]],
    overview: str,
    title: str,
    date_label: str,
) -> dict[str, Any]:
    priced = [item for item in stocks if item.get("price") is not None]
    changes = [_headline_change(item)[1] for item in priced]
    period = _headline_change(priced[0])[0] if priced else "1W"
    ups = sum(1 for pct in changes if pct is not None and pct > 0)
    downs = sum(1 for pct in changes if pct is not None and pct < 0)

    rows: list[dict[str, Any]] = []
    for item in stocks:
        label, pct = _headline_change(item)
        has_price = item.get("price") is not None
        rows.append(
            {
                "type": "box",
                "layout": "horizontal",
                "margin": "md",
                "contents": [
                    _text(str(item.get("symbol")), size="sm", weight="bold", flex=3),
                    _text(_price(item.get("price")) if has_price else "—", size="sm", color=MUTED, align="end", flex=4),
                    _text(_pct(pct) if has_price else "n/a", size="sm", weight="bold", color=_color(pct), align="end", flex=3),
                ],
            }
        )

    contents: list[dict[str, Any]] = [
        _text(f"📊 {title}", size="lg", weight="bold", wrap=True),
        _text(date_label, size="xs", color=MUTED),
        {
            "type": "box",
            "layout": "horizontal",
            "margin": "lg",
            "spacing": "lg",
            "contents": [
                _text(f"▲ ขึ้น {ups}", size="sm", weight="bold", color=UP, flex=0),
                _text(f"▼ ลง {downs}", size="sm", weight="bold", color=DOWN, flex=0),
            ],
        },
        {"type": "separator", "margin": "lg"},
        _text(f"เปลี่ยนแปลง {period}", size="xxs", color=SUBTLE, align="end", margin="md"),
        *rows,
    ]
    if overview:
        contents += [{"type": "separator", "margin": "lg"}, _text(f"📝 {overview}", size="sm", wrap=True, margin="lg")]

    return {
        "type": "bubble",
        "size": "mega",
        "body": {"type": "box", "layout": "vertical", "contents": contents},
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                _text("ปัดเพื่อดูรายตัว →", size="xs", color=MUTED, align="end"),
                _text(DISCLAIMER, size="xxs", color=SUBTLE, wrap=True, margin="sm"),
            ],
        },
    }


def _stock_bubble(item: dict[str, Any], note: str, dashboard_url: str, news_url: str) -> dict[str, Any]:
    symbol = str(item.get("symbol"))
    _, pct = _headline_change(item)
    company = _company(item)

    header_row = {
        "type": "box",
        "layout": "horizontal",
        "contents": [
            _text(symbol, size="xl", weight="bold", flex=1),
            _text(
                f"{_arrow(pct)} {_pct(pct)}" if item.get("price") is not None else "n/a",
                size="sm",
                weight="bold",
                color=_color(pct),
                align="end",
                gravity="center",
                flex=0,
            ),
        ],
    }
    contents: list[dict[str, Any]] = [header_row]
    if company:
        contents.append(_text(company, size="xs", color=MUTED, wrap=True))

    if item.get("price") is None:
        contents.append(_text("ยังดึงราคาล่าสุดไม่ได้ตอนนี้", size="sm", color=MUTED, wrap=True, margin="lg"))
        return {"type": "bubble", "size": "mega", "body": {"type": "box", "layout": "vertical", "contents": contents}}

    contents.append(_text(_price(item.get("price")), size="3xl", weight="bold", margin="md"))
    change_parts = _change_parts(item)
    if change_parts:
        contents.append(_text(" · ".join(change_parts), size="xs", color=MUTED))

    contents += _range_section(item)
    contents += _ma_section(item)

    extras = [line for line in (_financial_text(item), _analyst_text(item)) if line]
    if extras:
        contents.append({"type": "separator", "margin": "lg"})
        contents += [_text(line, size="xs", color=MUTED, wrap=True, margin="md") for line in extras]

    if note:
        contents += [{"type": "separator", "margin": "lg"}, _text(f"💬 {note}", size="sm", wrap=True, margin="lg")]

    bubble: dict[str, Any] = {
        "type": "bubble",
        "size": "mega",
        "body": {"type": "box", "layout": "vertical", "contents": contents},
    }
    buttons = []
    if _is_web_url(news_url):
        buttons.append(_link_button("อ่านข่าว", news_url))
    if dashboard_url:
        buttons.append(_link_button("ดูกราฟ", f"{dashboard_url}/#/finance/{symbol}"))
    if buttons:
        bubble["footer"] = {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": buttons}
    return bubble


def _range_section(item: dict[str, Any]) -> list[dict[str, Any]]:
    position, label = _range_position(item)
    if position is None:
        return []
    technical = item.get("technical") or {}
    # Keep a sliver of fill so a price at (or below) support still shows a bar.
    fill = max(3, round(position * 100))
    return [
        {"type": "separator", "margin": "lg"},
        {
            "type": "box",
            "layout": "horizontal",
            "margin": "lg",
            "contents": [
                _text("กรอบ 20 วัน", size="xs", color=MUTED),
                _text(label, size="xs", weight="bold", color=_range_color(position, item), align="end"),
            ],
        },
        {
            "type": "box",
            "layout": "vertical",
            "margin": "sm",
            "height": "6px",
            "cornerRadius": "3px",
            "backgroundColor": TRACK,
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "width": f"{fill}%",
                    "height": "6px",
                    "cornerRadius": "3px",
                    "backgroundColor": RANGE_FILL,
                    "contents": [{"type": "filler"}],
                }
            ],
        },
        {
            "type": "box",
            "layout": "horizontal",
            "margin": "xs",
            "contents": [
                _text(_price(technical.get("support")), size="xxs", color=SUBTLE),
                _text(_price(technical.get("resistance")), size="xxs", color=SUBTLE, align="end"),
            ],
        },
    ]


def _ma_section(item: dict[str, Any]) -> list[dict[str, Any]]:
    label = _ma_label(item)
    if not label:
        return []
    return [
        _text(label, size="sm", weight="bold", margin="lg", wrap=True),
        _text(_ma_values(item), size="xs", color=MUTED),
    ]


def _text(text: str, **props: Any) -> dict[str, Any]:
    # LINE rejects a Flex text component whose text is empty.
    return {"type": "text", "text": text or "-", **props}


def _link_button(label: str, uri: str) -> dict[str, Any]:
    return {
        "type": "button",
        "style": "link",
        "height": "sm",
        "action": {"type": "uri", "label": label, "uri": uri},
    }


# --------------------------------------------------------------- shared --


def _order_by_move(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Biggest movers first; stocks without a price go last."""

    def key(item: dict[str, Any]) -> tuple[int, float]:
        _, pct = _headline_change(item)
        if item.get("price") is None or pct is None:
            return (1, 0.0)
        return (0, -abs(pct))

    return sorted(stocks, key=key)


def _headline_change(item: dict[str, Any]) -> tuple[str, float | None]:
    """The move a weekly brief leads with: one week, or one day when that's all there is."""
    week = _number(item.get("week_change_pct"))
    if week is not None:
        return "1W", week
    return "1D", _number(item.get("change_pct"))


def _change_parts(item: dict[str, Any]) -> list[str]:
    parts = []
    day = _number(item.get("change_pct"))
    week = _number(item.get("week_change_pct"))
    if day is not None:
        parts.append(f"1D {_pct(day)}")
    if week is not None:
        parts.append(f"1W {_pct(week)}")
    return parts


def _range_position(item: dict[str, Any]) -> tuple[float | None, str]:
    technical = item.get("technical") or {}
    price = _number(item.get("price"))
    support = _number(technical.get("support"))
    resistance = _number(technical.get("resistance"))
    if price is None or support is None or resistance is None or resistance <= support:
        return None, ""

    if price < support:
        return 0.0, "หลุดกรอบล่าง"
    if price > resistance:
        return 1.0, "ทะลุกรอบบน"
    position = (price - support) / (resistance - support)
    if position <= 0.2:
        return position, "ใกล้ขอบล่าง"
    if position >= 0.8:
        return position, "ใกล้ขอบบน"
    return position, "กลางกรอบ"


def _range_color(position: float, item: dict[str, Any]) -> str:
    price = _number(item.get("price"))
    support = _number((item.get("technical") or {}).get("support"))
    if price is not None and support is not None and price < support:
        return DOWN
    if position >= 1.0:
        return UP
    return MUTED


def _ma_label(item: dict[str, Any]) -> str:
    technical = item.get("technical") or {}
    price = _number(item.get("price"))
    ma20 = _number(technical.get("moving_average_20"))
    ma50 = _number(technical.get("moving_average_50"))
    if price is None or (ma20 is None and ma50 is None):
        return ""
    if ma50 is None:
        return "เหนือ MA20" if price >= ma20 else "ต่ำกว่า MA20"
    if ma20 is None:
        return "เหนือ MA50" if price >= ma50 else "ต่ำกว่า MA50"

    above20, above50 = price >= ma20, price >= ma50
    if above20 and above50:
        return "เหนือ MA20 และ MA50"
    if not above20 and not above50:
        return "ต่ำกว่า MA20 และ MA50"
    if above50:
        return "เหนือ MA50 แต่ต่ำกว่า MA20"
    return "เหนือ MA20 แต่ต่ำกว่า MA50"


def _ma_values(item: dict[str, Any]) -> str:
    technical = item.get("technical") or {}
    parts = []
    for label, key in (("MA20", "moving_average_20"), ("MA50", "moving_average_50")):
        value = _number(technical.get(key))
        if value is not None:
            parts.append(f"{label} {_price(value)}")
    return " · ".join(parts)


def _financial_text(item: dict[str, Any]) -> str:
    financials = item.get("financials")
    if not isinstance(financials, dict):
        return ""
    parts = []
    revenue = _number(financials.get("revenue"))
    if revenue is not None:
        parts.append(f"รายได้ {_large_number(revenue)}{_pct_suffix(financials.get('revenue_change_pct'))}")
    net_income = _number(financials.get("net_income"))
    if net_income is not None:
        parts.append(f"กำไร {_large_number(net_income)}{_pct_suffix(financials.get('net_income_change_pct'))}")
    return "งบล่าสุด: " + " · ".join(parts) if parts else ""


def _analyst_text(item: dict[str, Any]) -> str:
    analyst = item.get("analyst")
    if not isinstance(analyst, dict):
        return ""
    parts = []
    recommendation = analyst.get("recommendation")
    if recommendation and recommendation != "none":
        parts.append(str(recommendation).replace("_", " ").upper())
    target = _number(analyst.get("target_mean_price"))
    if target is not None:
        parts.append(f"เป้าเฉลี่ย {_price(target)}")
    count = analyst.get("analyst_count")
    if count:
        parts.append(f"{count} ราย")
    return "นักวิเคราะห์: " + " · ".join(parts) if parts else ""


def _company(item: dict[str, Any]) -> str:
    company = item.get("company_name")
    return str(company) if company and company != item.get("symbol") else ""


def _thai_date(now: datetime) -> str:
    return f"{now.day} {THAI_MONTHS[now.month - 1]} {now.year}"


def _arrow(pct: float | None) -> str:
    if pct is None or pct == 0:
        return "•"
    return "▲" if pct > 0 else "▼"


def _color(pct: float | None) -> str:
    if pct is None or pct == 0:
        return FLAT
    return UP if pct > 0 else DOWN


def _is_web_url(value: str) -> bool:
    return value.startswith(("https://", "http://")) and len(value) <= 1000


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _price(value: Any) -> str:
    numeric = _number(value)
    return f"${numeric:,.2f}" if numeric is not None else "n/a"


def _pct(value: Any) -> str:
    numeric = _number(value)
    return f"{numeric:+.2f}%" if numeric is not None else "n/a"


def _pct_suffix(value: Any) -> str:
    numeric = _number(value)
    return f" ({numeric:+.1f}% QoQ)" if numeric is not None else ""


def _large_number(value: float) -> str:
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    return f"${value:,.0f}"
