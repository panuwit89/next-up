import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowClockwise,
  CaretRight,
  CheckSquare,
  MagnifyingGlass,
  MonitorPlay,
  Plus,
  Trash,
  X,
} from "@phosphor-icons/react";

import AddAnimeDialog from "./AddAnimeDialog.jsx";
import AnimeCard from "./AnimeCard.jsx";
import EpisodePicker from "./EpisodePicker.jsx";
import Button from "../components/Button.jsx";
import Input from "../components/Input.jsx";
import { Badge, EmptyState, ErrorState, Skeleton } from "../components/Feedback.jsx";
import { useToast } from "../components/Toast.jsx";
import { getAnime, unsubscribeAnime } from "../lib/api.js";
import { useAsync, useTicker } from "../lib/hooks.js";

const SECTIONS = [
  { key: "on_air", label: "On Air", hint: "airing now", defaultOpen: true },
  {
    key: "finished_watching",
    label: "Catching Up",
    hint: "finished airing · still watching",
    defaultOpen: true,
  },
  { key: "finished_done", label: "Completed", hint: "watched every episode", defaultOpen: false },
];

const STORAGE_KEY = "dashboard.anime.sections";

/** Re-derive the group an item belongs to, mirroring `web/anime_service.py`. */
function groupFor(item) {
  if (item.next_episode) return "on_air";
  if (item.total_episodes && item.watched_episode >= item.total_episodes) return "finished_done";
  return "finished_watching";
}

/** Apply a local edit and move the card between groups if the rule now differs. */
function regroup(data, animeId, changes) {
  if (!data?.groups) return data;

  const groups = { ...data.groups };
  let moved = null;

  for (const key of Object.keys(groups)) {
    const index = groups[key].findIndex((item) => item.anime_id === animeId);
    if (index === -1) continue;
    moved = { ...groups[key][index], ...changes };
    groups[key] = groups[key].filter((item) => item.anime_id !== animeId);
    break;
  }
  if (!moved) return data;

  const target = groupFor(moved);
  groups[target] = [...groups[target], moved].sort(
    (a, b) => (b.latest_episode_at ?? 0) - (a.latest_episode_at ?? 0),
  );
  return { ...data, groups };
}

