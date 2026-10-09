import { useCallback, useState } from "react";
import { ArrowSquareOut, CaretDown, CaretUp, Newspaper, Trash, X } from "@phosphor-icons/react";

import PriceChart from "./PriceChart.jsx";
import Button from "../components/Button.jsx";
import { Badge, EmptyState, ErrorState, Skeleton } from "../components/Feedback.jsx";
import { Drawer, useOverlayClose } from "../components/Overlay.jsx";
import { getStockDetail, getStockNews } from "../lib/api.js";
import { useAsync } from "../lib/hooks.js";
import {
  currencySign,
  formatCompact,
  formatNumber,
  formatPercent,
  formatPrice,
  formatSigned,
} from "../lib/format.js";

const RANGES = [
  { key: "1d", label: "1D" },
  { key: "5d", label: "5D" },
  { key: "1mo", label: "1M" },
  { key: "6mo", label: "6M" },
  { key: "ytd", label: "YTD" },
  { key: "1y", label: "1Y" },
  { key: "5y", label: "5Y" },
  { key: "max", label: "MAX" },
];

const MARKET_STATE_LABELS = {
  REGULAR: "Market open",
  PRE: "Pre-market",
  POST: "After hours",
  PREPRE: "Pre-market",
  POSTPOST: "Closed",
  CLOSED: "Market closed",
};

export default function StockDrawer({ symbol, onClose, onRemove }) {
  const [range, setRange] = useState("1d");
  const [showEma, setShowEma] = useState(true);

  const detail = useAsync(
    useCallback((signal) => getStockDetail(symbol, range, signal), [symbol, range]),
    [symbol, range],
  );
  const news = useAsync(
    useCallback((signal) => getStockNews(symbol, signal), [symbol]),
    [symbol],
  );

  const data = detail.data;
  const positive = (data?.change ?? 0) >= 0;
  const DirectionIcon = positive ? CaretUp : CaretDown;

  return (
    <Drawer open onClose={onClose} label={`${symbol} details`}>
      <header className="flex items-start gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="tabular text-lg font-semibold tracking-tight text-fg">{symbol}</h2>
            {data?.exchange ? <Badge>{data.exchange}</Badge> : null}
            {data?.market_state ? (
              <Badge tone={data.market_state === "REGULAR" ? "up" : "neutral"}>
                {MARKET_STATE_LABELS[data.market_state] ?? data.market_state}
              </Badge>
            ) : null}
          </div>
          <p className="mt-0.5 truncate text-sm text-fg-muted">
            {data?.company_name ?? <span className="opacity-0">placeholder</span>}
          </p>
        </div>
        <CloseButton />
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
        {detail.loading ? (
          <DetailSkeleton />
        ) : detail.error ? (
          <ErrorState error={detail.error} onRetry={detail.reload} />
        ) : (
          <>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="tabular text-3xl font-semibold tracking-tight text-fg">
                {formatPrice(data.price, data.currency)}
              </span>
              <span
                className={`tabular flex items-center gap-0.5 text-sm font-medium ${
                  positive ? "text-up" : "text-down"
                }`}
              >
                <DirectionIcon size={14} weight="fill" aria-hidden="true" />
                {formatSigned(data.change)} ({formatPercent(data.change_pct)})
              </span>
              {data.currency ? (
                <span className="text-xs text-fg-subtle">{data.currency}</span>
              ) : null}
            </div>

            <div
              role="tablist"
              aria-label="Chart range"
              className="mt-4 flex flex-wrap gap-1 border-b border-line pb-2"
            >
              {RANGES.map((option) => {
                const active = option.key === range;
                return (
                  <button
                    key={option.key}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setRange(option.key)}
                    className={[
                      "tabular cursor-pointer rounded-control px-2.5 py-1.5 text-xs font-semibold",
                      "transition-colors duration-150",
                      active
                        ? positive
                          ? "bg-up/15 text-up"
                          : "bg-down/15 text-down"
                        : "text-fg-subtle hover:bg-surface-2 hover:text-fg-muted",
                    ].join(" ")}
                  >
                    {option.label}
                  </button>
                );
              })}

              <label className="ml-auto flex cursor-pointer items-center gap-1.5 self-center text-xs text-fg-muted select-none">
                <input
                  type="checkbox"
                  checked={showEma}
                  onChange={(event) => setShowEma(event.target.checked)}
                  className="h-3.5 w-3.5 cursor-pointer accent-[var(--color-primary)]"
                />
                EMA
              </label>
            </div>

            <div className="mt-3">
              <PriceChart
                candles={data.candles ?? []}
                previousClose={data.previous_close}
                currency={data.currency}
                interval={data.interval}
                positive={positive}
                showEma={showEma}
              />
            </div>

            <Stats data={data} />

            <NewsSection news={news} />

            {/* Removing a symbol is fully reversible — the undo in the toast
                re-adds it — so this needs no confirmation step. */}
            <div className="mt-8 border-t border-line pt-4">
              <Button size="sm" variant="danger" onClick={() => onRemove(symbol)}>
                <Trash size={15} aria-hidden="true" />
                Remove from watchlist
              </Button>
            </div>
          </>
        )}
      </div>
    </Drawer>
  );
}

