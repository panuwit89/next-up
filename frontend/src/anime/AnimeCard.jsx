import { Check, ImageBroken, WarningCircle } from "@phosphor-icons/react";

import { Badge } from "../components/Feedback.jsx";
import { formatCountdown } from "../lib/format.js";
import { adjustedAiringAt } from "./EpisodePicker.jsx";

/**
 * One tracked show. The whole card is a single control — in select mode it
 * toggles selection, otherwise it opens the episode picker — so there are never
 * nested interactive elements to confuse keyboard or screen-reader users.
 */
export default function AnimeCard({ item, index, selectMode, selected, onActivate }) {
  const {
    title,
    title_english: titleEnglish,
    cover_image: cover,
    total_episodes: total,
    latest_episode: latest,
    watched_episode: watched,
    next_episode: next,
    offset_minutes: offsetMinutes,
    platform,
    platforms,
    unavailable,
  } = item;

  const available = total ?? latest ?? 0;
  const percent = available > 0 ? Math.min(100, (watched / available) * 100) : 0;
  // Show the time the episode actually reaches the user's service, not AniList's.
  const countdown = next ? formatCountdown(adjustedAiringAt(next, offsetMinutes)) : null;
  // Only ever the platform the user actually picked — falling back to the first
  // AniList streaming link would display a choice they never made.
  const activePlatform = platform ?? null;
  // AniList's episode count sometimes lags the schedule, so a still-airing show
  // can read as 100%. "Done" belongs only to shows that have finished airing.
  const complete = !next && available > 0 && percent >= 100;

  const label = selectMode
    ? `${selected ? "Deselect" : "Select"} ${title}`
    : `${title} — watched ${watched} of ${total ?? "?"} episodes. Open episode picker.`;

  return (
    <button
      type="button"
      onClick={onActivate}
      aria-label={label}
      aria-pressed={selectMode ? selected : undefined}
      style={{ "--i": index }}
      className={[
        "group relative cursor-pointer rounded-card text-left",
        "transition-transform duration-200 ease-out",
        "hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.985]",
      ].join(" ")}
    >
      <div
        className={[
          "relative aspect-[2/3] overflow-hidden rounded-card border bg-surface-2",
          "transition-colors duration-150",
          selected ? "border-primary-fg ring-2 ring-primary-fg/40" : "border-line group-hover:border-line-strong",
        ].join(" ")}
      >
        {cover ? (
          <img
            src={cover}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover transition-transform duration-300 ease-out group-hover:scale-[1.04]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-fg-subtle">
            <ImageBroken size={28} aria-hidden="true" />
          </div>
        )}

        {/* Scrim so the overlay text stays legible on any cover art. */}
        <div
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-black/85 to-transparent"
        />

        {countdown ? (
          <span className="absolute top-2 left-2 rounded-full bg-black/70 px-2 py-0.5 text-[11px] font-medium text-fg backdrop-blur-sm">
            EP {next.episode} · <span className="tabular">{countdown}</span>
          </span>
        ) : null}

        {unavailable ? (
          <span
            className="absolute top-2 right-2 text-warn"
            title="AniList did not return this title"
          >
            <WarningCircle size={18} weight="fill" aria-hidden="true" />
          </span>
        ) : null}

        {selectMode ? (
          <span
            aria-hidden="true"
            className={[
              "absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded-md border-2",
              selected
                ? "border-primary-fg bg-primary-fg text-bg"
                : "border-white/70 bg-black/40",
            ].join(" ")}
          >
            {selected ? <Check size={14} weight="bold" /> : null}
          </span>
        ) : null}

        <div className="absolute inset-x-0 bottom-0 px-2 pb-2">
          <div
            className="h-1 overflow-hidden rounded-full bg-white/20"
            role="progressbar"
            aria-valuenow={watched}
            aria-valuemin={0}
            aria-valuemax={available || undefined}
            aria-label={`${watched} of ${available || "unknown"} episodes watched`}
          >
            <div
              className={`h-full rounded-full transition-[width] duration-300 ${
                percent >= 100 ? "bg-up" : "bg-primary-fg"
              }`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      </div>

      <h3
        className="mt-2 line-clamp-2 text-[13px] leading-snug font-medium text-fg"
        title={titleEnglish ? `${title} · ${titleEnglish}` : title}
      >
        {title}
      </h3>

      <div className="mt-1 flex items-center gap-1.5 text-[11px] text-fg-subtle">
        <span className="tabular">
          {watched}/{total ?? "?"}
        </span>
        {activePlatform ? (
          <>
            <span aria-hidden="true">·</span>
            <span className="truncate">{activePlatform}</span>
          </>
        ) : null}
        {complete ? (
          <Badge tone="up" className="ml-auto shrink-0 !px-1.5 !py-0 !text-[10px]">
            <Check size={10} weight="bold" aria-hidden="true" />
            Done
          </Badge>
        ) : null}
      </div>
    </button>
  );
}
