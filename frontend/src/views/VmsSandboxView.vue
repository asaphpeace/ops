<template>
  <div class="view">
    <div class="sh">
      <div><h2>VMS Sandbox</h2><p>Paste a token · explore the real Dataloy VMS · compare fetches</p></div>
    </div>

    <!-- TOKEN SLOTS -->
    <div class="vsb-slots">
      <div class="tw vsb-card" v-for="s in (['A','B'] as const)" :key="s">
        <div class="vsb-eyebrow">Slot {{ s }}</div>
        <textarea class="inp vsb-token" placeholder="Paste access token (JWT)…" v-model="slots[s].token" rows="2"></textarea>
        <input class="inp vsb-host" placeholder="Tenant host, e.g. demonew.dataloy.com" v-model="slots[s].host">
        <label class="vsb-demo-check">
          <input type="checkbox" v-model="slots[s].isDemo"> this is the demo/sandbox token (allow writes)
        </label>
        <div v-if="decoded(s)" class="sub vsb-decoded">
          aud={{ decoded(s)!.aud ?? '—' }} · {{ expiryLabel(s) }}
          <template v-if="decoded(s)!.sub"> · sub={{ decoded(s)!.sub }}</template>
        </div>
        <div v-else-if="slots[s].token.trim()" class="sub vsb-decoded" style="color:var(--red)">Couldn't decode this token as a JWT.</div>
      </div>
    </div>

    <!-- REQUEST BUILDER -->
    <div class="tw vsb-card" style="margin-top:14px">
      <div class="vsb-eyebrow" style="display:flex;align-items:center;justify-content:space-between">
        <span>Request Builder</span>
        <span class="sub">sending as
          <select class="sel" v-model="sendingAs" style="width:56px">
            <option value="A">A</option>
            <option value="B">B</option>
          </select>
        </span>
      </div>
      <div class="vsb-builder-row">
        <input class="inp" style="width:160px" list="vsb-entities" placeholder="Entity (e.g. Voyage)" v-model="entityInput">
        <datalist id="vsb-entities">
          <option v-for="e in KNOWN_ENTITIES" :key="e" :value="e" />
        </datalist>
        <select class="sel" v-model="methodInput" style="width:90px">
          <option v-for="m in methodOptions" :key="m" :value="m">{{ m }}</option>
        </select>
        <input class="inp" style="width:140px" placeholder="Key" v-model="keyInput">
        <input class="inp" style="width:180px" placeholder="Filter (list GET only)" v-model="filterInput" :disabled="methodInput !== 'GET' || !!keyInput.trim()">
        <button class="btn btn-sm" :disabled="!entityInput.trim() || !slots[sendingAs].host.trim() || sending" @click="send">{{ sending ? 'Sending…' : 'Send' }}</button>
      </div>
      <textarea v-if="methodInput === 'POST' || methodInput === 'PUT'" class="inp vsb-body" placeholder="Request body (JSON)" v-model="bodyText" rows="4"></textarea>
      <div v-if="methodInput !== 'GET'" class="sub" style="font-size:10px;color:var(--text3);margin-top:4px">
        Write methods only unlock when Slot {{ sendingAs }}'s demo checkbox is ticked.
      </div>
    </div>

    <!-- RESPONSE + SNAPSHOT -->
    <div class="vsb-two-col" style="margin-top:14px">
      <div class="tw vsb-card">
        <div class="vsb-eyebrow">Response</div>
        <div v-if="!response" class="vsb-empty-hint">
          <div class="sub" style="font-size:11px;color:var(--text3)">Nothing sent yet.</div>
          <div class="sub" style="font-size:11px;margin-top:6px">
            First time here? Try a real chase:
            <a href="#" class="vsb-example-link" @click.prevent="loadExample">Vessel/1609784 → PortCall (openPosition) → Voyage (ownedByVoyage) → Cargo</a>
          </div>
        </div>
        <template v-else>
          <div class="sub" style="margin-bottom:8px">status: {{ response.status ?? '—' }}<template v-if="response.message"> · {{ response.message }}</template></div>
          <div v-if="paginationCapHint" class="vsb-cap-hint">⚠ {{ paginationCapHint }}</div>
          <div v-if="chaseableFields.length" class="vsb-chase-list">
            <div v-for="f in chaseableFields" :key="f.key" class="vsb-chase-row" @click="chase(f)">
              🔗 {{ f.key }}: {{ f.refKey }} <span class="sub">→ {{ f.guessedEntity }}</span>
            </div>
          </div>
          <button
            v-if="realPointerCount > 0"
            class="btn btn-sm"
            style="margin-bottom:10px"
            :disabled="isCrawling"
            @click="autoCrawl"
          >🔍 Auto-Crawl from here ({{ realPointerCount }} pointer{{ realPointerCount !== 1 ? 's' : '' }})</button>
          <pre class="vsb-json">{{ prettyJson(response.data) }}</pre>
        </template>
      </div>

      <div class="tw vsb-card">
        <div class="vsb-eyebrow" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px">
          <span>Environment Snapshot <span class="sub">· Slot {{ sendingAs }}</span></span>
          <span v-if="isCrawling || crawlSummary" class="vsb-crawl-controls">
            <label class="sub" style="display:flex;align-items:center;gap:3px">depth <input type="number" class="inp vsb-num" v-model.number="maxDepth" min="1" max="5" :disabled="isCrawling"></label>
            <label class="sub" style="display:flex;align-items:center;gap:3px">nodes <input type="number" class="inp vsb-num" v-model.number="maxNodes" min="1" max="100" :disabled="isCrawling"></label>
          </span>
          <span v-else class="vsb-crawl-controls">
            <label class="sub" style="display:flex;align-items:center;gap:3px">depth <input type="number" class="inp vsb-num" v-model.number="maxDepth" min="1" max="5"></label>
            <label class="sub" style="display:flex;align-items:center;gap:3px">nodes <input type="number" class="inp vsb-num" v-model.number="maxNodes" min="1" max="100"></label>
          </span>
        </div>
        <div v-if="isCrawling" class="vsb-crawl-status">
          <span>Crawling… {{ crawlProgress.fetched }}/{{ maxNodes }} fetched, depth {{ crawlProgress.depth }} of {{ maxDepth }}</span>
          <button class="btn btn-sm btn-red" @click="crawlAbort = true">■ Stop</button>
        </div>
        <div v-else-if="crawlSummary" class="vsb-crawl-summary">
          <div class="sub" style="font-weight:700;color:var(--text2);margin-bottom:4px">
            Snapshot: {{ crawlSummary.total }} node{{ crawlSummary.total !== 1 ? 's' : '' }} · {{ (crawlSummary.elapsedMs / 1000).toFixed(1) }}s{{ crawlSummary.errors ? ` · ${crawlSummary.errors} error${crawlSummary.errors !== 1 ? 's' : ''}` : '' }}{{ crawlSummary.stopped ? ' · stopped early' : '' }}
          </div>
          <div class="sub" style="font-size:10px">
            <span v-for="(count, entity) in crawlSummary.byEntity" :key="entity" style="margin-right:10px">{{ entity }}: {{ count }}</span>
          </div>
        </div>
        <div v-if="!snapshotTrees[sendingAs].length" class="sub" style="font-size:11px;color:var(--text3);margin-top:8px">Nothing fetched by key yet.</div>
        <ul v-else class="vsn-children" style="padding-left:0;border-left:none;margin-top:8px">
          <VmsSnapshotNode v-for="(n, i) in snapshotTrees[sendingAs]" :key="i" :node="n" />
        </ul>
      </div>
    </div>

    <!-- COMPARE / VERDICT -->
    <div class="tw vsb-card" style="margin-top:14px">
      <div class="vsb-eyebrow">Compare / Verdict <span class="sub">· pick any two requests from this session's history</span></div>
      <div class="vsb-builder-row">
        <select class="sel" v-model.number="leftId" style="width:280px">
          <option :value="0" disabled>Left…</option>
          <option v-for="h in history" :key="h.id" :value="h.id">{{ historyLabel(h) }}</option>
        </select>
        <select class="sel" v-model.number="rightId" style="width:280px">
          <option :value="0" disabled>Right…</option>
          <option v-for="h in history" :key="h.id" :value="h.id">{{ historyLabel(h) }}</option>
        </select>
      </div>
      <div v-if="diffRows.length" class="vsb-diff">
        <div v-for="(r, i) in diffRows" :key="i" class="vsb-diff-row" :class="'vsb-diff-' + r.type">
          <span class="vsb-diff-path">{{ r.path }}</span>
          <span class="vsb-diff-vals">{{ JSON.stringify(r.left) }} → {{ JSON.stringify(r.right) }}</span>
        </div>
      </div>
      <div v-else-if="leftId && rightId" class="sub" style="font-size:11px;color:var(--text3)">No differences.</div>
      <textarea class="inp" style="margin-top:10px" placeholder="Verdict notes (this session only)…" v-model="verdictNote" rows="3"></textarea>
    </div>

    <!-- HISTORY -->
    <div class="tw vsb-card" style="margin-top:14px">
      <div class="vsb-eyebrow">History <span class="sub">· {{ history.length }} requests, session only</span></div>
      <div v-if="!history.length" class="sub" style="font-size:11px;color:var(--text3)">Nothing sent yet.</div>
      <div v-for="h in history" :key="h.id" class="vsb-history-row">
        <span class="flag-pill" :style="h.slot === 'A' ? 'background:var(--accent-dim);color:var(--accent)' : 'background:var(--purple-dim);color:var(--purple)'">{{ h.slot }}</span>
        <span>{{ h.method }} {{ h.entity }}{{ h.key ? '/' + h.key : '' }}{{ h.filter ? '?filter=' + h.filter : '' }}</span>
        <span class="sub" style="margin-left:auto">{{ h.status ?? '—' }}</span>
        <span class="sub">{{ formatTime(h.timestamp) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { api } from '@/api/client'
import VmsSnapshotNode, { type SnapshotNode } from '@/components/VmsSnapshotNode.vue'

type SlotId = 'A' | 'B'

interface Slot {
  token: string
  isDemo: boolean
  host: string
}

const slots = reactive<Record<SlotId, Slot>>({
  A: { token: '', isDemo: false, host: '' },
  B: { token: '', isDemo: false, host: '' },
})

const sendingAs = ref<SlotId>('A')

// ── JWT decode (client-side, no signature verification — this is a read
// convenience for the engineer, not an auth boundary) ──
interface DecodedJwt { aud?: string; exp?: number; sub?: string }
function decodeJwt(token: string): DecodedJwt | null {
  const parts = token.trim().split('.')
  if (parts.length < 2) return null
  try {
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(payload))
  } catch {
    return null
  }
}
function decoded(s: SlotId): DecodedJwt | null {
  return slots[s].token.trim() ? decodeJwt(slots[s].token) : null
}
function expiryLabel(s: SlotId): string {
  const d = decoded(s)
  if (!d?.exp) return 'no exp claim'
  const secs = d.exp - Math.floor(Date.now() / 1000)
  if (secs <= 0) return 'expired'
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return `expires in ${h}h ${m}m`
}

// ── Method gating — GET-only unless the sending slot's demo box is ticked ──
const methodOptions = computed<('GET' | 'POST' | 'PUT' | 'DELETE')[]>(() =>
  slots[sendingAs.value].isDemo ? ['GET', 'POST', 'PUT', 'DELETE'] : ['GET']
)
const methodInput = ref<'GET' | 'POST' | 'PUT' | 'DELETE'>('GET')
watch(methodOptions, (opts) => {
  if (!opts.includes(methodInput.value)) methodInput.value = 'GET'
})

// ── Request Builder state ──
const entityInput = ref('')
const keyInput = ref('')
const filterInput = ref('')
const bodyText = ref('')
const sending = ref(false)

interface SandboxResponse { status: number | null; data: unknown; message: string | null }
const response = ref<SandboxResponse | null>(null)

// Known real entity names (the real 34, confirmed live via the docs'
// llms-full.txt export this session) — used both to seed the entity
// autocomplete and to drive the "chaseable field" heuristic below.
const KNOWN_ENTITIES = [
  'Cargo', 'Currency', 'Voyage', 'VoyageHeader', 'Document', 'PortCall', 'Vessel',
  'Commodity', 'BunkerOrder', 'BunkerOrderLine', 'BunkerType', 'BusinessPartner',
  'Address', 'ContactInfo', 'Bank', 'ExchangeRate', 'Remark', 'Event', 'EventLog',
  'StatusType', 'PaymentTerms', 'BusinessUnit', 'BaselineTerm', 'Www', 'User',
  'Company', 'Attachment', 'WebhookSubscription', 'ChannelInfo', 'ChannelType',
  'AuditLog', 'Action', 'System', 'LaytimeTimeSheetItem',
]

// Real API relationships are nested {key, self} objects (confirmed live —
// e.g. vesselType/flag/openPosition/owner), NOT flat primitive fields whose
// name happens to match an entity — the substring heuristic below only
// ever catches false positives against the real shape (e.g. "vesselName"
// matching "Vessel" with a non-key string value). The self URL's path
// segment names the real entity directly, which is more reliable than
// guessing from the field name.
const SELF_URL_ENTITY = /\/ws\/rest\/([^/]+)\/[^/]+$/

interface ChaseTarget { key: string; refKey: string | number; guessedEntity: string; fromArray: boolean }

function isRefObject(v: unknown): v is { key: string | number; self: string } {
  return !!v && typeof v === 'object' && !Array.isArray(v) && 'key' in v && 'self' in v
}

// Pure extraction, callable on ANY fetched payload — not just the currently
// displayed response — so the auto-crawl below can reuse it on every hop's
// result. `includeNameGuess` defaults true for the manual chase-list (kept
// exactly as before); the crawl passes false, since an unattended loop
// should only ever follow real {key,self} pointers, never the weaker
// substring-name guess this function's own comment already documents as
// false-positive-prone.
function extractChaseTargets(data: unknown, opts: { includeNameGuess?: boolean } = {}): ChaseTarget[] {
  const includeNameGuess = opts.includeNameGuess ?? true
  if (!data || typeof data !== 'object' || Array.isArray(data)) return []
  const rows: ChaseTarget[] = []
  for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
    if (isRefObject(v)) {
      const match = SELF_URL_ENTITY.exec(v.self)
      if (match) rows.push({ key: k, refKey: v.key, guessedEntity: match[1], fromArray: false })
      continue
    }
    // Array-of-{key,self} — a real one-to-many relationship (e.g. a
    // Voyage's `cargos`). Previously silently excluded entirely (arrays
    // were skipped outright), which meant the Sandbox's own worked example
    // ("Voyage → cargos[] → Cargo") was never actually clickable — each
    // element becomes its own chase target here.
    if (Array.isArray(v) && v.length && v.every(isRefObject)) {
      v.forEach((ref, i) => {
        const match = SELF_URL_ENTITY.exec((ref as { self: string }).self)
        if (match) rows.push({ key: `${k}[${i}]`, refKey: (ref as { key: string | number }).key, guessedEntity: match[1], fromArray: true })
      })
      continue
    }
    if (!includeNameGuess) continue
    if (typeof v !== 'string' && typeof v !== 'number') continue
    const match = KNOWN_ENTITIES.find(e => k.toLowerCase().includes(e.toLowerCase()))
    if (match) rows.push({ key: k, refKey: v, guessedEntity: match, fromArray: false })
  }
  return rows
}

