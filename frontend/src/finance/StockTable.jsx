import { CaretDown, CaretUp, Trash, WarningCircle } from "@phosphor-icons/react";

import { formatNumber, formatPercent, formatPrice } from "../lib/format.js";

const COLUMNS = [
  { key: "symbol", label: "Symbol", align: "left", sortable: true },
  { key: "price", label: "Price", align: "right", sortable: true },
  { key: "change_pct", label: "Change", align: "right", sortable: true },
  { key: "week_1", label: "EMA 5", align: "right", sortable: true, dense: true },
  { key: "week_2", label: "EMA 10", align: "right", sortable: true, dense: true },
  { key: "month_1", label: "EMA 21", align: "right", sortable: true },
];

const sortValue = (row, key) => {
  if (key === "symbol") return row.symbol;
  if (key in (row.ema ?? {})) return row.ema[key];
  return row[key];
};

export function sortRows(rows, { key, direction }) {
  const factor = direction === "asc" ? 1 : -1;
  return [...rows].sort((left, right) => {
    const a = sortValue(left, key);
    const b = sortValue(right, key);
    if (a === b) return 0;
    if (a === null || a === undefined) return 1;
    if (b === null || b === undefined) return -1;
    return (typeof a === "string" ? a.localeCompare(b) : a - b) * factor;
  });
}

/**
 * Watchlist table. Each row's symbol is a real button so the drawer is
 * reachable by keyboard; clicking anywhere else on the row does the same thing
 * as a mouse affordance.
 */
export default function StockTable({ rows, sort, onSort, onOpen, onRemove, removing }) {
  return (
    <div className="overflow-x-auto rounded-card border border-line bg-surface">
      <table className="w-full min-w-[520px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-line">
            {COLUMNS.map((column) => {
              const active = sort.key === column.key;
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
                  className={[
                    "px-3 py-2.5 text-xs font-medium tracking-wide text-fg-subtle uppercase",
                    column.align === "right" ? "text-right" : "text-left",
                    column.dense ? "hidden lg:table-cell" : "",
                  ].join(" ")}
                >
                  <button
                    type="button"
                    onClick={() => onSort(column.key)}
                    className={[
                      "inline-flex cursor-pointer items-center gap-1 transition-colors hover:text-fg",
                      active ? "text-fg" : "",
                      column.align === "right" ? "flex-row-reverse" : "",
                    ].join(" ")}
                  >
                    {column.label}
                    {active ? (
                      sort.direction === "asc" ? (
                        <CaretUp size={10} weight="bold" aria-hidden="true" />
                      ) : (
                        <CaretDown size={10} weight="bold" aria-hidden="true" />
                      )
                    ) : null}
                  </button>
                </th>
              );
            })}
            <th scope="col" className="w-12 px-3 py-2.5">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>

        <tbody className="stagger">
          {rows.map((row, index) => (
            <Row
              key={row.symbol}
              row={row}
              index={Math.min(index, 12)}
              onOpen={() => onOpen(row.symbol)}
              onRemove={() => onRemove(row.symbol)}
              removing={removing === row.symbol}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({ row, index, onOpen, onRemove, removing }) {
  const { symbol, company_name: name, price, change_pct: changePct, ema, error } = row;
  const positive = (changePct ?? 0) >= 0;
  const DirectionIcon = positive ? CaretUp : CaretDown;

  if (error) {
    return (
      <tr style={{ "--i": index }} className="border-b border-line last:border-0">
        <td className="px-3 py-2.5">
          <span className="tabular font-semibold text-fg">{symbol}</span>
          <span className="block truncate text-xs text-fg-subtle">{name}</span>
        </td>
        <td colSpan={5} className="px-3 py-2.5">
          <span className="flex items-center gap-1.5 text-xs text-warn">
            <WarningCircle size={14} weight="fill" aria-hidden="true" />
            {error}
          </span>
        </td>
        <td className="px-3 py-2.5 text-right">
          <RemoveButton symbol={symbol} onRemove={onRemove} removing={removing} />
        </td>
      </tr>
    );
  }

  // Price above its 21-day EMA is the trend signal; icon + colour, never colour alone.
  const aboveTrend = price !== null && ema?.month_1 ? price >= ema.month_1 : null;

  return (
    <tr
      style={{ "--i": index }}
      onClick={onOpen}
      className="cursor-pointer border-b border-line transition-colors last:border-0 hover:bg-surface-2"
    >
      <td className="px-3 py-2.5">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onOpen();
          }}
          className="cursor-pointer text-left"
        >
          <span className="tabular font-semibold text-fg">{symbol}</span>
        </button>
        <span className="block max-w-[22ch] truncate text-xs text-fg-subtle" title={name}>
          {name}
        </span>
      </td>

      <td className="tabular px-3 py-2.5 text-right font-medium text-fg">
        {formatPrice(price)}
      </td>

      <td
        className={`tabular px-3 py-2.5 text-right font-medium ${
          changePct === null || changePct === undefined
            ? "text-fg-subtle"
            : positive
              ? "text-up"
              : "text-down"
        }`}
      >
        <span className="inline-flex items-center gap-0.5">
          {changePct === null || changePct === undefined ? null : (
            <DirectionIcon size={11} weight="fill" aria-hidden="true" />
          )}
          {formatPercent(changePct)}
        </span>
      </td>

      <td className="tabular hidden px-3 py-2.5 text-right text-fg-muted lg:table-cell">
        {formatNumber(ema?.week_1)}
      </td>
      <td className="tabular hidden px-3 py-2.5 text-right text-fg-muted lg:table-cell">
        {formatNumber(ema?.week_2)}
      </td>
      <td className="tabular px-3 py-2.5 text-right text-fg-muted">
        <span className="inline-flex items-center gap-1">
          {aboveTrend === null ? null : aboveTrend ? (
            <CaretUp
              size={10}
              weight="bold"
              aria-label="price above 21-day EMA"
              className="text-up"
            />
          ) : (
            <CaretDown
              size={10}
              weight="bold"
              aria-label="price below 21-day EMA"
              className="text-down"
            />
          )}
          {formatNumber(ema?.month_1)}
        </span>
      </td>

      <td className="px-3 py-2.5 text-right">
        <RemoveButton symbol={symbol} onRemove={onRemove} removing={removing} />
      </td>
    </tr>
  );
}

function RemoveButton({ symbol, onRemove, removing }) {
  return (
    <button
      type="button"
      disabled={removing}
      aria-label={`Remove ${symbol} from watchlist`}
      onClick={(event) => {
        event.stopPropagation();
        onRemove();
      }}
      className="touch-target inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-control text-fg-subtle transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-40"
    >
      <Trash size={15} aria-hidden="true" />
    </button>
  );
}
