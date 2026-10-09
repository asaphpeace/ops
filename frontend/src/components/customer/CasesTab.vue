<template>
  <div v-if="summaryLoading" class="info-bar">Loading live case counts from Jira…</div>
  <template v-else-if="summary">
    <div class="cp-kpis">
      <div class="sc" :class="summary.open_count ? 'warn' : 'good'"><div class="lbl">Open now</div><div class="val">{{ summary.open_count }}</div><div class="sub">oldest {{ summary.oldest_days }}d</div></div>
      <div class="sc"><div class="lbl">Logged · 12 months</div><div class="val">{{ summary.logged_months ?? '—' }}</div><div class="sub">{{ topPriority }}</div></div>
      <div class="sc" :class="summary.recurring_topics?.length ? 'warn' : ''"><div class="lbl">Recurring topics</div><div class="val">{{ summary.recurring_topics?.length ?? 0 }}</div><div class="sub">3+ cases on one Jira component</div></div>
      <div class="sc" :class="connectedDefects.length ? 'alert' : ''"><div class="lbl">Connected defects</div><div class="val">{{ techLoading ? '…' : connectedDefects.length }}</div><div class="sub">{{ exposedCount }} exposed, not yet reported</div></div>
    </div>
    <div v-if="summary.source !== 'jira_live'" class="info-bar cp-warn-text cp-gap-sm">⚠ Live Jira lookup unavailable — showing the local cache only, likely undercounted.</div>
    <div v-if="summary.volume_spike" class="info-bar cp-warn-text cp-gap-sm">
      📈 Volume spike — {{ summary.volume_spike.count }} cases in {{ summary.volume_spike.month }} vs. an average of {{ summary.volume_spike.prior_average }}/month before. Worth a check-in.
    </div>

    <div class="cp-grid">
      <!-- Open now (live from Jira — authoritative) -->
      <div class="tw">
        <div class="ttb"><span class="md-eyebrow" style="margin:0">Open now</span><span class="cp-muted">live from Jira</span></div>
        <div v-if="!summary.open_tickets.length" class="cp-muted cp-card">No open cases.</div>
        <div v-for="t in summary.open_tickets" :key="t.jira_ref" class="cp-case-row" @click="openCase(t.jira_ref)">
          <a class="jref" :href="jiraUrl(t.jira_ref)" target="_blank" rel="noopener" @click.stop>↗ {{ t.jira_ref }}</a>
          <span class="cp-case-title">{{ t.title }}</span>
          <span :class="t.priority === 'High' ? 'priority-h' : t.priority === 'Low' ? 'priority-l' : 'priority-m'">{{ t.priority }}</span>
          <span class="cp-muted">{{ t.days_open }}d</span>
        </div>
      </div>

      <!-- Patterns -->
      <div class="tw cp-card">
        <template v-if="summary.monthly_counts?.length">
          <div class="md-eyebrow">Cases per month</div>
          <div class="cp-bars">
            <div v-for="m in summary.monthly_counts" :key="m.month" class="cp-bar-wrap" :title="`${m.month}: ${m.count} case${m.count === 1 ? '' : 's'}`">
              <div class="cp-bar" :style="{ height: barHeight(m.count) }"></div>
              <div class="cp-bar-lbl">{{ m.month.slice(5) }}</div>
            </div>
          </div>
        </template>
        <template v-if="summary.top_topics?.length">
          <div class="md-eyebrow cp-gap">Topics · Jira components, last 12 months</div>
          <div v-for="t in summary.top_topics" :key="t.topic" class="cp-topic">
            <span>{{ t.topic }}</span>
            <span v-if="isRecurring(t.topic)" class="cp-pill purple">recurring</span>
            <span class="cp-muted cp-push">{{ t.count }}</span>
          </div>
          <div v-if="summary.recurring_topics?.length" class="cp-muted cp-gap-sm">Recurring topics are a real, specific training/engagement opportunity.</div>
        </template>
        <template v-if="connectedDefects.length">
          <div class="md-eyebrow cp-gap">Connected defects</div>
          <div class="cp-chips">
            <span v-for="d in connectedDefects" :key="d.vms_ref" class="cp-chip" :class="d.reported ? '' : 'warn'" :title="d.fix_version ? `Fixed in ${d.fix_version}` : 'No fix version yet'">
              <b>{{ d.vms_ref }}</b><span>{{ d.reported ? 'reported' : 'exposed' }}{{ d.fix_version ? ` · fix ${d.fix_version}` : '' }}</span>
            </span>
          </div>
        </template>
      </div>
    </div>
  </template>

  <!-- History: every case mapped to this customer in Sedna Ops -->
  <div class="tw cp-gap">
    <div class="ttb">
      <span class="md-eyebrow" style="margin:0">Case history</span>
      <span class="cp-muted">mapped in Sedna Ops · {{ cases.length }}</span>
      <input class="inp cp-push" style="width:200px" v-model="filter" placeholder="Filter by ref or title…">
    </div>
    <div v-if="shown.length" class="cp-scroll-x">
    <table>
      <thead><tr><th>Ref</th><th>Title</th><th>Priority</th><th>Status</th><th>Assignee</th><th>Opened</th><th>Resolved</th></tr></thead>
      <tbody>
        <tr v-for="c in shown" :key="c.id" class="cp-click" @click="openCase(c.jira_ref)">
          <td><span class="jref">{{ c.jira_ref }}</span></td>
          <td class="cp-title-cell">{{ c.title }}</td>
          <td><span :class="c.priority === 'High' ? 'priority-h' : c.priority === 'Low' ? 'priority-l' : 'priority-m'">{{ c.priority }}</span></td>
          <td>{{ c.status }}</td>
          <td>{{ c.assigned_to || '—' }}</td>
          <td class="cp-nowrap">{{ fmtDate(c.created_at) }}</td>
          <td class="cp-nowrap">{{ c.resolved_at ? fmtDate(c.resolved_at) : '—' }}</td>
        </tr>
      </tbody>
    </table>
    </div>
    <div v-else class="cp-muted cp-card">No cases{{ filter ? ' match' : '' }}.</div>
  </div>
