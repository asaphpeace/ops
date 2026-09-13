// Shared localStorage-backed cache for the read-mostly stats endpoints My
// Desk and Command Center both call. An in-memory cache would die on a
// plain page reload (F5) — the actual "don't call APIs every refresh"
// complaint — so this persists across reloads instead. 10-minute default
// freshness, matching the backend's own bumped Jira-layer cache TTL, plus a
// manual force-refresh path so a page never gets stuck waiting on a stale
// number for a full 10 minutes.
//
// Balance between stale and refresh, the other half of that same design:
// a live fetch failure (Jira unreachable, an expired token, a network
// hiccup) must never wipe out data we already have. If a fetch fails and a
// previously-cached entry exists — however old — serve it instead of
// throwing, so a dashboard that already loaded once keeps showing real
// numbers through an outage instead of going blank. Only propagate the
// error when there's truly nothing cached yet (a genuine first load with
// no connectivity). isStaleFallback() lets a caller show "showing cached
// data" instead of silently pretending a stale serve was a fresh one.

const DEFAULT_TTL_MS = 10 * 60 * 1000
const PREFIX = 'so_cache:'

interface CacheEntry<T> {
  timestamp: number
  data: T
}

// Keys served from a stale cache entry because the live refresh that would
// have replaced them just failed — session-only, not persisted. Cleared at
// the start of every call for that key so a later successful refresh (or a
// fresh in-TTL cache hit) correctly un-flags it.
const staleFallbackKeys = new Set<string>()

export function isStaleFallback(key: string): boolean {
  return staleFallbackKeys.has(key)
}

function readEntry<T>(storageKey: string): CacheEntry<T> | null {
  try {
    const raw = localStorage.getItem(storageKey)
    return raw ? (JSON.parse(raw) as CacheEntry<T>) : null
  } catch {
    return null
  }
}

export async function cachedFetch<T>(
  key: string,
  fetchFn: () => Promise<T>,
  opts?: { force?: boolean; ttlMs?: number },
): Promise<T> {
  const ttl = opts?.ttlMs ?? DEFAULT_TTL_MS
  const storageKey = PREFIX + key
  staleFallbackKeys.delete(key)

  if (!opts?.force) {
    const entry = readEntry<T>(storageKey)
    if (entry && Date.now() - entry.timestamp < ttl) return entry.data
  }

  try {
    const data = await fetchFn()
    try {
      localStorage.setItem(storageKey, JSON.stringify({ timestamp: Date.now(), data }))
    } catch {
      // storage full or unavailable (private browsing) — non-fatal, just skip caching
    }
    return data
  } catch (err) {
    const stale = readEntry<T>(storageKey)
    if (stale) {
      // eslint-disable-next-line no-console
      console.warn(`cachedFetch(${key}): live refresh failed, serving cached data from ${new Date(stale.timestamp).toISOString()}`, err)
      staleFallbackKeys.add(key)
      return stale.data
    }
    throw err
  }
}

export function cacheAgeLabel(key: string): string | null {
  try {
    const raw = localStorage.getItem(PREFIX + key)
    if (!raw) return null
    const entry = JSON.parse(raw) as CacheEntry<unknown>
    const secs = Math.round((Date.now() - entry.timestamp) / 1000)
    if (secs < 60) return 'just now'
    return `${Math.round(secs / 60)}m ago`
  } catch {
    return null
  }
}