const chaseableFields = computed(() => extractChaseTargets(response.value?.data, { includeNameGuess: true }))

function chase(f: ChaseTarget) {
  entityInput.value = f.guessedEntity
  keyInput.value = String(f.refKey)
  filterInput.value = ''
  methodInput.value = 'GET'
  pendingChaseParent.value = currentNode.value
}

// The real API enforces a 2000-object cap on unfiltered list calls
// (confirmed live: GET /Voyage with no filter returns exactly this 400
// shape) — surface it as a friendly hint instead of a bare error dump.
const paginationCapHint = computed<string | null>(() => {
  const r = response.value
  if (!r || r.status !== 400) return null
  const d = r.data
  const msg = d && typeof d === 'object' && 'message' in (d as Record<string, unknown>)
    ? String((d as Record<string, unknown>).message)
    : typeof d === 'string' ? d : ''
  if (/too many objects requested/i.test(msg)) {
    return 'This entity has too many records to list without a filter. Try adding a filter (e.g. filter=currencyCode(EQ)USD) or fetch a single record by key instead.'
  }
  return null
})

// A real, validated chase path from this session — pre-fills the builder
// for a first-time user, does not auto-send (token + host are still
// required per slot).
function loadExample() {
  entityInput.value = 'Vessel'
  keyInput.value = '1609784'
  filterInput.value = ''
  methodInput.value = 'GET'
}

