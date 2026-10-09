import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { CheckCircle, WarningCircle } from "@phosphor-icons/react";

/**
 * Toasts confirm background writes (progress auto-save, add/remove) without
 * interrupting. They live in an aria-live region so they are announced but
 * never steal focus.
 */

const ToastContext = createContext(() => {});

export const useToast = () => useContext(ToastContext);

const DURATIONS = { success: 2600, error: 5000 };
const LEAVE_MS = 160; // a little over the 140ms sink-out

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(0);

  // Mark first so the exit animation can play, then drop it from the list.
  const dismiss = useCallback((id) => {
    setToasts((current) =>
      current.map((toast) => (toast.id === id ? { ...toast, leaving: true } : toast)),
    );
    window.setTimeout(
      () => setToasts((current) => current.filter((toast) => toast.id !== id)),
      LEAVE_MS,
    );
  }, []);

  const notify = useCallback(
    (message, tone = "success", action = null) => {
      const id = nextId.current++;
      setToasts((current) => [...current.slice(-2), { id, message, tone, action }]);
      // An offered undo needs longer than a plain confirmation to be usable.
      const duration = action ? 7000 : (DURATIONS[tone] ?? DURATIONS.success);
      window.setTimeout(() => dismiss(id), duration);
    },
    [dismiss],
  );

  const api = useMemo(
    () => ({
      success: (message, action) => notify(message, "success", action),
      error: (message) => notify(message, "error"),
    }),
    [notify],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 px-4 pb-4"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={[
              toast.leaving ? "animate-sink-out pointer-events-none" : "animate-rise-in pointer-events-auto",
              "flex max-w-md items-center gap-2.5",
              "rounded-control border px-3.5 py-2.5 text-sm shadow-overlay backdrop-blur",
              toast.tone === "error"
                ? "border-danger/40 bg-[#2a1518]/95 text-danger"
                : "border-line-strong bg-surface-2/95 text-fg",
            ].join(" ")}
          >
            {toast.tone === "error" ? (
              <WarningCircle size={16} weight="fill" aria-hidden="true" className="shrink-0" />
            ) : (
              <CheckCircle
                size={16}
                weight="fill"
                aria-hidden="true"
                className="shrink-0 text-up"
              />
            )}
            <span>{toast.message}</span>
            {toast.action ? (
              <button
                type="button"
                onClick={() => {
                  dismiss(toast.id);
                  toast.action.onClick();
                }}
                className="ml-1 shrink-0 cursor-pointer rounded px-1.5 py-0.5 text-sm font-semibold text-primary-fg transition-colors hover:bg-primary/15"
              >
                {toast.action.label}
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
