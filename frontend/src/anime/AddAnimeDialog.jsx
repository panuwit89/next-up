import { useEffect, useState } from "react";
import { Check, MagnifyingGlass, Plus, Star } from "@phosphor-icons/react";

import Button from "../components/Button.jsx";
import Input from "../components/Input.jsx";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback.jsx";
import { Modal } from "../components/Overlay.jsx";
import { useToast } from "../components/Toast.jsx";
import { searchAnime, subscribeAnime } from "../lib/api.js";
import { useDebounced } from "../lib/hooks.js";

/** AniList search → subscribe. Accepts a title or a raw AniList id. */
export default function AddAnimeDialog({ trackedIds, onClose, onAdded }) {
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [state, setState] = useState({ results: [], loading: false, error: null });
  const [adding, setAdding] = useState(null);

  const debouncedQuery = useDebounced(query.trim(), 350);

  useEffect(() => {
    if (!debouncedQuery) {
      setState({ results: [], loading: false, error: null });
      return undefined;
    }

    const controller = new AbortController();
    let active = true;
    setState((previous) => ({ ...previous, loading: true, error: null }));

    searchAnime(debouncedQuery, controller.signal)
      .then((payload) => {
        if (active) setState({ results: payload.results ?? [], loading: false, error: null });
      })
      .catch((error) => {
        if (!active || error.name === "AbortError") return;
        setState({ results: [], loading: false, error });
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [debouncedQuery]);

  const add = async (result) => {
    setAdding(result.anime_id);
    try {
      await subscribeAnime(result.anime_id, result.title);
      toast.success(`Tracking ${result.title}`);
      onAdded();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setAdding(null);
    }
  };

  return (
    <Modal open onClose={onClose} size="lg" title="Add anime" subtitle="Search AniList by title, or paste an AniList id">
      <Input
        label="Search"
        icon={MagnifyingGlass}
        placeholder="Frieren, Dandadan, 21…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        autoFocus
      />

      <div className="mt-4">
        {state.loading ? (
          <ul className="space-y-2">
            {Array.from({ length: 4 }, (_, index) => (
              <li key={index} className="flex gap-3">
                <Skeleton className="h-[72px] w-12 shrink-0" />
                <div className="flex-1 space-y-2 py-1">
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
              </li>
            ))}
          </ul>
        ) : state.error ? (
          <ErrorState error={state.error} compact />
        ) : !debouncedQuery ? (
          <EmptyState
            icon={MagnifyingGlass}
            title="Start typing to search"
            description="Results come straight from AniList. Numeric input is treated as an AniList id."
          />
        ) : state.results.length === 0 ? (
          <EmptyState
            icon={MagnifyingGlass}
            title={`Nothing found for “${debouncedQuery}”`}
            description="Try the romaji title, or paste the numeric AniList id from the URL."
          />
        ) : (
          <ul className="stagger space-y-1">
            {state.results.map((result, index) => {
              const tracked = trackedIds.has(result.anime_id);
              return (
                <li
                  key={result.anime_id}
                  style={{ "--i": index }}
                  className="flex items-center gap-3 rounded-control p-2 transition-colors hover:bg-surface-2"
                >
                  {result.cover_image ? (
                    <img
                      src={result.cover_image}
                      alt=""
                      width={48}
                      height={72}
                      loading="lazy"
                      className="h-[72px] w-12 shrink-0 rounded border border-line object-cover"
                    />
                  ) : (
                    <div className="h-[72px] w-12 shrink-0 rounded border border-line bg-surface-2" />
                  )}

                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-fg">{result.title}</p>
                    {result.title_english && result.title_english !== result.title ? (
                      <p className="truncate text-xs text-fg-subtle">{result.title_english}</p>
                    ) : null}
                    <div className="mt-1 flex items-center gap-2 text-xs text-fg-muted">
                      {result.year ? <span className="tabular">{result.year}</span> : null}
                      {result.episodes ? (
                        <span className="tabular">{result.episodes} eps</span>
                      ) : null}
                      {result.score ? (
                        <span className="flex items-center gap-0.5">
                          <Star size={11} weight="fill" aria-hidden="true" className="text-warn" />
                          <span className="tabular">{result.score}</span>
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {tracked ? (
                    <span className="flex shrink-0 items-center gap-1 px-2 text-xs font-medium text-up">
                      <Check size={14} weight="bold" aria-hidden="true" />
                      Tracking
                    </span>
                  ) : (
                    <Button
                      size="sm"
                      variant="primary"
                      className="shrink-0"
                      loading={adding === result.anime_id}
                      disabled={adding !== null}
                      onClick={() => add(result)}
                    >
                      {adding === result.anime_id ? null : (
                        <Plus size={15} weight="bold" aria-hidden="true" />
                      )}
                      Add
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Modal>
  );
}
