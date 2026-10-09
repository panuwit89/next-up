import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { formatCompact, formatDateTime, formatPrice, formatTime } from "../lib/format.js";

/**
 * Google-Finance-style price chart, hand-rolled in SVG.
 *
 * Deliberately not a chart library: this needs exactly one thing — an area line
 * tinted by direction, a dashed previous-close baseline, an optional EMA
 * overlay and a crosshair — and shipping ~90 kB of Recharts for that would be
 * the largest asset in the bundle.
 *
 * Accessibility: the plot is keyboard-navigable (arrow keys move the crosshair)
 * and carries a text summary, so the values are reachable without a pointer.
 */

const HEIGHT = 300;
const PRICE_TOP = 10;
const PRICE_BOTTOM = 224;
const VOLUME_TOP = 244;
const VOLUME_BOTTOM = 282;
const AXIS_Y = 296;
const PAD_X = 6;

const EMA_SERIES = [
  { key: "week_1", span: 5, label: "EMA 5", color: "#fbbf24" },
  { key: "week_2", span: 10, label: "EMA 10", color: "#a78bfa" },
  { key: "month_1", span: 21, label: "EMA 21", color: "#38bdf8" },
];

/** Same recurrence as `web/stock_service.py::_ema`, kept as a series. */
function emaSeries(closes, span) {
  if (closes.length < span) return [];
  const multiplier = 2 / (span + 1);
  const output = new Array(closes.length).fill(null);

  let value = closes.slice(0, span).reduce((sum, close) => sum + close, 0) / span;
  output[span - 1] = value;
  for (let index = span; index < closes.length; index += 1) {
    value = closes[index] * multiplier + value * (1 - multiplier);
    output[index] = value;
  }
  return output;
}

