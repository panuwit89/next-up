import { ArrowClockwise, WarningCircle } from "@phosphor-icons/react";

import Button from "./Button.jsx";

/** Shimmering placeholder. Always sized to the real content to avoid layout shift. */
export function Skeleton({ className = "" }) {
  return <div className={`skeleton rounded-control ${className}`} aria-hidden="true" />;
}

/** Nothing to show yet — never a blank region. */
export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-line px-6 py-14 text-center">
      {Icon ? (
        <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-fg-subtle">
          <Icon size={24} aria-hidden="true" />
        </span>
      ) : null}
      <p className="text-sm font-semibold text-fg">{title}</p>
      {description ? (
        <p className="mt-1 max-w-sm text-sm text-fg-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/** Failure state — states the cause and always offers the recovery path. */
export function ErrorState({ error, onRetry, compact = false }) {
  const message = error?.message ?? "Something went wrong.";

  if (compact) {
    return (
      <div
        role="alert"
        className="flex items-center gap-2 rounded-control border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
      >
        <WarningCircle size={16} weight="fill" aria-hidden="true" />
        <span className="min-w-0 flex-1">{message}</span>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="shrink-0 cursor-pointer font-medium underline underline-offset-2 hover:no-underline"
          >
            Retry
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center rounded-card border border-danger/30 bg-danger/5 px-6 py-14 text-center"
    >
      <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-danger/15 text-danger">
        <WarningCircle size={24} weight="fill" aria-hidden="true" />
      </span>
      <p className="text-sm font-semibold text-fg">Could not load this</p>
      <p className="mt-1 max-w-sm text-sm text-fg-muted">{message}</p>
      {onRetry ? (
        <Button variant="secondary" className="mt-4" onClick={onRetry}>
          <ArrowClockwise size={16} weight="bold" aria-hidden="true" />
          Try again
        </Button>
      ) : null}
    </div>
  );
}

/** Small pill for statuses and counts. */
export function Badge({ tone = "neutral", children, className = "" }) {
  const tones = {
    neutral: "bg-surface-2 text-fg-muted border-line",
    accent: "bg-primary/15 text-primary-fg border-primary/25",
    up: "bg-up/15 text-up border-up/25",
    down: "bg-down/15 text-down border-down/25",
    warn: "bg-warn/15 text-warn border-warn/25",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
