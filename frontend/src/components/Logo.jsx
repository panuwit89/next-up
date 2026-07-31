/**
 * App mark: a solid play triangle with a market line rising out from under it.
 *
 * Built on a 32×32 grid with the line *grazing* the triangle's lower-left edge
 * rather than crossing its middle — a line through the body breaks the play
 * silhouette, which is the only thing still legible once this is a 16px favicon.
 * Solid fill for the same reason: outlined marks turn to mush at that size.
 *
 * Colours come from the design tokens, so the mark follows the palette.
 * `mono` renders it in `currentColor` for single-colour contexts.
 */
export default function Logo({ size = 28, mono = false, className, title }) {
  const play = mono ? "currentColor" : "var(--color-primary-fg, #60a5fa)";
  const line = mono ? "currentColor" : "var(--color-up, #34d399)";

  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={className}
      role={title ? "img" : undefined}
      aria-label={title || undefined}
      aria-hidden={title ? undefined : "true"}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M5 6.5 L5 24.5 L17.5 15.5 Z" fill={play} />
      <path
        d="M6 24.5 L12 19 L16 22.5 L24.5 10.5"
        stroke={line}
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect x="22" y="8" width="5" height="5" rx="1.5" fill={line} />
    </svg>
  );
}
