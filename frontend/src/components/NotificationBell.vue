<template>
  <div class="bell-wrap">
    <button class="bell-btn" @click="toggleOpen" :title="notices.length ? `${notices.length} item(s) need attention` : 'Nothing needs attention'">
      🔔
      <span v-if="newCount > 0" class="bell-badge">{{ newCount > 9 ? '9+' : newCount }}</span>
    </button>

    <template v-if="open">
      <div class="bell-backdrop" @click="open = false"></div>
      <div class="bell-dropdown">
        <div class="bell-head">
          <span>Notices <span class="bell-count">{{ notices.length }}</span></span>
          <div class="bell-scope-toggle">
            <button type="button" :class="{ active: bellScope === 'me' }" @click.stop="setBellScope('me')">Me</button>
            <button type="button" :class="{ active: bellScope === 'team' }" @click.stop="setBellScope('team')">Whole Team</button>
          </div>
        </div>
        <div v-if="!notices.length" class="bell-empty">Nothing needs attention right now.</div>
        <div v-else class="bell-list">
          <div v-for="n in notices" :key="n.key" class="bell-item" :class="n.severity" @click="goTo(n)">
            <span class="bell-item-type">{{ n.type }}</span>
            <span class="bell-item-text">{{ n.text }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// Global "push" surface for the Queue Supervisor's real checks — that page
// is "pull" (open My Desk to see state); this is visible from anywhere.
// Reuses the exact same GET /desk/briefing data, no new backend endpoint.
// SLA Breach + Hypercare are flagged critical (the two genuinely
// time-sensitive signals); everything else Queue Supervisor tracks still
// shows here too, just styled as a regular notice, not alarming.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, type DeskBriefing } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { YOU } from '@/config/team'

const { openCase } = useCaseDrill()
const { openCustomer } = useCustomerDrill()

// Own toggle, independent of Queue Supervisor's — the bell defaults to
// "me" since a whole-team notice list (300+ real items) is too noisy for
// a badge you glance at constantly; Queue Supervisor's own page-level
// toggle stays whole-team by default for the overview use case.
const SCOPE_KEY = 'so_bell_scope'
const bellScope = ref<'me' | 'team'>((localStorage.getItem(SCOPE_KEY) as 'me' | 'team') || 'me')

interface Notice {
  key: string
  type: string
  severity: 'critical' | 'notice'
  text: string
  jira_ref?: string | null
  customer_id?: number | null
}

const briefing = ref<DeskBriefing | null>(null)
const open = ref(false)
const SEEN_KEY = 'so_bell_seen'

function loadSeen(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) ?? '[]'))
  } catch {
    return new Set()
  }
}
function saveSeen(keys: Set<string>) {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...keys]))
  } catch { /* private window / storage disabled — badge just won't persist across reloads */ }
}
const seenKeys = ref<Set<string>>(loadSeen())

function buildNotices(b: DeskBriefing, scope: 'me' | 'team'): Notice[] {
  const f = b.flags
  const notices: Notice[] = []
  // The bell is now a "what's new/urgent right now" feed, not a mirror of
  // every ongoing state Queue Supervisor already tracks — that's what was
  // driving 62 real items in "Me" scope. Ticket-level checks that are
  // inherently multi-day thresholds (Stale = 14d+, Chase Needed = 5d+,
  // Blocked Upgrade/Renewal/Stalled Migration/Overdue Decommission/
  // Bug-Fix-Upgrade-Overdue = ongoing account facts with no honest "this
  // happened today" reading) were dropped from the bell entirely — they
  // still live in full on Queue Supervisor, which is exactly the "everything
  // currently outstanding" view. SLA Breach is kept but limited to tickets
  // that are genuinely new (days_open <= 1) — a fresh ticket already
  // breaching its Initial Response SLA is a real "just happened" signal,
  // unlike an old ticket that's been breaching for weeks. Hypercare is the
  // one deliberate exception to the day-limit — it's rare, always critical,
  // and already treated as an always-surface flag everywhere else in the
  // app (My Desk's Needs-a-Decision sorts it first regardless of age).
  const mine = <T extends { assignee_name: string | null }>(list: T[]) => scope === 'me' ? list.filter(t => t.assignee_name === YOU) : list
  const recentSlaBreach = f.sla_breach_tickets.filter(t => t.days_open != null && t.days_open <= 1)
  for (const t of mine(recentSlaBreach)) {
    notices.push({ key: `sla_breach:${t.jira_ref}`, type: 'SLA Breach', severity: 'critical', jira_ref: t.jira_ref, text: `${t.jira_ref} — ${t.customer_name ?? 'Unknown'} (${t.days_open}d open)` })
  }
  for (const c of f.hypercare_customers) {
    notices.push({ key: `hypercare:${c.id}`, type: 'Hypercare', severity: 'critical', customer_id: c.id, text: `${c.name} is in hypercare` })
  }
  // Being tagged — real Case.last_mention_at, already limited to the last
  // 24h server-side. Filtered by who was mentioned, not who the ticket is
  // assigned to (a different person can be tagged on someone else's case).
  const taggedMe = (list: typeof f.mentioned_tickets) => scope === 'me' ? list.filter(t => t.mentioned_name === YOU) : list
  for (const t of taggedMe(f.mentioned_tickets)) {
    notices.push({ key: `mentioned:${t.jira_ref}`, type: 'Tagged', severity: 'critical', jira_ref: t.jira_ref, text: `${t.mentioned_name} tagged on ${t.jira_ref} — ${t.customer_name ?? 'Unknown'}` })
  }
  // Recent comments — sourced from the locally-cached CaseComment table
  // (populated when a case's Jira Activity tab has been opened at least
  // once), also already limited to the last 24h server-side. Coverage
  // grows as cases get opened in the normal course of support work, but
  // isn't a complete global comment feed on day one — stated here, not
  // silently presented as more complete than it is.
  for (const c of mine(f.recent_comments)) {
    notices.push({ key: `comment:${c.jira_ref}:${c.created}`, type: 'Comment', severity: 'notice', jira_ref: c.jira_ref, text: `${c.author} commented on ${c.jira_ref} — ${c.customer_name ?? 'Unknown'}` })
  }
  // Critical first, otherwise stable insertion order.
  return notices.sort((a, b2) => (a.severity === b2.severity ? 0 : a.severity === 'critical' ? -1 : 1))
}

