import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowSquareOut,
  Check,
  CloudCheck,
  CloudSlash,
  SpinnerGap,
  Trash,
} from "@phosphor-icons/react";

import Button from "../components/Button.jsx";
import Input from "../components/Input.jsx";
import { Badge } from "../components/Feedback.jsx";
import { Modal } from "../components/Overlay.jsx";
import { useToast } from "../components/Toast.jsx";
import { getPlatforms, setAiringOffset, setPlatform, setWatchedEpisode } from "../lib/api.js";
import { formatCountdown, formatRelative } from "../lib/format.js";

const PER_PAGE = 25;
const SAVE_DEBOUNCE_MS = 400;
const OFFSET_PRESETS = [0, 30, 60, 120];

/** Airing time as actually shown, i.e. AniList's schedule plus the local delay. */
export function adjustedAiringAt(next, offsetMinutes) {
  if (!next) return null;
  return next.airing_at + (offsetMinutes || 0) * 60;
}

/**
 * Episode picker.
 *
 * The API stores progress as a single high-water mark (`watched_episode`), the
 * same model AniList and MAL use — so tapping episode N means "watched through
 * N", and tapping the current mark again steps back to N-1. Writes are
 * debounced and auto-saved; a pending write is flushed on close.
 */
export default function EpisodePicker({
  item,
  onClose,
  onProgress,
  onPlatform,
  onOffset,
  onRemove,
}) {
  const toast = useToast();
  const available = item.total_episodes ?? item.latest_episode ?? 0;
  const aired = item.latest_episode ?? available;

  const [draft, setDraft] = useState(item.watched_episode);
  const [status, setStatus] = useState("idle");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [manual, setManual] = useState(String(item.watched_episode));

  const pageCount = Math.max(1, Math.ceil(available / PER_PAGE));
  const [page, setPage] = useState(() =>
    Math.min(pageCount - 1, Math.floor(Math.max(0, item.watched_episode - 1) / PER_PAGE)),
  );

  // Refs so neither the unmount flush nor a tap handler can read a stale value:
  // taps arriving in the same frame as an earlier one would otherwise still see
  // the previous render's `draft` and mis-resolve the step-back.
  const timerRef = useRef(null);
  const pendingRef = useRef(null);
  const savedRef = useRef(item.watched_episode);
  const draftRef = useRef(item.watched_episode);

  const flush = useRef(async (value) => {
    try {
      await setWatchedEpisode(item.anime_id, value);
      savedRef.current = value;
      pendingRef.current = null;
      onProgress(item.anime_id, value);
      return true;
    } catch (error) {
      return error;
    }
  });

  const commit = (value) => {
    const next = Math.max(0, Math.min(available || value, value));
    setDraft(next);
    setManual(String(next));
    draftRef.current = next;
    pendingRef.current = next;
    setStatus("saving");

    window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(async () => {
      const result = await flush.current(next);
      if (result === true) {
        setStatus("saved");
      } else {
        setStatus("error");
        setDraft(savedRef.current);
        setManual(String(savedRef.current));
        draftRef.current = savedRef.current;
        toast.error(result?.message ?? "Could not save progress.");
      }
    }, SAVE_DEBOUNCE_MS);
  };

  // Closing mid-debounce must not lose the last tap.
  useEffect(
    () => () => {
      window.clearTimeout(timerRef.current);
      const pending = pendingRef.current;
      if (pending !== null && pending !== savedRef.current) flush.current(pending);
    },
    [],
  );

  const episodes = useMemo(() => {
    const start = page * PER_PAGE;
    const end = Math.min(available, start + PER_PAGE);
    return Array.from({ length: Math.max(0, end - start) }, (_, offset) => start + offset + 1);
  }, [page, available]);

  const percent = available > 0 ? Math.round((draft / available) * 100) : 0;

  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      title={item.title}
      subtitle={item.title_english && item.title_english !== item.title ? item.title_english : null}
      footer={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SaveStatus status={status} />

          {confirmRemove ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-fg-muted">Remove from watchlist?</span>
              <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(false)}>
                Cancel
              </Button>
              <Button size="sm" variant="danger" onClick={() => onRemove(item)}>
                Remove
              </Button>
            </div>
          ) : (
            <Button size="sm" variant="danger" onClick={() => setConfirmRemove(true)}>
              <Trash size={15} aria-hidden="true" />
              Remove
            </Button>
          )}
        </div>
      }
    >
      <div className="flex gap-4">
        {item.cover_image ? (
          <img
            src={item.cover_image}
            alt=""
            width={80}
            height={120}
            loading="lazy"
            className="hidden h-[120px] w-20 shrink-0 rounded-control border border-line object-cover sm:block"
          />
        ) : null}

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {item.next_episode ? (
              <Badge tone="accent">
                EP {item.next_episode.episode} ·{" "}
                {formatCountdown(adjustedAiringAt(item.next_episode, item.offset_minutes))}
              </Badge>
            ) : null}
            {item.status ? <Badge>{item.status.replaceAll("_", " ").toLowerCase()}</Badge> : null}
            {item.latest_episode_at ? (
              <span className="text-xs text-fg-subtle">
                latest aired {formatRelative(item.latest_episode_at)}
              </span>
            ) : null}
          </div>

          <div className="mt-3">
            <div className="flex items-baseline justify-between text-sm">
              <span className="font-medium text-fg">
                <span className="tabular">{draft}</span>
                <span className="text-fg-subtle"> / {available || "?"} episodes</span>
              </span>
              <span className="tabular text-xs text-fg-muted">{percent}%</span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div
                className={`h-full rounded-full transition-[width] duration-300 ${
                  percent >= 100 ? "bg-up" : "bg-primary-fg"
                }`}
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => commit(available)} disabled={!available || draft >= available}>
              Mark all watched
            </Button>
            <Button size="sm" variant="ghost" onClick={() => commit(0)} disabled={draft === 0}>
              Reset
            </Button>
            {item.site_url ? (
              <a
                href={item.site_url}
                target="_blank"
                rel="noreferrer"
                className="touch-target inline-flex items-center gap-1.5 rounded-control px-3 text-sm font-medium text-primary-fg transition-colors hover:bg-surface-2"
              >
                AniList
                <ArrowSquareOut size={14} aria-hidden="true" />
              </a>
            ) : null}
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <PlatformSelect
          item={item}
          onPick={async (value) => {
            const previous = item.platform ?? null;
            onPlatform(item.anime_id, value);
            try {
              await setPlatform(item.anime_id, value);
            } catch (error) {
              onPlatform(item.anime_id, previous);
              toast.error(error.message);
            }
          }}
        />

        <OffsetControl
          item={item}
          onSave={async (value) => {
            const previous = item.offset_minutes ?? 0;
            onOffset(item.anime_id, value);
            try {
              await setAiringOffset(item.anime_id, value);
            } catch (error) {
              onOffset(item.anime_id, previous);
              toast.error(error.message);
            }
          }}
        />
      </div>

      <hr className="my-4 border-line" />

      {available > 0 ? (
        <>
          {pageCount > 1 ? (
            <div className="mb-3 flex flex-wrap items-center gap-1.5">
              {Array.from({ length: pageCount }, (_, index) => {
                const from = index * PER_PAGE + 1;
                const to = Math.min(available, (index + 1) * PER_PAGE);
                const active = index === page;
                return (
                  <button
                    key={index}
                    type="button"
                    onClick={() => setPage(index)}
                    aria-current={active ? "true" : undefined}
                    className={[
                      "tabular cursor-pointer rounded-control border px-2.5 py-1 text-xs font-medium",
                      "transition-colors duration-150",
                      active
                        ? "border-primary-fg/40 bg-primary/20 text-primary-fg"
                        : "border-line bg-surface-2 text-fg-muted hover:bg-surface-3 hover:text-fg",
                    ].join(" ")}
                  >
                    {from}–{to}
                  </button>
                );
              })}
            </div>
          ) : null}

          <div className="grid grid-cols-5 gap-1.5">
            {episodes.map((episode) => {
              const watched = episode <= draft;
              const nextUp = episode === draft + 1;
              const notAired = aired > 0 && episode > aired;

              return (
                <button
                  key={episode}
                  type="button"
                  aria-pressed={watched}
                  aria-label={`Episode ${episode}${notAired ? ", not aired yet" : ""}`}
                  title={notAired ? "Has not aired yet" : undefined}
                  onClick={() => commit(episode === draftRef.current ? episode - 1 : episode)}
                  className={[
                    "tabular relative flex h-11 cursor-pointer items-center justify-center rounded-control",
                    "border text-sm font-medium transition-colors duration-150",
                    watched
                      ? "border-primary bg-primary text-white hover:bg-primary-hover"
                      : nextUp
                        ? "border-primary-fg/50 bg-surface-2 text-primary-fg hover:bg-surface-3"
                        : "border-line bg-surface-2 text-fg-muted hover:bg-surface-3 hover:text-fg",
                    notAired && !watched ? "border-dashed opacity-55" : "",
                  ].join(" ")}
                >
                  {episode}
                  {watched ? (
                    <Check
                      size={10}
                      weight="bold"
                      aria-hidden="true"
                      className="absolute top-1 right-1 opacity-70"
                    />
                  ) : null}
                </button>
              );
            })}
          </div>

          <p className="mt-3 text-xs text-fg-subtle">
            Tap an episode to mark everything up to it as watched. Tap the current one again to
            step back. Saved automatically.
          </p>
        </>
      ) : (
        <Input
          label="Episodes watched"
          type="number"
          inputMode="numeric"
          min={0}
          value={manual}
          onChange={(event) => setManual(event.target.value)}
          onBlur={() => commit(Number(manual) || 0)}
          hint="AniList did not report an episode count for this title, so enter the number directly."
          className="max-w-xs"
        />
      )}
    </Modal>
  );
}

