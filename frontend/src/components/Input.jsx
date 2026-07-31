import { forwardRef } from "react";

/**
 * Text input with a always-visible label (never placeholder-as-label) and an
 * optional leading icon. Helper text sits below and stays put, so showing an
 * error message cannot shift the layout.
 */
const Input = forwardRef(function Input(
  { label, hint, error, icon: Icon, className = "", id, ...props },
  ref,
) {
  const inputId = id ?? `field-${props.name ?? label?.toLowerCase().replace(/\s+/g, "-")}`;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;

  return (
    <div className={className}>
      {label ? (
        <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium text-fg-muted">
          {label}
        </label>
      ) : null}

      <div className="relative">
        {Icon ? (
          <Icon
            size={17}
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-fg-subtle"
          />
        ) : null}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={[
            "h-10 w-full rounded-control border bg-surface-2 text-sm text-fg",
            "placeholder:text-fg-subtle",
            "transition-colors duration-150 outline-none",
            "focus:border-ring focus:ring-2 focus:ring-ring/30",
            Icon ? "pr-3 pl-9" : "px-3",
            error ? "border-danger" : "border-line",
          ].join(" ")}
          {...props}
        />
      </div>

      {error ? (
        <p id={`${inputId}-error`} role="alert" className="mt-1.5 text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="mt-1.5 text-xs text-fg-subtle">
          {hint}
        </p>
      ) : null}
    </div>
  );
});

export default Input;
