import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

/**
 * Data fetching with loading / error / refetch, guarding against out-of-order
 * responses. `loader` receives an AbortSignal; pass it straight to the api call.
 */
export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    setState((previous) => ({ ...previous, loading: true, error: null }));

    loaderRef
      .current(controller.signal)
      .then((data) => {
        if (active) setState({ data, error: null, loading: false });
      })
      .catch((error) => {
        if (!active || error.name === "AbortError") return;
        setState({ data: null, error, loading: false });
      });

    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  /** Optimistic local edit — avoids a full refetch after a small mutation. */
  const patch = useCallback(
    (updater) => setState((previous) => ({ ...previous, data: updater(previous.data) })),
    [],
  );

  return { ...state, reload, patch };
}

/**
 * Hash router: `#/anime`, `#/anime/21`, `#/finance`, `#/finance/NVDA`.
 *
 * Hash routing is deliberate — the server only ever receives "/", so no SPA
 * catch-all is needed on the FastAPI side and /api can never be shadowed.
 * Deep links still work: an open drawer or episode picker is in the URL.
 */
const TABS = ["anime", "finance"];

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [tab, param] = raw.split("/");
  return {
    tab: TABS.includes(tab) ? tab : "anime",
    param: param ? decodeURIComponent(param) : null,
  };
}

export function useRoute() {
  const [route, setRoute] = useState(parseHash);

  useEffect(() => {
    const onChange = () => setRoute(parseHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  /**
   * `pushState` instead of assigning `location.hash` so the state update is
   * synchronous — a view transition needs the new DOM inside its callback.
   * Back/forward still fire `hashchange`, which the listener above handles.
   *
   * `morphFrom`: an element whose snapshot morphs into whatever carries
   * `view-transition-name: anime-cover` on the next screen.
   */
  const navigate = useCallback((tab, param, { morphFrom } = {}) => {
    const update = () => {
      window.history.pushState(
        null,
        "",
        param ? `#/${tab}/${encodeURIComponent(param)}` : `#/${tab}`,
      );
      setRoute(parseHash());
    };

    const canMorph =
      morphFrom &&
      typeof document.startViewTransition === "function" &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!canMorph) {
      update();
      return;
    }

    morphFrom.style.viewTransitionName = "anime-cover";
    document.startViewTransition(() => {
      flushSync(update);
      // The new screen owns the name now; two holders would cancel the morph.
      morphFrom.style.viewTransitionName = "";
    });
  }, []);

  return { ...route, navigate };
}

/** Debounce a rapidly changing value (search boxes). */
export function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** Re-render on an interval — drives the live "next episode" countdowns. */
export function useTicker(intervalMs = 60_000) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((tick) => tick + 1), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
}

/** Latest value in a ref, for use inside stable callbacks. */
export function useLatest(value) {
  const ref = useRef(value);
  ref.current = value;
  return ref;
}
