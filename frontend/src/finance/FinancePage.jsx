import { useCallback, useMemo, useState } from "react";
import { ArrowClockwise, ChartLineUp, Plus } from "@phosphor-icons/react";

import StockDrawer from "./StockDrawer.jsx";
import StockTable, { sortRows } from "./StockTable.jsx";
import Button from "../components/Button.jsx";
import Input from "../components/Input.jsx";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback.jsx";
import { useToast } from "../components/Toast.jsx";
import { addStock, getStocks, removeStock } from "../lib/api.js";
import { useAsync } from "../lib/hooks.js";
import { formatPercent } from "../lib/format.js";

export default function FinancePage({ openSymbol, onOpenSymbol }) {
  const toast = useToast();
  const { data, error, loading, reload } = useAsync(getStocks);

  const [sort, setSort] = useState({ key: "change_pct", direction: "desc" });
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);
  const [removing, setRemoving] = useState(null);

  const rows = data?.stocks ?? [];
  // A refresh keeps the table on screen (useAsync holds the previous data), so
  // rows stay mounted and can flash their price changes instead of blinking
  // back to a skeleton.
  const firstLoad = loading && !data;
  const sorted = useMemo(() => sortRows(rows, sort), [rows, sort]);

  const movers = useMemo(() => {
    const ranked = rows
      .filter((row) => typeof row.change_pct === "number")
      .sort((a, b) => b.change_pct - a.change_pct);
    if (ranked.length < 2) return null;
    return { best: ranked[0], worst: ranked[ranked.length - 1] };
  }, [rows]);

  const toggleSort = (key) =>
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : // Symbols read best A→Z; every numeric column is most useful highest-first.
          { key, direction: key === "symbol" ? "asc" : "desc" },
    );

  const submitAdd = async (event) => {
    event.preventDefault();
    const symbol = draft.trim();
    if (!symbol) return;

    setAdding(true);
    setAddError(null);
    try {
      const result = await addStock(symbol);
      toast.success(`Added ${result.symbol}`);
      setDraft("");
      reload();
    } catch (requestError) {
      setAddError(requestError.message);
    } finally {
      setAdding(false);
    }
  };

  const remove = useCallback(
    async (symbol) => {
      setRemoving(symbol);
      try {
        await removeStock(symbol);
        if (openSymbol === symbol) onOpenSymbol(null);
        reload();
        toast.success(`Removed ${symbol}`, {
          label: "Undo",
          onClick: async () => {
            try {
              await addStock(symbol);
              reload();
            } catch (undoError) {
              toast.error(undoError.message);
            }
          },
        });
      } catch (requestError) {
        toast.error(requestError.message);
      } finally {
        setRemoving(null);
      }
    },
    [openSymbol, onOpenSymbol, reload, toast],
  );

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <h1 className="text-xl font-semibold tracking-tight text-fg">Finance</h1>
          <p className="mt-0.5 text-sm text-fg-muted">
            {firstLoad ? (
              "Loading watchlist…"
            ) : movers ? (
              <>
                <span className="tabular">{rows.length}</span> symbols · best{" "}
                <span className="tabular font-medium text-up">
                  {movers.best.symbol} {formatPercent(movers.best.change_pct)}
                </span>{" "}
                · worst{" "}
                <span className="tabular font-medium text-down">
                  {movers.worst.symbol} {formatPercent(movers.worst.change_pct)}
                </span>
              </>
            ) : (
              <>
                <span className="tabular">{rows.length}</span> symbols
              </>
            )}
          </p>
        </div>

        <form onSubmit={submitAdd} className="flex items-start gap-2">
          <Input
            aria-label="Add a symbol"
            name="symbol"
            placeholder="NVDA or nvidia"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              if (addError) setAddError(null);
            }}
            error={addError}
            className="w-44 sm:w-52"
          />
          <Button type="submit" variant="primary" loading={adding} disabled={!draft.trim()}>
            {adding ? null : <Plus size={16} weight="bold" aria-hidden="true" />}
            Add
          </Button>
        </form>

        <Button variant="ghost" size="iconLg" onClick={reload} aria-label="Refresh prices">
          <ArrowClockwise size={17} aria-hidden="true" className={loading ? "animate-spin" : ""} />
        </Button>
      </div>

      {firstLoad ? (
        <TableSkeleton />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={ChartLineUp}
          title="Watchlist is empty"
          description="Add a ticker above. Common company names work too — “nvidia” resolves to NVDA."
        />
      ) : (
        <StockTable
          rows={sorted}
          sort={sort}
          onSort={toggleSort}
          onOpen={(symbol) => onOpenSymbol(symbol)}
          onRemove={remove}
          removing={removing}
        />
      )}

      <p className="mt-3 text-xs text-fg-subtle">
        EMA windows are trading days: 5, 10 and 21 sessions. Prices come from Yahoo Finance and
        are cached for 15 minutes.
      </p>

      {openSymbol ? (
        <StockDrawer
          key={openSymbol}
          symbol={openSymbol}
          onClose={() => onOpenSymbol(null)}
          onRemove={remove}
        />
      ) : null}
    </>
  );
}

function TableSkeleton() {
  return (
    <div className="overflow-hidden rounded-card border border-line bg-surface">
      <div className="border-b border-line px-3 py-2.5">
        <Skeleton className="h-3 w-full max-w-md" />
      </div>
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="flex items-center gap-4 border-b border-line px-3 py-3 last:border-0">
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-16" />
            <Skeleton className="h-2.5 w-32" />
          </div>
          <Skeleton className="h-3.5 w-16" />
          <Skeleton className="h-3.5 w-14" />
          <Skeleton className="hidden h-3.5 w-14 lg:block" />
          <Skeleton className="hidden h-3.5 w-14 lg:block" />
          <Skeleton className="h-3.5 w-14" />
        </div>
      ))}
    </div>
  );
}
