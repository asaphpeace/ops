<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Support Signals</h2>
        <p>Analytical · nothing here needs an action today</p>
      </div>
    </div>

    <div v-if="loading" class="info-bar">Loading signals…</div>
    <div v-if="error" class="alert-bar">⚠ {{ error }}</div>

    <template v-if="aging && volume && exchanges">
      <div class="tw" style="padding:15px 17px;margin-bottom:16px">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:11px">
          Aging Buckets · {{ aging.over_90_days }} of {{ aging.total_open }} tickets over 90 days
        </div>
        <AgingBars :buckets="aging.buckets" />
      </div>

      <div class="tw" style="padding:15px 17px;margin-bottom:16px" v-if="resolved">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:11px">
          Resolved Tickets · last {{ resolved.window_days }} days · not just the open queue
        </div>
        <div class="ss-resolved-kpis">
          <div class="ss-kpi"><div class="ss-kpi-val">{{ resolved.resolved_this_week }}</div><div class="ss-kpi-lbl">Resolved this week</div></div>
          <div class="ss-kpi"><div class="ss-kpi-val">{{ resolved.resolved_this_month }}</div><div class="ss-kpi-lbl">Resolved this month</div></div>
          <div class="ss-kpi"><div class="ss-kpi-val">{{ resolved.total_resolved_90d }}</div><div class="ss-kpi-lbl">Total, 90 days</div></div>
          <div class="ss-kpi"><div class="ss-kpi-val">{{ resolved.ttr_median_hours ?? '—' }}<span v-if="resolved.ttr_median_hours" style="font-size:11px">h</span></div><div class="ss-kpi-lbl">Median time to resolve</div></div>
        </div>
        <div class="ss-weektrend">
          <div v-for="w in resolved.weekly_trend" :key="w.week_ending" class="ss-weekbar-col" :title="w.week_ending + ' · ' + w.count + ' resolved'">
            <div class="ss-weekbar" :style="{ height: barHeight(w.count) + 'px' }"></div>
          </div>
        </div>
        <div v-if="resolved.top_resolved_accounts.length" class="ss-top-resolved">
          <span class="ss-top-resolved-lbl">Most resolved for:</span>
          <span v-for="a in resolved.top_resolved_accounts.slice(0, 6)" :key="a.customer_name" class="ss-top-resolved-chip">
            {{ a.customer_name }} <b>{{ a.count }}</b>
          </span>
        </div>
      </div>

      <div class="tw" style="padding:15px 17px;margin-bottom:16px">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:11px">
          Volume by Account · current open vs each account's own 4-week baseline
        </div>
        <table>
          <thead>
            <tr><th>Customer</th><th>Open</th><th>Baseline</th><th>vs baseline</th><th></th><th></th><th></th></tr>
          </thead>
          <tbody>
            <template v-for="a in volume.accounts" :key="a.customer_id">
              <tr>
                <td class="td-name">{{ a.customer_name }}</td>
                <td class="vm">{{ a.open_count }}</td>
                <td class="vm">{{ a.baseline ?? '—' }}</td>
                <td class="vm">{{ a.multiplier ? '×' + a.multiplier : '—' }}</td>
                <td><span class="flag-pill" :class="labelClass(a.label)">{{ a.label }}</span></td>
                <td>
                  <button class="btn btn-g btn-sm" :disabled="drilling.has(a.customer_id)" @click="toggleDrill(a.customer_id)">
                    {{ drillOpen === a.customer_id ? '▾ tickets' : '▸ tickets' }}
                  </button>
                </td>
                <td>
                  <button class="btn btn-g btn-sm" :disabled="summarizing.has(a.customer_id)" @click="onCustomerSummaryClick(a)">
                    {{ summarizing.has(a.customer_id) ? 'Generating…' : (customerSummaries[a.customer_id]?.summary ? '✦ View Summary' : '✦ Summarize') }}
                  </button>
                </td>
              </tr>
              <tr v-if="drillOpen === a.customer_id">
                <td colspan="7" class="ss-drill-cell">
                  <div v-if="drilling.has(a.customer_id)" class="sub" style="color:var(--text3)">Loading tickets…</div>
                  <template v-else-if="drillData[a.customer_id]">
                    <div v-if="!drillData[a.customer_id]!.open_tickets.length" class="sub" style="color:var(--text3)">No open tickets.</div>
                    <div v-for="t in drillData[a.customer_id]!.open_tickets" :key="t.jira_ref" class="ss-drill-row" @click="openCase(t.jira_ref)">
                      <a class="jref" :href="jiraUrl(t.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>{{ t.jira_ref }}</a>
                      <span class="ss-drill-title">{{ t.title }}</span>
                      <span :class="t.priority === 'High' ? 'priority-h' : t.priority === 'Low' ? 'priority-l' : 'priority-m'">{{ t.priority }}</span>
                      <span class="ss-drill-days">{{ t.days_open }}d open</span>
                    </div>
                  </template>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div class="tw" style="padding:15px 17px;margin-bottom:16px">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:11px">
          Cases Going Back and Forth · more than {{ exchanges.threshold }} replies
        </div>
        <div v-if="!exchanges.cases.length" class="sub" style="font-size:11px;color:var(--text3)">
          Nothing crossing the exchange threshold right now.
        </div>
        <div v-for="c in exchanges.cases" :key="c.jira_ref" class="jr jr-click" @click="openCase(c.jira_ref)">
          <a class="jref" :href="jiraUrl(c.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>{{ c.jira_ref }}</a>
          <span class="jtitle">{{ c.customer_name }} · {{ c.title }}</span>
          <span class="jst">{{ c.comment_count }} replies</span>
        </div>
      </div>

      <!-- BUG / DEFECT INTELLIGENCE -->
      <div class="tw" style="padding:15px 17px">
        <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:11px">
          Bug/Defect Intelligence <span style="text-transform:none;font-weight:600;color:var(--text2)">· real DSD ↔ VMS linkage, DSD severity stays authoritative over VMS priority</span>
        </div>
        <div v-if="!bugs.length" class="sub" style="font-size:11px;color:var(--text3)">No linked VMS bugs yet.</div>
        <div v-for="bug in bugs" :key="bug.jira_ref" class="ss-bug-card">
          <div class="ss-bug-head" @click="openBug(bug.jira_ref)">
            <span class="jref">{{ bug.jira_ref }}</span>
            <span class="ss-bug-status" :class="statusClass(bug.status)">{{ bug.status }}</span>
            <span v-if="bug.fix_version" class="flag-pill" style="background:var(--green-dim);color:var(--green)">fix {{ bug.fix_version }}</span>
            <span v-else class="sub" style="font-size:9px;color:var(--text3)">no fix version yet</span>
            <span v-if="bug.sprint_name" class="sub" style="font-size:9px;color:var(--text3)">🏃 {{ bug.sprint_name }}</span>
            <span v-if="bug.assignee" class="sub" style="font-size:9px;color:var(--text3)">{{ bug.assignee }}</span>
            <button class="btn btn-g btn-sm" style="margin-left:auto" :disabled="summarizingBug.has(bug.jira_ref)" @click.stop="onBugSummaryClick(bug)">
              {{ summarizingBug.has(bug.jira_ref) ? 'Generating…' : (bugHasSummary(bug) ? '✦ View Summary' : '✦ Summarize') }}
            </button>
          </div>
          <div class="ss-bug-customers">
            Affects: <b>{{ bug.affected_customers.join(', ') || 'Unknown' }}</b>
            <span class="sub" style="color:var(--text3)"> · {{ bug.linked_cases.length }} linked ticket{{ bug.linked_cases.length !== 1 ? 's' : '' }}</span>
          </div>
          <div v-if="bug.labels.length" style="display:flex;gap:5px;flex-wrap:wrap;margin-top:5px">
            <span v-for="l in bug.labels" :key="l" class="flag-pill" style="background:var(--surface2);color:var(--text2)">{{ l }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>

  <AiSummaryModal
    :open="viewingBugRef !== null"
    :title="viewingBugRef ?? ''"
    :summary="viewingBugSummary"
    :generated-at="viewingBugGeneratedAt"
    :loading="viewingBugRef !== null && summarizingBug.has(viewingBugRef)"
    :error="viewingBugRef ? bugSummaries[viewingBugRef]?.message ?? null : null"
    @close="viewingBugRef = null"
    @regenerate="viewingBugRef && summarizeBug(viewingBugRef)"
  />

  <AiSummaryModal
    :open="viewingCustomerId !== null"
    :title="viewingCustomerName ?? ''"
    :summary="viewingCustomerId !== null ? (customerSummaries[viewingCustomerId]?.summary ?? null) : null"
    :generated-at="null"
    :loading="viewingCustomerId !== null && summarizing.has(viewingCustomerId)"
    :error="viewingCustomerId !== null ? (customerSummaries[viewingCustomerId]?.message ?? null) : null"
    @close="viewingCustomerId = null"
    @regenerate="viewingCustomerId !== null && summarizeCustomer(viewingCustomerId)"
  />
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted } from 'vue'
import { api, jiraUrl, type AgingBuckets, type VolumeAccount, type ExchangeCase, type VmsBug, type ResolvedStats, type CustomerCaseSummary } from '@/api/client'
import AgingBars from '@/components/charts/AgingBars.vue'
import AiSummaryModal from '@/components/AiSummaryModal.vue'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useBugDrill } from '@/composables/useBugDrill'

