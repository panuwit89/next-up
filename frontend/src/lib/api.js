/**
 * Thin wrapper over the FastAPI dashboard API (`/api/*`, single user, no auth).
 *
 * Every call resolves to parsed JSON or throws an Error carrying the message
 * FastAPI put in `detail`, so callers can surface it verbatim.
 */

const BASE = "/api";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function readDetail(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  // 422s arrive as a list of {loc, msg, type}.
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item.msg || String(item)).join(", ");
  }
  return fallback;
}

async function request(path, { method = "GET", body, signal } = {}) {
  let response;
  try {
    response = await fetch(BASE + path, {
      method,
      signal,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    if (cause.name === "AbortError") throw cause;
    throw new ApiError("Cannot reach the server. Is the API running?", 0);
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      readDetail(payload, `Request failed (${response.status})`),
      response.status,
    );
  }
  return payload;
}

/* -------------------------------------------------------------- anime ---- */

export const getAnime = (signal) => request("/anime", { signal });

export const searchAnime = (query, signal) =>
  request(`/anime/search?q=${encodeURIComponent(query)}`, { signal });

export const subscribeAnime = (animeId, title) =>
  request("/anime", { method: "POST", body: { anime_id: animeId, title } });

export const unsubscribeAnime = (animeIds) =>
  request("/anime", { method: "DELETE", body: { anime_ids: animeIds } });

export const setWatchedEpisode = (animeId, watchedEpisode) =>
  request(`/anime/${animeId}/progress`, {
    method: "PUT",
    body: { watched_episode: watchedEpisode },
  });

export const setPlatform = (animeId, platform) =>
  request(`/anime/${animeId}/platform`, { method: "PUT", body: { platform } });

export const getPlatforms = (signal) => request("/anime/platforms", { signal });

export const setAiringOffset = (animeId, offsetMinutes) =>
  request(`/anime/${animeId}/offset`, {
    method: "PUT",
    body: { offset_minutes: offsetMinutes },
  });

/* ------------------------------------------------------------- stocks ---- */

export const getStocks = (signal) => request("/stocks", { signal });

export const addStock = (symbol) => request("/stocks", { method: "POST", body: { symbol } });

export const removeStock = (symbol) =>
  request(`/stocks/${encodeURIComponent(symbol)}`, { method: "DELETE" });

export const getStockDetail = (symbol, range, signal) =>
  request(`/stocks/${encodeURIComponent(symbol)}?range=${encodeURIComponent(range)}`, { signal });

export const getStockNews = (symbol, signal) =>
  request(`/stocks/${encodeURIComponent(symbol)}/news`, { signal });

export { ApiError };