</template>

<script setup lang="ts">
// What support problems do they have, and is there a pattern? The live
// Jira summary is authoritative for "open now" (the local table is a
// mapped subset, confirmed ~7x undercounted); the history table below is
// that local subset, for browsing.
import { ref, computed, watch } from 'vue'
import { api, jiraUrl, type Customer, type Case, type CustomerCaseSummary, type CustomerTechnical } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { fmtDate } from './profileUtils'

const props = defineProps<{ customer: Customer; tech: CustomerTechnical | null; techLoading: boolean }>()
const { openCase } = useCaseDrill()

const summary = ref<CustomerCaseSummary | null>(null)
const summaryLoading = ref(true)
const cases = ref<Case[]>([])
const filter = ref('')

const connectedDefects = computed(() => props.tech?.connected_defects ?? [])
const exposedCount = computed(() => connectedDefects.value.filter(d => !d.reported).length)
const topPriority = computed(() => {
  const p = summary.value?.by_priority ?? {}
  return Object.entries(p).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${v} ${k}`).slice(0, 3).join(' · ')
})
function isRecurring(topic: string) {
  return !!summary.value?.recurring_topics?.some(r => r.topic === topic)
}
function barHeight(count: number) {
  const max = Math.max(1, ...(summary.value?.monthly_counts.map(m => m.count) ?? [1]))
  return `${Math.max(6, Math.round((count / max) * 100))}%`
}
const shown = computed(() => {
  const q = filter.value.trim().toLowerCase()
  const list = q ? cases.value.filter(c => c.jira_ref.toLowerCase().includes(q) || c.title.toLowerCase().includes(q)) : cases.value
  return [...list].sort((a, b) => Number(b.status !== 'Closed') - Number(a.status !== 'Closed') || new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
})

async function load() {
  const id = props.customer.id
  summaryLoading.value = true
  summary.value = null
  // Live Jira scan can be slow — don't block the history table on it.
  api.customers.caseSummary(id)
    .then(r => { summary.value = r.data })
    .catch(() => { summary.value = null })
    .finally(() => { summaryLoading.value = false })
  cases.value = (await api.cases.list({ customer_id: id })).data
}
watch(() => props.customer.id, load, { immediate: true })
</script>