// ── Environment Snapshot (accumulating tree, per slot) ──
const snapshotTrees = reactive<Record<SlotId, SnapshotNode[]>>({ A: [], B: [] })
const pendingChaseParent = ref<SnapshotNode | null>(null)
const currentNode = ref<SnapshotNode | null>(null)

// ── History (session-only) ──
interface HistoryEntry {
  id: number
  slot: SlotId
  entity: string
  method: string
  key: string
  filter: string
  timestamp: string
  status: number | null
  data: unknown
  message: string | null
}
const history = ref<HistoryEntry[]>([])
let nextHistoryId = 1

async function send() {
  const slot = slots[sendingAs.value]
  if (!slot.token.trim() || !slot.host.trim() || !entityInput.value.trim()) return
  sending.value = true
  try {
    let parsedBody: Record<string, unknown> | undefined
    if (bodyText.value.trim()) {
      try {
        parsedBody = JSON.parse(bodyText.value)
      } catch {
        response.value = { status: null, data: null, message: 'Request body is not valid JSON' }
        return
      }
    }
    const res = await api.vmsSandbox.request({
      token: slot.token.trim(),
      entity: entityInput.value.trim(),
      host: slot.host.trim(),
      method: methodInput.value,
      key: keyInput.value.trim() || undefined,
      filter: filterInput.value.trim() || undefined,
      body: parsedBody,
    })
    response.value = res.data

    const entry: HistoryEntry = {
      id: nextHistoryId++, slot: sendingAs.value, entity: entityInput.value.trim(),
      method: methodInput.value, key: keyInput.value.trim(), filter: filterInput.value.trim(),
      timestamp: new Date().toISOString(), status: res.data.status, data: res.data.data, message: res.data.message,
    }
    history.value.unshift(entry)

    if (methodInput.value === 'GET' && keyInput.value.trim() && res.data.data && typeof res.data.data === 'object') {
      const node: SnapshotNode = { entity: entityInput.value.trim(), key: keyInput.value.trim(), data: res.data.data, children: [] }
      if (pendingChaseParent.value) pendingChaseParent.value.children.push(node)
      else snapshotTrees[sendingAs.value].push(node)
      pendingChaseParent.value = null
      currentNode.value = node
    } else {
      currentNode.value = null
    }
  } catch (e: any) {
    response.value = { status: null, data: null, message: e?.response?.data?.detail ?? 'Request failed' }
  } finally {
    sending.value = false
  }
}

