<template>
  <div class="qt">
    <div class="qt-filters">
      <input class="inp" style="width:220px" placeholder="Search ticket, customer, subject..." v-model="search">
      <select class="sel" v-model="filterStatus">
        <option value="">All statuses</option>
        <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
      </select>
      <FilterPills :options="priorityOptions" all-label="All priorities" v-model="filterPriority" />
      <select class="sel" v-model="filterAgent">
        <option value="">All agents</option>
        <option v-for="a in agentOptions" :key="a" :value="a">{{ a }}</option>
      </select>
    </div>

    <div class="qt-count">{{ sortedRows.length }} of {{ rows.length }} tickets</div>

    <div class="qt-table-wrap">
      <table class="qt-table">
        <thead>
          <tr>
            <th class="qt-th-sort" @click="toggleSort('jira_ref')">Ticket<span class="qt-sort-arrow">{{ sortArrow('jira_ref') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('title')">Subject<span class="qt-sort-arrow">{{ sortArrow('title') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('customer_name')">Customer<span class="qt-sort-arrow">{{ sortArrow('customer_name') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('priority')">Priority<span class="qt-sort-arrow">{{ sortArrow('priority') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('status')">Status<span class="qt-sort-arrow">{{ sortArrow('status') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('assigned_to')">Agent<span class="qt-sort-arrow">{{ sortArrow('assigned_to') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('created')">Logged<span class="qt-sort-arrow">{{ sortArrow('created') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('days_open')">Age<span class="qt-sort-arrow">{{ sortArrow('days_open') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('last_reply_at')">Last Update<span class="qt-sort-arrow">{{ sortArrow('last_reply_at') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('sla')">SLA (First Response)<span class="qt-sort-arrow">{{ sortArrow('sla') }}</span></th>
            <th class="qt-th-sort" @click="toggleSort('lane_label')">Lane<span class="qt-sort-arrow">{{ sortArrow('lane_label') }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!sortedRows.length"><td colspan="11" class="qt-empty">No tickets match these filters.</td></tr>
          <tr v-for="r in sortedRows" :key="r.jira_ref" @click="openCase(r.jira_ref)">
            <td><span class="jref">{{ r.jira_ref }}</span></td>
            <td class="qt-subject">{{ r.title }}</td>
            <td>
              <span class="qt-customer-cell">
                <span v-if="r.customer_id" class="qt-customer" @click.stop="goToCustomer(r.customer_id!, 'overview')">{{ r.customer_name ?? 'Unknown' }}</span>
                <span v-else class="qt-customer-plain">{{ r.customer_name ?? 'Unknown' }}</span>
                <span v-if="r.customer_tier" class="tier-badge" :class="tierClass(r.customer_tier)">{{ r.customer_tier }}</span>
              </span>
            </td>
            <td><span :class="priorityClass(r.priority)">{{ r.priority }}</span></td>
            <td class="qt-status">{{ r.raw_status }}</td>
            <td class="qt-agent">{{ r.assigned_to ?? 'Unassigned' }}</td>
            <td class="qt-logged">{{ formatLogged(r.created) }}</td>
            <td class="qt-age">{{ r.days_open }}d</td>
            <td class="qt-update">
              <span v-if="r.last_reply_at" :class="['qt-update-who', updateWhoClass(r.last_reply_by)]">{{ updateWhoLabel(r.last_reply_by) }}</span>
              <span v-if="r.last_reply_at" class="qt-update-ago">{{ formatTimeSince(r.last_reply_at) }}</span>
              <span v-else class="qt-update-none">No replies yet</span>
            </td>
            <td><span class="qt-sla" :class="slaClass(r)">{{ slaLabel(r) }}</span></td>
            <td><span class="qt-lane" :class="'ld-' + r.lane">{{ r.lane_label }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { QueueRow, QueueSla } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { YOU } from '@/config/team'

const props = defineProps<{ rows: QueueRow[]; initialStatus?: string; initialAgent?: string }>()
const { openCase } = useCaseDrill()
const { openCustomer: goToCustomer } = useCustomerDrill()

const search = ref('')
// Seeded from the caller (My Desk opens this pre-filtered to "my own
// Waiting for support tickets" — the actual working queue, not a blank
// browse-everything table) but stays a normal, freely-changeable filter
// from here — nothing re-applies these once the user clears them.
const filterStatus = ref(props.initialStatus ?? '')
const filterPriority = ref('')
const filterAgent = ref(props.initialAgent ?? '')

type SortKey = 'jira_ref' | 'title' | 'customer_name' | 'priority' | 'status' | 'assigned_to' |
  'created' | 'days_open' | 'last_reply_at' | 'sla' | 'lane_label'

const sortKey = ref<SortKey>('sla')
const sortDir = ref<'asc' | 'desc'>('asc')

// Each column's sensible first-click direction — e.g. clicking "Age" should
// show the oldest ticket first, not the newest, without a second click.
const DEFAULT_DIR: Record<SortKey, 'asc' | 'desc'> = {
  jira_ref: 'asc', title: 'asc', customer_name: 'asc', status: 'asc',
  assigned_to: 'asc', lane_label: 'asc',
  priority: 'desc',       // High first
  created: 'desc',        // newest logged first
  days_open: 'desc',      // oldest ticket first
  last_reply_at: 'asc',   // stalest (or never-replied) first
  sla: 'asc',             // most urgent first (matches the old default)
}

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = DEFAULT_DIR[key]
  }
}

function sortArrow(key: SortKey): string {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? '▲' : '▼'
}

const priorityOptions = [
  { value: 'High', label: 'High' },
  { value: 'Medium', label: 'Medium' },
  { value: 'Low', label: 'Low' },
]

// The real, un-collapsed Jira status (e.g. "Defect / Enhancement submitted",
// "Waiting for support", "Waiting for customer") — not the 3-bucket
// Active/Awaiting Customer/Closed status every open row would otherwise
// share, which made defect tickets indistinguishable from plain ones.
const statusOptions = computed(() => {
  const set = new Set(props.rows.map(r => r.raw_status))
  return [...set].sort()
})
const agentOptions = computed(() => {
  const set = new Set(props.rows.map(r => r.assigned_to).filter((a): a is string => !!a))
  return [...set].sort()
})

// SLA urgency for sorting: breached-and-not-completed first, then by how
// little time remains — the actual "what needs attention right now"
// ordering, not just a plain field sort.
function slaUrgency(r: QueueRow): number {
  const sla = r.sla
  if (!sla || sla.completed) return Number.POSITIVE_INFINITY
  if (sla.remaining_minutes == null) return Number.POSITIVE_INFINITY
  return sla.remaining_minutes // negative (already breached) sorts first naturally
}

const PRIORITY_RANK: Record<string, number> = { High: 3, Medium: 2, Low: 1 }
function priorityRank(p: string): number {
  return PRIORITY_RANK[p] ?? 0
}

// A ticket that's never had a reply is the most neglected, not "unknown" —
// sorts as older than any real timestamp so it surfaces first under the
// "stalest first" default direction.
function lastReplyRank(r: QueueRow): number {
  return r.last_reply_at ? new Date(r.last_reply_at).getTime() : -Infinity
}

const filteredRows = computed(() => {
  const q = search.value.trim().toLowerCase()
  return props.rows.filter(r => {
    if (filterStatus.value && r.raw_status !== filterStatus.value) return false
    if (filterPriority.value && r.priority !== filterPriority.value) return false
    if (filterAgent.value && r.assigned_to !== filterAgent.value) return false
    if (q) {
      const hay = `${r.jira_ref} ${r.customer_name ?? ''} ${r.title}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

function compareRows(a: QueueRow, b: QueueRow): number {
  let cmp: number
  switch (sortKey.value) {
    case 'jira_ref': cmp = a.jira_ref.localeCompare(b.jira_ref); break
    case 'title': cmp = a.title.localeCompare(b.title); break
    case 'customer_name': cmp = (a.customer_name ?? '').localeCompare(b.customer_name ?? ''); break
    case 'priority': cmp = priorityRank(a.priority) - priorityRank(b.priority); break
    case 'status': cmp = a.raw_status.localeCompare(b.raw_status); break
    case 'assigned_to': cmp = (a.assigned_to ?? 'Unassigned').localeCompare(b.assigned_to ?? 'Unassigned'); break
    case 'created': cmp = (a.created ?? '').localeCompare(b.created ?? ''); break
    case 'days_open': cmp = a.days_open - b.days_open; break
    case 'last_reply_at': cmp = lastReplyRank(a) - lastReplyRank(b); break
    case 'lane_label': cmp = a.lane_label.localeCompare(b.lane_label); break
    case 'sla':
    default: cmp = slaUrgency(a) - slaUrgency(b)
  }
  return sortDir.value === 'asc' ? cmp : -cmp
}

const sortedRows = computed(() => [...filteredRows.value].sort(compareRows))

function tierClass(t: string) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}
function priorityClass(p: string) {
  return p === 'High' ? 'priority-h' : p === 'Low' ? 'priority-l' : 'priority-m'
}

function formatLogged(created: string | null): string {
  if (!created) return '—'
  const d = new Date(created)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

// last_reply_by is "customer", a real team display name (YOU or a
// teammate), or null — label/color it so the three states read at a
// glance, matching the customer's own phrasing ("since I or the customer
// last replied").
function updateWhoLabel(who: string | null): string {
  if (!who) return ''
  if (who === 'customer') return 'Customer'
  return who === YOU ? 'You' : who.split(' ')[0]
}
function updateWhoClass(who: string | null): string {
  if (who === 'customer') return 'qt-update-customer'
  if (who === YOU) return 'qt-update-you'
  return 'qt-update-team'
}

function formatTimeSince(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const mins = Math.round(ms / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

function formatMinutes(mins: number): string {
  const abs = Math.abs(Math.round(mins))
  if (abs >= 1440) return `${Math.floor(abs / 1440)}d ${Math.floor((abs % 1440) / 60)}h`
  if (abs >= 60) return `${Math.floor(abs / 60)}h ${abs % 60}m`
  return `${abs}m`
}

function slaLabel(r: QueueRow): string {
  const sla = r.sla
  if (!sla) return '—'
  if (!sla.completed) {
    if (sla.remaining_minutes == null) return sla.breached ? 'Breached' : 'Ticking'
    return sla.remaining_minutes < 0 || sla.breached
      ? `Breached ${formatMinutes(sla.remaining_minutes)} ago`
      : `${formatMinutes(sla.remaining_minutes)} left`
  }
  return sla.breached ? 'Responded late' : 'Responded — within SLA'
}

function slaClass(r: QueueRow): string {
  const sla = r.sla
  if (!sla) return 'qt-sla-none'
  if (!sla.completed) return sla.breached || (sla.remaining_minutes ?? 0) < 0 ? 'qt-sla-breached' : 'qt-sla-ok'
  return sla.breached ? 'qt-sla-breached' : 'qt-sla-done'
}
</script>

<style scoped>
.qt-filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 8px; }
.qt-count { font-size: 10px; color: var(--text3); margin-bottom: 8px; }

.qt-table-wrap { overflow-x: auto; max-height: 520px; overflow-y: auto; border: 1px solid var(--border); border-radius: 8px; }
.qt-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.qt-table thead th {
  position: sticky; top: 0; background: var(--surface2); text-align: left; padding: 7px 9px;
  font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; color: var(--text3);
  border-bottom: 1px solid var(--border); white-space: nowrap;
}
.qt-th-sort { cursor: pointer; user-select: none; }
.qt-th-sort:hover { color: var(--text2); }
.qt-sort-arrow { display: inline-block; margin-left: 4px; font-size: 8px; color: var(--accent); }
.qt-table tbody tr { border-bottom: 1px solid var(--border2); cursor: pointer; transition: background .12s; }
.qt-table tbody tr:hover { background: var(--surface2); }
.qt-table td { padding: 7px 9px; vertical-align: middle; white-space: nowrap; }
.qt-empty { text-align: center; color: var(--text3); padding: 20px !important; white-space: normal; }

.qt-subject { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap !important; color: var(--text2); }
.qt-customer-cell { display: inline-flex; align-items: center; gap: 5px; }
.qt-customer { color: var(--accent); cursor: pointer; }
.qt-customer:hover { text-decoration: underline; }
.qt-customer-plain { color: var(--text2); }
.qt-status { color: var(--text2); }
.qt-agent { color: var(--text3); }
.qt-logged, .qt-age { color: var(--text3); font-variant-numeric: tabular-nums; }

.qt-update { font-size: 10.5px; }
.qt-update-who { font-weight: 700; margin-right: 5px; }
.qt-update-customer { color: var(--amber); }
.qt-update-you { color: var(--accent); }
.qt-update-team { color: var(--text2); }
.qt-update-ago { color: var(--text3); font-variant-numeric: tabular-nums; }
.qt-update-none { color: var(--text3); font-style: italic; }

.qt-sla { font-size: 9.5px; font-weight: 700; padding: 2px 7px; border-radius: 4px; white-space: nowrap; }
.qt-sla-ok { background: var(--green-dim); color: var(--green); }
.qt-sla-breached { background: var(--red-dim); color: var(--red); }
.qt-sla-done { background: var(--surface3); color: var(--text3); }
.qt-sla-none { color: var(--text3); }

.qt-lane { font-size: 9.5px; font-weight: 600; padding: 2px 7px; border-radius: 4px; background: var(--surface3); color: var(--text2); white-space: nowrap; }
.qt-lane.ld-escalated { background: var(--red-dim); color: var(--red); }
.qt-lane.ld-unassigned { background: var(--amber-dim); color: var(--amber); }
.qt-lane.ld-customer { color: var(--text3); }
</style>