export default function PriceChart({
  candles,
  previousClose,
  currency,
  interval,
  positive,
  showEma,
}) {
  const wrapRef = useRef(null);
  const [width, setWidth] = useState(760);
  const [cursor, setCursor] = useState(null);

  useLayoutEffect(() => {
    const element = wrapRef.current;
    if (!element) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(320, entry.contentRect.width));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // A new range means a new dataset — drop a stale crosshair index.
  useEffect(() => setCursor(null), [candles]);

  const intraday = interval === "5m" || interval === "30m";
  // EMA windows are defined in *trading days*, so they are only truthful when
  // one candle is one day. On intraday or weekly bars they would silently mean
  // something else, and are hidden rather than mislabelled.
  const emaMeaningful = interval === "1d";

  const model = useMemo(() => {
    const closes = candles.map((candle) => candle.close);
    if (closes.length < 2) return null;

    const emas = emaMeaningful && showEma
      ? EMA_SERIES.map((series) => ({ ...series, values: emaSeries(closes, series.span) }))
      : [];

    const domainValues = [...closes];
    if (previousClose) domainValues.push(previousClose);
    for (const series of emas) {
      for (const value of series.values) if (value !== null) domainValues.push(value);
    }

    let min = Math.min(...domainValues);
    let max = Math.max(...domainValues);
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const headroom = (max - min) * 0.08;
    min -= headroom;
    max += headroom;

    const innerWidth = width - PAD_X * 2;
    const xAt = (index) => PAD_X + (index / (closes.length - 1)) * innerWidth;
    const yAt = (value) =>
      PRICE_BOTTOM - ((value - min) / (max - min)) * (PRICE_BOTTOM - PRICE_TOP);

    const line = closes.map((close, index) => `${xAt(index)},${yAt(close)}`).join(" L ");
    const linePath = `M ${line}`;
    const areaPath = `${linePath} L ${xAt(closes.length - 1)},${PRICE_BOTTOM} L ${PAD_X},${PRICE_BOTTOM} Z`;

    const emaPaths = emas.map((series) => {
      const segment = series.values
        .map((value, index) => (value === null ? null : `${xAt(index)},${yAt(value)}`))
        .filter(Boolean)
        .join(" L ");
      return { ...series, path: segment ? `M ${segment}` : null };
    });

    const maxVolume = Math.max(1, ...candles.map((candle) => candle.volume ?? 0));
    const barWidth = Math.max(1, innerWidth / closes.length - 0.6);

    // 5 evenly spaced ticks, snapped to real candles.
    const tickCount = Math.min(5, closes.length);
    const ticks = Array.from({ length: tickCount }, (_, position) => {
      const index = Math.round((position / (tickCount - 1)) * (closes.length - 1));
      return { index, x: xAt(index), timestamp: candles[index].timestamp };
    });

    return {
      closes,
      xAt,
      yAt,
      linePath,
      areaPath,
      emaPaths,
      maxVolume,
      barWidth,
      ticks,
      baselineY: previousClose ? yAt(previousClose) : null,
    };
  }, [candles, width, previousClose, showEma, emaMeaningful]);

  if (!model) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-card border border-dashed border-line text-sm text-fg-subtle">
        Not enough price data for this range.
      </div>
    );
  }

  const stroke = positive ? "var(--color-up)" : "var(--color-down)";
  const gradientId = positive ? "spark-up" : "spark-down";
  // Keyed on the dataset, not the path: a new range replays the entrance, a
  // resize (same candles, new width) does not.
  const drawKey = `${interval}-${candles.length}-${candles[0].timestamp}`;

  const pointFromClientX = (clientX) => {
    const rect = wrapRef.current.getBoundingClientRect();
    const ratio = (clientX - rect.left - PAD_X) / (rect.width - PAD_X * 2);
    return Math.max(0, Math.min(model.closes.length - 1, Math.round(ratio * (model.closes.length - 1))));
  };

  const active = cursor === null ? null : candles[cursor];
  const summary = `${candles.length} points from ${formatDateTime(candles[0].timestamp)} to ${formatDateTime(candles[candles.length - 1].timestamp)}. Range ${formatPrice(Math.min(...model.closes), currency)} to ${formatPrice(Math.max(...model.closes), currency)}.`;

  return (
    <div className="relative" ref={wrapRef}>
      <svg
        viewBox={`0 0 ${width} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        role="img"
        aria-label={`Price chart. ${summary}`}
        tabIndex={0}
        className="touch-none select-none"
        onPointerMove={(event) => setCursor(pointFromClientX(event.clientX))}
        onPointerLeave={() => setCursor(null)}
        onFocus={() => setCursor((current) => current ?? model.closes.length - 1)}
        onBlur={() => setCursor(null)}
        onKeyDown={(event) => {
          if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
          event.preventDefault();
          setCursor((current) => {
            const base = current ?? model.closes.length - 1;
            const step = event.key === "ArrowLeft" ? -1 : 1;
            return Math.max(0, Math.min(model.closes.length - 1, base + step));
          });
        }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.26" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Previous close — the reference every intraday move is measured against. */}
        {model.baselineY !== null ? (
          <>
            <line
              x1={PAD_X}
              y1={model.baselineY}
              x2={width - PAD_X}
              y2={model.baselineY}
              stroke="var(--color-fg-subtle)"
              strokeWidth="1"
              strokeDasharray="3 4"
              opacity="0.6"
            />
            <text
              x={width - PAD_X}
              y={model.baselineY - 4}
              textAnchor="end"
              className="tabular"
              fill="var(--color-fg-subtle)"
              fontSize="10"
            >
              prev {formatPrice(previousClose, currency)}
            </text>
          </>
        ) : null}

        <path
          key={`area-${drawKey}`}
          d={model.areaPath}
          fill={`url(#${gradientId})`}
          className="animate-chart-fade"
        />
        <path
          key={`line-${drawKey}`}
          d={model.linePath}
          pathLength="1"
          className="animate-draw"
          fill="none"
          stroke={stroke}
          strokeWidth="1.75"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {model.emaPaths.map((series) =>
          series.path ? (
            <path
              key={`${series.key}-${drawKey}`}
              d={series.path}
              className="animate-chart-fade"
              fill="none"
              stroke={series.color}
              strokeWidth="1.25"
              strokeDasharray={series.span === 5 ? "0" : series.span === 10 ? "5 3" : "2 3"}
              opacity="0.85"
              strokeLinejoin="round"
            />
          ) : null,
        )}

        {/* Volume histogram, tinted per bar by that bar's own direction. */}
        <g key={`volume-${drawKey}`} className="animate-bar-grow">
          {candles.map((candle, index) => {
            const height =
              ((candle.volume ?? 0) / model.maxVolume) * (VOLUME_BOTTOM - VOLUME_TOP);
            const rising = index === 0 || candle.close >= candles[index - 1].close;
            return (
              <rect
                key={candle.timestamp}
                x={model.xAt(index) - model.barWidth / 2}
                y={VOLUME_BOTTOM - height}
                width={model.barWidth}
                height={Math.max(0, height)}
                fill={rising ? "var(--color-up)" : "var(--color-down)"}
                opacity={cursor === index ? 0.85 : 0.32}
              />
            );
          })}
        </g>

        {model.ticks.map((tick) => (
          <text
            key={tick.index}
            x={Math.min(Math.max(tick.x, 20), width - 20)}
            y={AXIS_Y}
            textAnchor="middle"
            className="tabular"
            fill="var(--color-fg-subtle)"
            fontSize="10"
          >
            {intraday ? formatTime(tick.timestamp) : formatDateTime(tick.timestamp).split(",")[0]}
          </text>
        ))}

        {cursor !== null ? (
          <g pointerEvents="none">
            <line
              x1={model.xAt(cursor)}
              y1={PRICE_TOP}
              x2={model.xAt(cursor)}
              y2={VOLUME_BOTTOM}
              stroke="var(--color-line-strong)"
              strokeWidth="1"
            />
            <circle
              cx={model.xAt(cursor)}
              cy={model.yAt(model.closes[cursor])}
              r="4"
              fill={stroke}
              stroke="var(--color-surface)"
              strokeWidth="2"
            />
          </g>
        ) : null}
      </svg>

      {active ? (
        <div
          className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-control border border-line-strong bg-surface-2/95 px-2.5 py-1.5 shadow-overlay backdrop-blur"
          style={{
            left: `${Math.min(Math.max(model.xAt(cursor), 70), width - 70)}px`,
          }}
        >
          <p className="tabular text-sm font-semibold text-fg">
            {formatPrice(active.close, currency)}
          </p>
          <p className="tabular mt-0.5 text-[11px] whitespace-nowrap text-fg-muted">
            {formatDateTime(active.timestamp)}
          </p>
          {active.volume ? (
            <p className="tabular text-[11px] text-fg-subtle">
              Vol {formatCompact(active.volume)}
            </p>
          ) : null}
        </div>
      ) : null}

      {model.emaPaths.length ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
          {model.emaPaths.map((series) => (
            <span key={series.key} className="flex items-center gap-1.5 text-[11px] text-fg-muted">
              <svg width="16" height="6" aria-hidden="true">
                <line
                  x1="0"
                  y1="3"
                  x2="16"
                  y2="3"
                  stroke={series.color}
                  strokeWidth="1.5"
                  strokeDasharray={series.span === 5 ? "0" : series.span === 10 ? "5 3" : "2 3"}
                />
              </svg>
              {series.label}
            </span>
          ))}
        </div>
      ) : null}

      {showEma && !emaMeaningful ? (
        <p className="mt-2 text-[11px] text-fg-subtle">
          EMA overlays are hidden on this range — the windows are defined in trading days and this
          range uses {interval} candles.
        </p>
      ) : null}
    </div>
  );
}
