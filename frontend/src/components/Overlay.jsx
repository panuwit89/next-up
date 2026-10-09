import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "@phosphor-icons/react";

import Button from "./Button.jsx";

/**
 * Close request for anything rendered inside a Modal or Drawer. Calling the
 * parent's `onClose` directly would unmount the panel mid-frame; this plays the
 * exit animation first.
 */
const OverlayCloseContext = createContext(null);

export const useOverlayClose = () => useContext(OverlayCloseContext);

// Longest exit animation plus slack, in case `animationend` never arrives.
const EXIT_FALLBACK_MS = 260;

/**
 * Every caller mounts its dialog conditionally, so the panel cannot linger
 * after `onClose`. Instead a close is *requested*: the exit animation plays,
 * and `onClose` runs once it ends.
 */
function useClosing(onClose) {
  const [closing, setClosing] = useState(false);
  const doneRef = useRef(false);
  const timerRef = useRef(null); // non-null once a close has been requested
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const finish = useCallback(() => {
    if (doneRef.current) return;
    doneRef.current = true;
    window.clearTimeout(timerRef.current);
    onCloseRef.current();
  }, []);

  const requestClose = useCallback(() => {
    if (timerRef.current !== null) return;
    timerRef.current = window.setTimeout(finish, EXIT_FALLBACK_MS);
    setClosing(true);
  }, [finish]);

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  const onAnimationEnd = (event) => {
    if (closing && event.target === event.currentTarget) finish();
  };

  return { closing, requestClose, onAnimationEnd };
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Shared dialog behaviour for the episode picker (Modal) and the stock detail
 * panel (Drawer): scrim, Escape to close, focus trap, focus restore and a
 * scroll lock that compensates the scrollbar so the page never shifts.
 */
function useDialogBehaviour(open, panelRef, onClose) {
  useEffect(() => {
    if (!open) return undefined;

    const previouslyFocused = document.activeElement;
    const { body } = document;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    const previousOverflow = body.style.overflow;
    const previousPadding = body.style.paddingRight;

    body.style.overflow = "hidden";
    if (scrollbarWidth > 0) body.style.paddingRight = `${scrollbarWidth}px`;

    // Move focus into the panel so screen readers and keyboards land inside it.
    const focusTimer = window.setTimeout(() => {
      const panel = panelRef.current;
      if (!panel) return;
      const first = panel.querySelector(FOCUSABLE);
      (first ?? panel).focus({ preventScroll: true });
    }, 0);

    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;
      const focusable = [...panel.querySelectorAll(FOCUSABLE)].filter(
        (node) => node.offsetParent !== null,
      );
      if (!focusable.length) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);

    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown, true);
      body.style.overflow = previousOverflow;
      body.style.paddingRight = previousPadding;
      previouslyFocused?.focus?.({ preventScroll: true });
    };
  }, [open, panelRef, onClose]);
}

function Scrim({ onClose, closing }) {
  return (
    <div
      className={`${closing ? "animate-fade-out" : "animate-fade-in"} absolute inset-0 bg-black/65 backdrop-blur-[2px]`}
      onClick={onClose}
      aria-hidden="true"
    />
  );
}

/** Centred dialog. Used for the episode picker and the add-anime search. */
export function Modal({ open, onClose, title, subtitle, children, footer, size = "lg" }) {
  const panelRef = useRef(null);
  const { closing, requestClose, onAnimationEnd } = useClosing(onClose);
  useDialogBehaviour(open, panelRef, requestClose);

  if (!open) return null;

  const widths = { md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <Scrim onClose={requestClose} closing={closing} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        tabIndex={-1}
        onAnimationEnd={onAnimationEnd}
        className={[
          "relative flex max-h-[92dvh] w-full flex-col",
          closing ? "animate-sink-out pointer-events-none" : "animate-rise-in",
          "rounded-t-card sm:rounded-card border border-line bg-surface shadow-overlay",
          widths[size],
        ].join(" ")}
      >
        <header className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-base font-semibold text-fg">{title}</h2>
            {subtitle ? <p className="mt-0.5 text-sm text-fg-muted">{subtitle}</p> : null}
          </div>
          <Button variant="ghost" size="icon" onClick={requestClose} aria-label="Close dialog">
            <X size={18} weight="bold" aria-hidden="true" />
          </Button>
        </header>

        <OverlayCloseContext.Provider value={requestClose}>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
            {children}
          </div>

          {footer ? (
            <footer className="border-t border-line px-5 py-3.5">{footer}</footer>
          ) : null}
        </OverlayCloseContext.Provider>
      </div>
    </div>,
    document.body,
  );
}

/** Right-hand panel. Used for stock detail — full width on phones. */
export function Drawer({ open, onClose, label, children }) {
  const panelRef = useRef(null);
  const { closing, requestClose, onAnimationEnd } = useClosing(onClose);
  useDialogBehaviour(open, panelRef, requestClose);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <Scrim onClose={requestClose} closing={closing} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        onAnimationEnd={onAnimationEnd}
        className={[
          "relative flex h-full w-full flex-col",
          closing ? "animate-slide-out-right pointer-events-none" : "animate-slide-in-right",
          "border-l border-line bg-surface shadow-overlay",
          "sm:max-w-xl lg:max-w-2xl",
        ].join(" ")}
      >
        <OverlayCloseContext.Provider value={requestClose}>{children}</OverlayCloseContext.Provider>
      </div>
    </div>,
    document.body,
  );
}