const notices = computed(() => (briefing.value ? buildNotices(briefing.value, bellScope.value) : []))
const newCount = computed(() => notices.value.filter(n => !seenKeys.value.has(n.key)).length)

function toggleOpen() {
  open.value = !open.value
  if (open.value) {
    const next = new Set(seenKeys.value)
    for (const n of notices.value) next.add(n.key)
    seenKeys.value = next
    saveSeen(next)
  }
}

function setBellScope(scope: 'me' | 'team') {
  bellScope.value = scope
  localStorage.setItem(SCOPE_KEY, scope)
  // No re-fetch — `notices` is a computed over the already-fetched
  // team-wide briefing, so this is instant.
}

function goTo(n: Notice) {
  if (n.jira_ref) openCase(n.jira_ref)
  else if (n.customer_id != null) openCustomer(n.customer_id, 'overview')
  open.value = false
}

async function fetchBriefing() {
  try {
    const res = await api.desk.briefing(undefined, 'team')
    briefing.value = res.data
  } catch { /* keep showing last-known state rather than clearing the bell */ }
}

let intervalId: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  fetchBriefing()
  // 5 min — matches the Jira poll cadence backing these checks; polling
  // faster wouldn't surface anything newer.
  intervalId = setInterval(fetchBriefing, 5 * 60 * 1000)
})
onUnmounted(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>

<style scoped>
.bell-wrap { position: relative; }
.bell-btn {
  position: relative;
  background: var(--surface2); border: 1px solid var(--border2); color: var(--text2);
  width: 30px; height: 30px; border-radius: 8px; cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
}
.bell-btn:hover { background: var(--surface3); color: var(--text); }
.bell-badge {
  position: absolute; top: -4px; right: -4px;
  background: var(--red); color: white; font-size: 9px; font-weight: 800;
  min-width: 15px; height: 15px; border-radius: 999px;
  display: flex; align-items: center; justify-content: center; padding: 0 3px;
}
.bell-backdrop { position: fixed; inset: 0; z-index: 349; }
.bell-dropdown {
  position: absolute; top: 38px; right: 0; z-index: 350;
  width: 340px; max-height: 420px; overflow-y: auto;
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, .4);
}
.bell-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 12px; border-bottom: 1px solid var(--border);
  font-size: 11px; font-weight: 800; color: var(--text);
}
.bell-count { color: var(--text3); font-weight: 600; margin-left: 4px; }
.bell-scope-toggle { display: flex; gap: 3px; }
.bell-scope-toggle button {
  background: var(--surface2); border: 1px solid var(--border2); color: var(--text3);
  font-size: 9px; font-weight: 700; padding: 2px 7px; border-radius: 5px; cursor: pointer;
}
.bell-scope-toggle button.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }
.bell-empty { padding: 24px 12px; text-align: center; font-size: 11px; color: var(--text3); }
.bell-list { display: flex; flex-direction: column; }
.bell-item {
  display: flex; flex-direction: column; gap: 2px;
  padding: 8px 12px; border-bottom: 1px solid var(--border); cursor: pointer;
}
.bell-item:last-child { border-bottom: none; }
.bell-item:hover { background: var(--surface2); }
.bell-item-type { font-size: 8.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; }
.bell-item.critical .bell-item-type { color: var(--red); }
.bell-item.notice .bell-item-type { color: var(--amber); }
.bell-item-text { font-size: 11px; color: var(--text2); }
</style>
