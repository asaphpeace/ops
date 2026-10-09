// Shared formatting / derivation helpers for the customer profile sections.
// Moved over from the retired CustomerDrillPanel.vue so behaviour (version
// colouring, WildFly inference, cert thresholds) stays exactly as before.

export function fmtDate(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
export function fmtMonth(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}
export function fmtDateTime(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
export function formatArr(v?: number | null) {
  if (v == null) return null
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}K`
  return `£${v.toLocaleString()}`
}

// Real element-wise comparison, not parseFloat — parseFloat("8.3.3") == 8.3
// would rank above 8.20 even though 8.3.x is many releases older.
export function versionAtLeast(release: string | null | undefined, min: number[]): boolean {
  const v = release?.match(/\d+/g)?.map(Number)
  if (!v || !v.length) return false
  for (let i = 0; i < Math.max(v.length, min.length); i++) {
    const d = (v[i] ?? 0) - (min[i] ?? 0)
    if (d !== 0) return d > 0
  }
  return true
}
/** 'bad' below 8.23, 'warn' below 8.27, '' otherwise — same thresholds as the exports. */
export function versionTone(v?: string | null): '' | 'warn' | 'bad' {
  if (!v) return ''
  if (!versionAtLeast(v, [8, 23])) return 'bad'
  if (!versionAtLeast(v, [8, 27])) return 'warn'
  return ''
}
/** Not from any API — the agreed heuristic: 8.20+ is probably WildFly 33. */
export function wildflyGuess(release: string | null | undefined): string | null {
  if (!release?.match(/\d/)) return null
  return versionAtLeast(release, [8, 20]) ? '33 (inferred)' : '8 (inferred, legacy)'
}

export function host(subdomain: string) {
  if (subdomain.includes('://')) return new URL(subdomain).host
  return subdomain.includes('.') ? subdomain.split('/')[0] : `${subdomain}.dataloy.com`
}
export function daysUntil(iso?: string | null): number | null {
  if (!iso) return null
  return Math.floor((new Date(iso).getTime() - Date.now()) / 86_400_000)
}
/** Matches services/cert_scan.py's thresholds: ≤7 days critical, ≤30 warn. */
export function certTone(days: number | null): '' | 'ok' | 'warn' | 'bad' {
  if (days === null) return ''
  if (days <= 7) return 'bad'
  if (days <= 30) return 'warn'
  return 'ok'
}
export function usageTone(used: number, limit: number): '' | 'warn' | 'bad' {
  if (!limit) return ''
  if (used >= limit) return 'bad'
  if (used > limit * 0.7) return 'warn'
  return ''
}
