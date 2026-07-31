import { CircleNotch } from "@phosphor-icons/react";

/**
 * The only button in the app. Both tabs use it, so a "Refresh" in Finance and
 * an "Add anime" in Anime are pixel-identical.
 */

const VARIANTS = {
  primary:
    "bg-primary text-white hover:bg-primary-hover shadow-raise disabled:hover:bg-primary",
  secondary:
    "bg-surface-2 text-fg border border-line hover:bg-surface-3 hover:border-line-strong disabled:hover:bg-surface-2",
  ghost:
    "text-fg-muted hover:text-fg hover:bg-surface-2 disabled:hover:bg-transparent disabled:hover:text-fg-muted",
  danger:
    "bg-transparent text-danger border border-danger/40 hover:bg-danger/10 hover:border-danger disabled:hover:bg-transparent",
};

const SIZES = {
  sm: "h-9 px-3 text-sm gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  icon: "h-9 w-9 justify-center",
  iconLg: "h-10 w-10 justify-center",
};

export default function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  disabled = false,
  className = "",
  children,
  ...props
}) {
  const isDisabled = disabled || loading;

  return (
    <button
      type="button"
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={[
        "touch-target inline-flex cursor-pointer items-center rounded-control font-medium",
        "transition-colors duration-150 select-none",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      ].join(" ")}
      {...props}
    >
      {loading ? (
        <CircleNotch size={16} weight="bold" className="animate-spin" aria-hidden="true" />
      ) : null}
      {children}
    </button>
  );
}