/**
 * "Watching on" picker.
 *
 * AniList's links are only a suggestion — a title may list Crunchyroll while
 * actually airing on Bilibili in this region — so the list is the full service
 * catalogue, with AniList's guesses grouped at the top.
 *
 * A native `<select>` rather than a custom popover: this sits inside a modal
 * whose focus trap handles Escape in the capture phase, so a custom listbox
 * could never take Escape for itself, and the native control also gets proper
 * keyboard support and the system picker on phones for free.
 */
function PlatformSelect({ item, onPick }) {
  const [catalog, setCatalog] = useState([]);

  useEffect(() => {
    const controller = new AbortController();
    getPlatforms(controller.signal)
      .then((data) => setCatalog(data.platforms ?? []))
      .catch(() => {
        /* Suggested links still work on their own. */
      });
    return () => controller.abort();
  }, []);

  const suggested = item.platforms ?? [];
  const suggestedKeys = new Set(suggested.map((entry) => entry.site.toLowerCase()));
  const others = catalog.filter((entry) => !suggestedKeys.has(entry.site.toLowerCase()));

  const selected = item.platform ?? "";
  // A service saved before it existed in the catalogue must still be selectable.
  const missing = selected && ![...suggested, ...others].some((entry) => entry.site === selected);

  const active =
    suggested.find((entry) => entry.site === selected) ??
    catalog.find((entry) => entry.site === selected) ??
    null;

  return (
    <div>
      <label
        htmlFor={`platform-${item.anime_id}`}
        className="mb-1.5 block text-sm font-medium text-fg-muted"
      >
        Watching on
      </label>

      <div className="flex items-center gap-2">
        <PlatformMark platform={active} name={selected} />

        <select
          id={`platform-${item.anime_id}`}
          value={selected}
          onChange={(event) => onPick(event.target.value || null)}
          className={[
            "touch-target min-w-0 flex-1 cursor-pointer rounded-control border border-line",
            "bg-surface-2 px-3 text-sm text-fg transition-colors duration-150",
            "hover:bg-surface-3 focus:border-primary-fg focus:outline-none",
          ].join(" ")}
        >
          <option value="">Not set</option>
          {missing ? <option value={selected}>{selected}</option> : null}
          {suggested.length ? (
            <optgroup label="Listed on AniList">
              {suggested.map((entry) => (
                <option key={`s-${entry.site}`} value={entry.site}>
                  {entry.site}
                </option>
              ))}
            </optgroup>
          ) : null}
          {others.length ? (
            <optgroup label="All services">
              {others.map((entry) => (
                <option key={`o-${entry.site}`} value={entry.site}>
                  {entry.site}
                </option>
              ))}
            </optgroup>
          ) : null}
        </select>
      </div>
    </div>
  );
}