export default function AnimePage({ openAnimeId, onOpenAnime }) {
  const toast = useToast();
  const { data, error, loading, reload, patch } = useAsync(getAnime);

  const [filter, setFilter] = useState("");
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [addOpen, setAddOpen] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [open, setOpen] = useState(() => {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    return stored ?? Object.fromEntries(SECTIONS.map((s) => [s.key, s.defaultOpen]));
  });

  // Keeps the "next episode in 4h 12m" pills honest.
  useTicker(60_000);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(open));
  }, [open]);

  const allItems = useMemo(
    () => (data?.groups ? Object.values(data.groups).flat() : []),
    [data],
  );
  const trackedIds = useMemo(
    () => new Set(allItems.map((item) => item.anime_id)),
    [allItems],
  );

  const needle = filter.trim().toLowerCase();
  const sections = useMemo(
    () =>
      SECTIONS.map((section) => ({
        ...section,
        items: (data?.groups?.[section.key] ?? []).filter(
          (item) =>
            !needle ||
            item.title.toLowerCase().includes(needle) ||
            item.title_english?.toLowerCase().includes(needle),
        ),
      })),
    [data, needle],
  );

  const openItem = openAnimeId
    ? allItems.find((item) => item.anime_id === openAnimeId) ?? null
    : null;

  const closePicker = useCallback(() => onOpenAnime(null), [onOpenAnime]);

  const handleProgress = useCallback(
    (animeId, watched) => patch((current) => regroup(current, animeId, { watched_episode: watched })),
    [patch],
  );

  const handlePlatform = useCallback(
    (animeId, platform) => patch((current) => regroup(current, animeId, { platform })),
    [patch],
  );

  const handleOffset = useCallback(
    (animeId, offsetMinutes) =>
      patch((current) => regroup(current, animeId, { offset_minutes: offsetMinutes })),
    [patch],
  );

  const remove = async (animeIds, label) => {
    setRemoving(true);
    try {
      await unsubscribeAnime(animeIds);
      toast.success(label);
      setSelected(new Set());
      setSelectMode(false);
      closePicker();
      reload();
    } catch (requestError) {
      toast.error(requestError.message);
    } finally {
      setRemoving(false);
    }
  };

  const toggleSelected = (animeId) =>
    setSelected((current) => {
      const next = new Set(current);
      next.has(animeId) ? next.delete(animeId) : next.add(animeId);
      return next;
    });

  const behindCount = allItems.reduce((total, item) => {
    const available = item.total_episodes ?? item.latest_episode ?? 0;
    return total + Math.max(0, available - item.watched_episode);
  }, 0);

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="text-xl font-semibold tracking-tight text-fg">Anime</h1>
          <p className="mt-0.5 text-sm text-fg-muted">
            {loading ? (
              "Loading your watchlist…"
            ) : (
              <>
                <span className="tabular">{allItems.length}</span> tracked
                {behindCount > 0 ? (
                  <>
                    {" · "}
                    <span className="tabular text-primary-fg">{behindCount}</span> episodes behind
                  </>
                ) : null}
              </>
            )}
          </p>
        </div>

        {/* <Input
          aria-label="Filter tracked anime"
          icon={MagnifyingGlass}
          placeholder="Filter…"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          className="w-full sm:w-56"
        /> */}

        <Button
          variant={selectMode ? "primary" : "secondary"}
          onClick={() => {
            setSelectMode((mode) => !mode);
            setSelected(new Set());
          }}
          aria-pressed={selectMode}
        >
          {selectMode ? <X size={16} aria-hidden="true" /> : <CheckSquare size={16} aria-hidden="true" />}
          {selectMode ? "Cancel" : "Select"}
        </Button>

        {/* <Button variant="ghost" size="iconLg" onClick={reload} aria-label="Refresh watchlist">
          <ArrowClockwise size={17} aria-hidden="true" className={loading ? "animate-spin" : ""} />
        </Button> */}

        <Button variant="primary" onClick={() => setAddOpen(true)}>
          <Plus size={16} weight="bold" aria-hidden="true" />
          Add anime
        </Button>
      </div>

      {selectMode ? (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-card border border-line bg-surface px-4 py-3">
          <span className="text-sm text-fg-muted">
            <span className="tabular font-medium text-fg">{selected.size}</span> selected
          </span>
          <Button
            variant="danger"
            size="sm"
            className="ml-auto"
            disabled={selected.size === 0}
            loading={removing}
            onClick={() =>
              remove([...selected], `Removed ${selected.size} ${selected.size === 1 ? "title" : "titles"}`)
            }
          >
            <Trash size={15} aria-hidden="true" />
            Remove selected
          </Button>
        </div>
      ) : null}

      {loading ? (
        <LoadingGrid />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : allItems.length === 0 ? (
        <EmptyState
          icon={MonitorPlay}
          title="No anime tracked yet"
          description="Subscriptions are shared with the Discord bot — anything you add here gets notified there too."
          action={
            <Button variant="primary" onClick={() => setAddOpen(true)}>
              <Plus size={16} weight="bold" aria-hidden="true" />
              Add your first anime
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          {sections.map((section) => (
            <Section
              key={section.key}
              section={section}
              open={open[section.key]}
              onToggle={() =>
                setOpen((current) => ({ ...current, [section.key]: !current[section.key] }))
              }
              selectMode={selectMode}
              selected={selected}
              onActivate={(item) =>
                selectMode ? toggleSelected(item.anime_id) : onOpenAnime(item.anime_id)
              }
            />
          ))}

          {needle && sections.every((section) => section.items.length === 0) ? (
            <EmptyState
              icon={MagnifyingGlass}
              title={`No tracked anime matches “${filter}”`}
              action={
                <Button variant="secondary" onClick={() => setFilter("")}>
                  Clear filter
                </Button>
              }
            />
          ) : null}
        </div>
      )}

      {openItem ? (
        <EpisodePicker
          key={openItem.anime_id}
          item={openItem}
          onClose={closePicker}
          onProgress={handleProgress}
          onPlatform={handlePlatform}
          onOffset={handleOffset}
          onRemove={(item) => remove([item.anime_id], `Removed ${item.title}`)}
        />
      ) : null}

      {addOpen ? (
        <AddAnimeDialog
          trackedIds={trackedIds}
          onClose={() => setAddOpen(false)}
          onAdded={reload}
        />
      ) : null}
    </>
  );
}

function Section({ section, open, onToggle, selectMode, selected, onActivate }) {
  const { label, hint, items } = section;
  if (items.length === 0) return null;

  return (
    <section>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="group mb-3 flex w-full cursor-pointer items-center gap-2 text-left"
      >
        <CaretRight
          size={16}
          weight="bold"
          aria-hidden="true"
          className={`text-fg-subtle transition-transform duration-200 ${open ? "rotate-90" : ""}`}
        />
        <h2 className="text-sm font-semibold tracking-wide text-fg uppercase">{label}</h2>
        <Badge>{items.length}</Badge>
        <span className="hidden text-xs text-fg-subtle sm:inline">{hint}</span>
        <span aria-hidden="true" className="ml-2 h-px flex-1 bg-line" />
      </button>

      {open ? (
        <div className="stagger grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
          {items.map((item, index) => (
            <AnimeCard
              key={item.anime_id}
              item={item}
              index={Math.min(index, 12)}
              selectMode={selectMode}
              selected={selected.has(item.anime_id)}
              onActivate={() => onActivate(item)}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function LoadingGrid() {
  return (
    <div className="space-y-6">
      {[10, 5].map((count, section) => (
        <div key={section}>
          <Skeleton className="mb-3 h-4 w-40" />
          <div className="grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {Array.from({ length: count }, (_, index) => (
              <div key={index}>
                <Skeleton className="aspect-[2/3] w-full" />
                <Skeleton className="mt-2 h-3.5 w-4/5" />
                <Skeleton className="mt-1.5 h-2.5 w-1/3" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