/** Rendered inside the Drawer so it can request an animated close. */
function CloseButton() {
  const requestClose = useOverlayClose();
  return (
    <Button variant="ghost" size="icon" onClick={requestClose} aria-label="Close details">
      <X size={18} weight="bold" aria-hidden="true" />
    </Button>
  );
}

function Stats({ data }) {
  const profile = data.profile ?? {};
  const sign = currencySign(data.currency);

  const rows = [
    ["Open", data.open === null || data.open === undefined ? "—" : sign + formatNumber(data.open)],
    ["Previous close", data.previous_close ? sign + formatNumber(data.previous_close) : "—"],
    ["Day high", data.day_high ? sign + formatNumber(data.day_high) : "—"],
    ["Day low", data.day_low ? sign + formatNumber(data.day_low) : "—"],
    [
      "52-week high",
      data.fifty_two_week_high ? sign + formatNumber(data.fifty_two_week_high) : "—",
    ],
    ["52-week low", data.fifty_two_week_low ? sign + formatNumber(data.fifty_two_week_low) : "—"],
    ["Market cap", profile.market_cap ? formatCompact(profile.market_cap) : "—"],
    ["P/E ratio", profile.pe_ratio ? formatNumber(profile.pe_ratio) : "—"],
    ["Forward P/E", profile.forward_pe ? formatNumber(profile.forward_pe) : "—"],
    ["Dividend yield", formatDividendYield(profile.dividend_yield)],
  ];

  return (
    <section className="mt-6">
      <h3 className="mb-2 text-sm font-semibold text-fg">Stats</h3>
      <dl className="grid grid-cols-2 gap-x-6">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="flex items-center justify-between border-b border-line py-2 text-sm"
          >
            <dt className="text-fg-muted">{label}</dt>
            <dd className="tabular font-medium text-fg">{value}</dd>
          </div>
        ))}
      </dl>
      {profile.sector ? (
        <p className="mt-2 text-xs text-fg-subtle">Sector · {profile.sector}</p>
      ) : null}
    </section>
  );
}

/**
 * yfinance reports `dividendYield` as a fraction on some versions and as a
 * percentage on others. Values at or below 1 are treated as fractions, which is
 * right for every yield except the ambiguous 0–1% band.
 */
function formatDividendYield(value) {
  if (!value) return "—";
  return `${formatNumber(value <= 1 ? value * 100 : value)}%`;
}

function NewsSection({ news }) {
  return (
    <section className="mt-6">
      <h3 className="mb-2 text-sm font-semibold text-fg">News</h3>

      {news.loading ? (
        <ul className="space-y-3">
          {Array.from({ length: 3 }, (_, index) => (
            <li key={index} className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-3 w-24" />
            </li>
          ))}
        </ul>
      ) : news.error ? (
        <ErrorState error={news.error} onRetry={news.reload} compact />
      ) : !news.data?.articles?.length ? (
        <EmptyState
          icon={Newspaper}
          title="No headlines right now"
          description="NewsAPI's free tier is rate-limited and results are cached for 6 hours."
        />
      ) : (
        <ul className="space-y-1">
          {news.data.articles.map((article) => (
            <li key={article.url}>
              <a
                href={article.url}
                target="_blank"
                rel="noreferrer"
                className="group -mx-2 flex gap-2 rounded-control px-2 py-2 transition-colors hover:bg-surface-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-snug font-medium text-fg group-hover:text-primary-fg">
                    {article.title}
                  </p>
                  <p className="mt-0.5 text-xs text-fg-subtle">{article.source}</p>
                </div>
                <ArrowSquareOut
                  size={14}
                  aria-hidden="true"
                  className="mt-1 shrink-0 text-fg-subtle opacity-0 transition-opacity group-hover:opacity-100"
                />
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DetailSkeleton() {
  return (
    <div>
      <Skeleton className="h-9 w-40" />
      <Skeleton className="mt-2 h-4 w-32" />
      <Skeleton className="mt-4 h-8 w-full" />
      <Skeleton className="mt-3 h-[300px] w-full" />
      <Skeleton className="mt-6 h-4 w-16" />
      <div className="mt-2 grid grid-cols-2 gap-x-6">
        {Array.from({ length: 10 }, (_, index) => (
          <Skeleton key={index} className="my-2 h-4 w-full" />
        ))}
      </div>
    </div>
  );
}