/** Favicon when AniList supplied one, otherwise a brand-coloured initial. */
function PlatformMark({ platform, name }) {
  if (!name) {
    return (
      <span
        aria-hidden="true"
        className="h-7 w-7 shrink-0 rounded-control border border-dashed border-line"
      />
    );
  }

  if (platform?.icon) {
    return (
      <img
        src={platform.icon}
        alt=""
        width={28}
        height={28}
        className="h-7 w-7 shrink-0 rounded-control border border-line object-contain"
      />
    );
  }

  return (
    <span
      aria-hidden="true"
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-control border border-line text-xs font-semibold text-white"
      style={{ backgroundColor: platform?.color ?? "var(--color-surface-3)" }}
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

/**
 * Local release delay, shared with the Discord bot's `/setoffset`.
 *
 * Some services publish an episode later than AniList's schedule says; the
 * offset shifts both the countdown here and when the bot notifies.
 */
function OffsetControl({ item, onSave }) {
  const saved = item.offset_minutes ?? 0;
  const [value, setValue] = useState(String(saved));

  useEffect(() => setValue(String(saved)), [saved]);

  const commit = (next) => {
    const minutes = Number.isFinite(next) ? Math.trunc(next) : 0;
    setValue(String(minutes));
    if (minutes !== saved) onSave(minutes);
  };

  const shifted = adjustedAiringAt(item.next_episode, saved);

  return (
    <div>
      <label
        htmlFor={`offset-${item.anime_id}`}
        className="mb-1.5 block text-sm font-medium text-fg-muted"
      >
        Release delay
      </label>

      <div className="flex items-center gap-2">
        <input
          id={`offset-${item.anime_id}`}
          type="number"
          inputMode="numeric"
          step={15}
          min={-1440}
          max={1440}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onBlur={() => commit(Number(value))}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
          className={[
            "touch-target tabular w-24 rounded-control border border-line bg-surface-2 px-3",
            "text-sm text-fg transition-colors duration-150",
            "focus:border-primary-fg focus:outline-none",
          ].join(" ")}
        />
        <span className="text-sm text-fg-subtle">min</span>

        <div className="ml-auto flex gap-1">
          {OFFSET_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => commit(preset)}
              aria-pressed={saved === preset}
              className={[
                "tabular cursor-pointer rounded-control border px-2 py-1 text-xs font-medium",
                "transition-colors duration-150",
                saved === preset
                  ? "border-primary-fg/40 bg-primary/20 text-primary-fg"
                  : "border-line bg-surface-2 text-fg-muted hover:bg-surface-3 hover:text-fg",
              ].join(" ")}
            >
              {preset === 0 ? "None" : `+${preset}`}
            </button>
          ))}
        </div>
      </div>

      <p className="mt-1.5 text-xs text-fg-subtle">
        {saved === 0 ? (
          "Airs when AniList says. Also used by the Discord bot."
        ) : shifted ? (
          <>
            Next episode shifts to <span className="tabular">{formatCountdown(shifted)}</span>.
          </>
        ) : (
          <>
            Notifications wait <span className="tabular">{saved}</span> min after AniList.
          </>
        )}
      </p>
    </div>
  );
}

function SaveStatus({ status }) {
  if (status === "idle") {
    return <span className="text-xs text-fg-subtle">Changes save automatically</span>;
  }
  if (status === "saving") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-fg-muted">
        <SpinnerGap size={14} className="animate-spin" aria-hidden="true" />
        Saving…
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-danger">
        <CloudSlash size={14} weight="fill" aria-hidden="true" />
        Not saved — reverted
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-up">
      <CloudCheck size={14} weight="fill" aria-hidden="true" />
      Saved
    </span>
  );
}
