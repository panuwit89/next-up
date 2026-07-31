import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "@phosphor-icons/react";

import Button from "./Button.jsx";

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

function Scrim({ onClose }) {
  return (
    <div
      className="animate-fade-in absolute inset-0 bg-black/65 backdrop-blur-[2px]"
      onClick={onClose}
      aria-hidden="true"
    />
  );
}

/** Centred dialog. Used for the episode picker and the add-anime search. */
export function Modal({ open, onClose, title, subtitle, children, footer, size = "lg" }) {
  const panelRef = useRef(null);
  useDialogBehaviour(open, panelRef, onClose);

  if (!open) return null;

  const widths = { md: "max-w-lg", lg: "max-w-2xl", xl: "max-w-4xl" };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <Scrim onClose={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        tabIndex={-1}
        className={[
          "animate-rise-in relative flex max-h-[92dvh] w-full flex-col",
          "rounded-t-card sm:rounded-card border border-line bg-surface shadow-overlay",
          widths[size],
        ].join(" ")}
      >
        <header className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-base font-semibold text-fg">{title}</h2>
            {subtitle ? <p className="mt-0.5 text-sm text-fg-muted">{subtitle}</p> : null}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close dialog">
            <X size={18} weight="bold" aria-hidden="true" />
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          {children}
        </div>

        {footer ? (
          <footer className="border-t border-line px-5 py-3.5">{footer}</footer>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}

/** Right-hand panel. Used for stock detail — full width on phones. */
export function Drawer({ open, onClose, label, children }) {
  const panelRef = useRef(null);
  useDialogBehaviour(open, panelRef, onClose);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <Scrim onClose={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className={[
          "animate-slide-in-right relative flex h-full w-full flex-col",
          "border-l border-line bg-surface shadow-overlay",
          "sm:max-w-xl lg:max-w-2xl",
        ].join(" ")}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