const { openCase } = useCaseDrill()
const { openBug } = useBugDrill()

const aging = ref<AgingBuckets | null>(null)
const volume = ref<{ accounts: VolumeAccount[] } | null>(null)
const exchanges = ref<{ threshold: number; cases: ExchangeCase[] } | null>(null)
const resolved = ref<ResolvedStats | null>(null)
const bugs = ref<VmsBug[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const summarizing = reactive<Set<number>>(new Set())
const customerSummaries = reactive<Record<number, { summary: string | null; message?: string }>>({})
const summarizingBug = reactive<Set<string>>(new Set())
const bugSummaries = reactive<Record<string, { summary: string | null; message?: string }>>({})

const drillOpen = ref<number | null>(null)
const drilling = reactive<Set<number>>(new Set())
const drillData = reactive<Record<number, CustomerCaseSummary>>({})

onMounted(async () => {
  try {
    const [a, v, e, b, r] = await Promise.all([
      api.supportSignals.aging(),
      api.supportSignals.volume(),
      api.supportSignals.exchanges(),
      api.bugs.list(),
      api.supportSignals.resolved(),
    ])
    aging.value = a.data
    volume.value = v.data
    exchanges.value = e.data
    bugs.value = b.data
    resolved.value = r.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Failed to load support signals'
  } finally {
    loading.value = false
  }
})

function barHeight(count: number) {
  if (!resolved.value) return 2
  const max = Math.max(...resolved.value.weekly_trend.map(w => w.count), 1)
  return Math.max(2, Math.round((count / max) * 40))
}

async function toggleDrill(customerId: number) {
  if (drillOpen.value === customerId) {
    drillOpen.value = null
    return
  }
  drillOpen.value = customerId
  if (drillData[customerId]) return
  drilling.add(customerId)
  try {
    const res = await api.customers.caseSummary(customerId)
    drillData[customerId] = res.data
  } finally {
    drilling.delete(customerId)
  }
}

// Which customer's summary modal (if any) is open, and their name for the
// modal title (VolumeAccount only carries customer_id, not a full Customer,
// so the name has to be looked up from the row that's already rendered).
const viewingCustomerId = ref<number | null>(null)
const viewingCustomerName = computed(() =>
  volume.value?.accounts.find(a => a.customer_id === viewingCustomerId.value)?.customer_name ?? null
)

function onCustomerSummaryClick(a: VolumeAccount) {
  if (customerSummaries[a.customer_id]?.summary) {
    viewingCustomerId.value = a.customer_id
    return
  }
  summarizeCustomer(a.customer_id)
}

async function summarizeCustomer(id: number) {
  viewingCustomerId.value = id
  summarizing.add(id)
  try {
    const res = await api.customers.summarize(id)
    customerSummaries[id] = res.data
  } finally {
    summarizing.delete(id)
  }
}

// Which bug's summary modal (if any) is currently open — a single shared
// modal instance for the whole list, not one per card.
const viewingBugRef = ref<string | null>(null)

// A bug "has a summary" either from its initial fetch (bug.ai_summary,
// generated in an earlier session and persisted) or from one just
// generated in this session (bugSummaries, keyed by ref) — check both so
// the button doesn't say "Summarize" right after a fresh generation just
// because the VmsBug list itself hasn't been re-fetched.
function bugHasSummary(bug: VmsBug): boolean {
  return !!(bug.ai_summary || bugSummaries[bug.jira_ref]?.summary)
}

const viewingBugSummary = computed(() => {
  if (!viewingBugRef.value) return null
  return bugSummaries[viewingBugRef.value]?.summary ?? bugs.value.find(b => b.jira_ref === viewingBugRef.value)?.ai_summary ?? null
})
const viewingBugGeneratedAt = computed(() => {
  if (!viewingBugRef.value) return null
  return bugs.value.find(b => b.jira_ref === viewingBugRef.value)?.ai_summary_at ?? null
})

function onBugSummaryClick(bug: VmsBug) {
  if (bugHasSummary(bug)) {
    viewingBugRef.value = bug.jira_ref
    return
  }
  summarizeBug(bug.jira_ref)
}

async function summarizeBug(ref: string) {
  viewingBugRef.value = ref
  summarizingBug.add(ref)
  try {
    const res = await api.bugs.summarize(ref)
    bugSummaries[ref] = res.data
  } finally {
    summarizingBug.delete(ref)
  }
}

function labelClass(label: string) {
  if (label === 'loud') return 'fip'
  if (label === 'quiet') return 'fup'
  if (label === 'calibrating') return 'lbl-calibrating'
  return ''
}

function statusClass(status: string) {
  if (status === 'Done') return 'ss-status-done'
  if (status === 'To Do') return 'ss-status-todo'
  return 'ss-status-progress'
}
</script>

<style scoped>
.lbl-calibrating {
  font-size: 8px; font-weight: 700; padding: 1px 5px; border-radius: 3px;
  text-transform: uppercase; letter-spacing: .04em;
  background: var(--surface3); color: var(--text3);
}
.ss-bug-card { padding: 10px 0; border-top: 1px solid var(--border); }
.ss-bug-card:first-of-type { border-top: none; }
.ss-bug-head { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; cursor: pointer; }
.ss-bug-head:hover .jref { text-decoration: underline; }
.ss-bug-status { font-size: 8px; font-weight: 700; padding: 1px 6px; border-radius: 3px; text-transform: uppercase; letter-spacing: .04em; }
.ss-status-done { background: var(--green-dim); color: var(--green); }
.ss-status-todo { background: var(--surface3); color: var(--text3); }
.ss-status-progress { background: var(--amber-dim); color: var(--amber); }
.ss-bug-customers { font-size: 11.5px; color: var(--text2); }
.ss-bug-customers b { color: var(--text); }

.ss-resolved-kpis { display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.ss-kpi { background: var(--surface2); border: 1px solid var(--border2); border-radius: 7px; padding: 8px 14px; min-width: 110px; }
.ss-kpi-val { font-size: 19px; font-weight: 800; color: var(--text); font-variant-numeric: tabular-nums; }
.ss-kpi-lbl { font-size: 9px; color: var(--text3); text-transform: uppercase; letter-spacing: .06em; margin-top: 2px; }

.ss-weektrend { display: flex; align-items: flex-end; gap: 3px; height: 44px; margin-bottom: 12px; }
.ss-weekbar-col { flex: 1; display: flex; align-items: flex-end; height: 100%; }
.ss-weekbar { width: 100%; background: var(--accent-dim); border-top: 2px solid var(--accent); border-radius: 2px 2px 0 0; min-height: 2px; }

.ss-top-resolved { font-size: 10.5px; color: var(--text3); display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.ss-top-resolved-lbl { font-weight: 700; text-transform: uppercase; letter-spacing: .05em; font-size: 8.5px; }
.ss-top-resolved-chip { background: var(--surface2); border: 1px solid var(--border2); border-radius: 4px; padding: 2px 7px; color: var(--text2); }
.ss-top-resolved-chip b { color: var(--text); font-variant-numeric: tabular-nums; }

.ss-drill-cell { padding: 8px 12px !important; background: var(--surface2); }
.ss-drill-row { display: flex; align-items: center; gap: 9px; font-size: 11px; padding: 4px 6px; border-bottom: 1px solid var(--border); cursor: pointer; border-radius: 4px; transition: background .15s; }
.ss-drill-row:hover { background: var(--surface3); }
.ss-drill-row:last-child { border-bottom: none; }
.ss-drill-title { color: var(--text2); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ss-drill-days { font-size: 9.5px; color: var(--text3); white-space: nowrap; }
</style>
