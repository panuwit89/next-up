/**
 * Formatting helpers shared by both tabs.
 *
 * Locales are pinned rather than left to the browser: `en-US` digits keep the
 * tabular columns aligned, and `en-GB` dates ("31 Jul 2026") are unambiguous —
 * unlike `th-TH`, which would render Buddhist-era years in the price charts.
 */

const NUMBER_LOCALE = "en-US";
const DATE_LOCALE = "en-GB";

const CURRENCY_SIGNS = { USD: "$", THB: "฿", EUR: "€", GBP: "£", JPY: "¥" };

export const currencySign = (code) => CURRENCY_SIGNS[code] ?? "";

/** Price with the precision the magnitude deserves — penny stocks keep decimals. */
export function formatPrice(value, currency) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const digits = Math.abs(value) < 1 ? 4 : 2;
  return (
    currencySign(currency) +
    value.toLocaleString(NUMBER_LOCALE, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  );
}

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString(NUMBER_LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Always signed, because the sign — not just the colour — carries the meaning. */
export function formatSigned(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return sign + Math.abs(value).toLocaleString(NUMBER_LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${formatSigned(value, digits)}%`;
}

/** 3.24T / 891.5B / 12.0M — market cap and volume. */
export function formatCompact(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const units = [
    [1e12, "T"],
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ];
  for (const [size, suffix] of units) {
    if (abs >= size) return (value / size).toFixed(2).replace(/\.00$/, "") + suffix;
  }
  return value.toLocaleString(NUMBER_LOCALE);
}

/** Direction as a token, so colour is never the only signal. */
export function direction(value) {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

/* ------------------------------------------------------------- dates ----- */

const toDate = (unixSeconds) => new Date(unixSeconds * 1000);

export function formatDate(unixSeconds) {
  if (!unixSeconds) return "—";
  return toDate(unixSeconds).toLocaleDateString(DATE_LOCALE, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(unixSeconds) {
  if (!unixSeconds) return "—";
  return toDate(unixSeconds).toLocaleString(DATE_LOCALE, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function formatTime(unixSeconds) {
  if (!unixSeconds) return "—";
  return toDate(unixSeconds).toLocaleTimeString(DATE_LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** "2 days ago" / "in 3 hours" — used for episode air times. */
export function formatRelative(unixSeconds) {
  if (!unixSeconds) return "—";
  const deltaSeconds = unixSeconds - Date.now() / 1000;
  const steps = [
    [60, "second"],
    [3600, "minute"],
    [86400, "hour"],
    [604800, "day"],
    [2629800, "week"],
    [31557600, "month"],
    [Infinity, "year"],
  ];

  let previous = 1;
  for (const [limit, unit] of steps) {
    if (Math.abs(deltaSeconds) < limit) {
      const formatter = new Intl.RelativeTimeFormat(DATE_LOCALE, { numeric: "auto" });
      return formatter.format(Math.round(deltaSeconds / previous), unit);
    }
    previous = limit;
  }
  return "—";
}

/** Compact countdown for the "next episode" pill: 2d 04h / 04h 12m / 12m. */
export function formatCountdown(unixSeconds) {
  if (!unixSeconds) return null;
  let remaining = Math.floor(unixSeconds - Date.now() / 1000);
  if (remaining <= 0) return "airing now";

  const days = Math.floor(remaining / 86400);
  remaining %= 86400;
  const hours = Math.floor(remaining / 3600);
  remaining %= 3600;
  const minutes = Math.floor(remaining / 60);

  if (days > 0) return `${days}d ${String(hours).padStart(2, "0")}h`;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  return `${minutes}m`;
}