// ── Auto-crawl ("detonate and observe" mode) ──
// Client-side only, deliberately — the chase heuristic (extractChaseTargets)
// already lives in exactly one place; a server-side crawler would need a
// second copy of it in Python, which could drift from this one. This loop
// just calls the same api.vmsSandbox.request() the manual Send button uses,
// on a bounded, concurrency-limited queue, instead of waiting for a click
// per hop.
const isCrawling = ref(false)
const crawlAbort = ref(false)
const maxDepth = ref(3)
const maxNodes = ref(30)
const crawlProgress = reactive({ fetched: 0, depth: 0 })
interface CrawlSummary { total: number; byEntity: Record<string, number>; errors: number; elapsedMs: number; stopped: boolean }
const crawlSummary = ref<CrawlSummary | null>(null)

// Only real {key,self} pointers (single or array-sourced) count — the
// weaker name-guess heuristic stays manual-click-only, see
// extractChaseTargets' own comment for why an unattended crawl shouldn't
// trust it.
const realPointerCount = computed(() =>
  extractChaseTargets(response.value?.data, { includeNameGuess: false }).length
)

interface CrawlQueueItem { entity: string; refKey: string | number; depth: number; parent: SnapshotNode | null }

async function autoCrawl() {
  if (isCrawling.value) return
  const slot = slots[sendingAs.value]
  if (!response.value?.data || !slot.token.trim() || !slot.host.trim()) return

  isCrawling.value = true
  crawlAbort.value = false
  crawlSummary.value = null
  crawlProgress.fetched = 0
  crawlProgress.depth = 0
  const startTime = Date.now()

  // Seed with the currently-displayed entity's real pointers — the crawl
  // expands outward from whatever's on screen, matching a manual chase's
  // own starting point. Nests new nodes under currentNode (the already-
  // displayed node) when one exists; falls back to new roots otherwise —
  // e.g. if the seed response came from a filter/list call rather than a
  // single-key GET, so no snapshot node exists for it yet.
  const seedNode = currentNode.value
  const visited = new Set<string>()
  const byEntity: Record<string, number> = {}
  let errors = 0
  let stopped = false

  const queue: CrawlQueueItem[] = []
  for (const t of extractChaseTargets(response.value.data, { includeNameGuess: false })) {
    const k = `${t.guessedEntity}:${t.refKey}`
    if (visited.has(k) || visited.size >= maxNodes.value) continue
    visited.add(k)
    queue.push({ entity: t.guessedEntity, refKey: t.refKey, depth: 1, parent: seedNode })
  }

  const CONCURRENCY = 3

  async function worker() {
    while (queue.length && !crawlAbort.value) {
      const item = queue.shift()
      if (!item) break
      crawlProgress.depth = Math.max(crawlProgress.depth, item.depth)

      const node: SnapshotNode = { entity: item.entity, key: String(item.refKey), data: null, children: [], status: 'pending' }
      if (item.parent) item.parent.children.push(node)
      else snapshotTrees[sendingAs.value].push(node)

      try {
        const res = await api.vmsSandbox.request({
          token: slot.token.trim(), entity: item.entity, host: slot.host.trim(),
          method: 'GET', key: String(item.refKey),
        })
        crawlProgress.fetched++

        if (res.data.status !== null && res.data.status >= 200 && res.data.status < 300 && res.data.data && typeof res.data.data === 'object') {
          node.data = res.data.data
          node.status = 'done'
          byEntity[item.entity] = (byEntity[item.entity] ?? 0) + 1

          history.value.unshift({
            id: nextHistoryId++, slot: sendingAs.value, entity: item.entity,
            method: 'GET', key: String(item.refKey), filter: '',
            timestamp: new Date().toISOString(), status: res.data.status, data: res.data.data, message: res.data.message,
          })

          if (item.depth < maxDepth.value) {
            for (const t of extractChaseTargets(res.data.data, { includeNameGuess: false })) {
              if (visited.size >= maxNodes.value) { stopped = true; break }
              const k = `${t.guessedEntity}:${t.refKey}`
              if (visited.has(k)) continue
              visited.add(k)
              queue.push({ entity: t.guessedEntity, refKey: t.refKey, depth: item.depth + 1, parent: node })
            }
          }
        } else {
          node.status = 'error'
          errors++
        }
      } catch {
        node.status = 'error'
        errors++
        crawlProgress.fetched++
      }
    }
  }

  await Promise.all(Array.from({ length: CONCURRENCY }, worker))

  if (crawlAbort.value && queue.length) stopped = true
  crawlSummary.value = { total: crawlProgress.fetched, byEntity, errors, elapsedMs: Date.now() - startTime, stopped }
  isCrawling.value = false
}

function prettyJson(v: unknown): string {
  return JSON.stringify(v, null, 2)
}
function historyLabel(h: HistoryEntry): string {
  return `${h.slot} · ${h.method} ${h.entity}${h.key ? '/' + h.key : ''} · ${formatTime(h.timestamp)}`
}
function formatTime(t: string): string {
  return new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// ── Compare / diff ──
const leftId = ref(0)
const rightId = ref(0)

interface DiffRow { path: string; type: 'added' | 'removed' | 'changed'; left: unknown; right: unknown }

function diffValues(a: unknown, b: unknown, path: string): DiffRow[] {
  if (a === b) return []
  const aIsObj = a !== null && typeof a === 'object'
  const bIsObj = b !== null && typeof b === 'object'
  if (!aIsObj || !bIsObj) {
    return [{ path: path || '(root)', type: 'changed', left: a, right: b }]
  }
  const aArr = Array.isArray(a), bArr = Array.isArray(b)
  if (aArr !== bArr) return [{ path: path || '(root)', type: 'changed', left: a, right: b }]

  const rows: DiffRow[] = []
  const keys = aArr
    ? Array.from({ length: Math.max((a as unknown[]).length, (b as unknown[]).length) }, (_, i) => String(i))
    : [...new Set([...Object.keys(a as object), ...Object.keys(b as object)])]

  for (const k of keys) {
    const rec = a as Record<string, unknown>
    const recB = b as Record<string, unknown>
    const p = path ? `${path}.${k}` : k
    const hasA = k in rec, hasB = k in recB
    if (!hasA) { rows.push({ path: p, type: 'added', left: undefined, right: recB[k] }); continue }
    if (!hasB) { rows.push({ path: p, type: 'removed', left: rec[k], right: undefined }); continue }
    rows.push(...diffValues(rec[k], recB[k], p))
  }
  return rows
}

const diffRows = computed<DiffRow[]>(() => {
  const left = history.value.find(h => h.id === leftId.value)
  const right = history.value.find(h => h.id === rightId.value)
  if (!left || !right) return []
  return diffValues(left.data, right.data, '')
})

const verdictNote = ref('')
</script>

<style scoped>
.vsb-slots { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 900px) { .vsb-slots { grid-template-columns: 1fr; } }
.vsb-card { padding: 15px 17px; }
.vsb-eyebrow { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .1em; color: var(--text3); margin-bottom: 10px; }
.vsb-token { font-family: 'SF Mono', monospace; font-size: 10.5px; resize: vertical; margin-bottom: 8px; }
.vsb-host { font-family: 'SF Mono', monospace; font-size: 10.5px; margin-bottom: 8px; }
.vsb-demo-check { display: flex; align-items: center; gap: 6px; font-size: 10.5px; color: var(--text3); cursor: pointer; }
.vsb-decoded { margin-top: 6px; font-size: 10.5px; color: var(--text3); font-variant-numeric: tabular-nums; }

.vsb-builder-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.vsb-body { font-family: 'SF Mono', monospace; font-size: 11px; margin-top: 8px; resize: vertical; }

.vsb-two-col { display: grid; grid-template-columns: 1.4fr 1fr; gap: 14px; align-items: start; }
@media (max-width: 950px) { .vsb-two-col { grid-template-columns: 1fr; } }

.vsb-chase-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.vsb-chase-row { font-size: 10.5px; color: var(--accent); cursor: pointer; padding: 3px 6px; background: var(--surface2); border-radius: 5px; }
.vsb-chase-row:hover { background: var(--surface3); }

.vsb-json { font-size: 10.5px; background: var(--surface2); border-radius: 6px; padding: 10px; overflow: auto; max-height: 320px; white-space: pre-wrap; }
.vsb-cap-hint { font-size: 11px; padding: 8px 10px; border-radius: 6px; margin-bottom: 8px; background: rgba(240, 160, 48, .08); color: var(--text2); }
.vsb-example-link { color: var(--accent); cursor: pointer; text-decoration: underline; }

.vsb-diff { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; max-height: 260px; overflow: auto; }
.vsb-diff-row { display: flex; gap: 10px; font-size: 10.5px; padding: 4px 8px; border-radius: 5px; font-family: 'SF Mono', monospace; }
.vsb-diff-path { color: var(--text2); font-weight: 700; flex-shrink: 0; min-width: 160px; }
.vsb-diff-vals { color: var(--text3); overflow-wrap: anywhere; }
.vsb-diff-added   { background: rgba(15, 186, 129, .08); }
.vsb-diff-removed { background: rgba(232, 68, 90, .08); }
.vsb-diff-changed { background: rgba(240, 160, 48, .08); }

.vsb-history-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-top: 1px dashed var(--border2); font-size: 11px; }
.vsb-history-row:first-child { border-top: none; }

.vsb-crawl-controls { display: flex; gap: 10px; align-items: center; }
.vsb-num { width: 42px; padding: 2px 5px; font-size: 10.5px; text-align: center; }
.vsb-crawl-status { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 10.5px; color: var(--text2); background: var(--surface2); border-radius: 6px; padding: 6px 9px; margin-top: 8px; }
.vsb-crawl-summary { background: var(--surface2); border-radius: 6px; padding: 8px 10px; margin-top: 8px; }
</style>
