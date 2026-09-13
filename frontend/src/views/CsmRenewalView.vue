<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>CSM Renewal Risk</h2>
        <p>Customers approaching renewal · sorted by urgency · action before the window closes</p>
      </div>
    </div>

    <div v-if="error" class="info-bar" style="border-color:var(--red);color:var(--red);background:rgba(232,68,90,.06)">
      ⚠ {{ error }} — <button class="btn btn-g btn-sm" style="font-size:10px;padding:1px 7px" @click="load">Retry</button>
    </div>
    <div v-if="loading" class="info-bar">Loading renewal data…</div>

    <template v-if="!loading && !error">
      <!-- Headline stats -->
      <div class="stats-row sr-4" style="margin-bottom:20px">
        <div class="sc" :class="renewingIn30 > 0 ? 'alert' : 'good'">
          <div class="lbl">Renewing ≤30d</div>
          <div class="val">{{ renewingIn30 }}</div>
          <div class="sub">customers</div>
        </div>
        <div class="sc warn">
          <div class="lbl">Renewing 31–90d</div>
          <div class="val">{{ renewingIn90 }}</div>
          <div class="sub">customers</div>
        </div>
        <div class="sc" :class="highRisk > 0 ? 'alert' : 'good'">
          <div class="lbl">High Risk</div>
          <div class="val">{{ highRisk }}</div>
          <div class="sub">renewing ≤90d</div>
        </div>
        <div class="sc info">
          <div class="lbl">ARR at Risk</div>
          <div class="val">£{{ formatArr(arrAtRisk) }}</div>
          <div class="sub">≤90d + risk≥action</div>
        </div>
      </div>

      <div v-if="!filtered.length" class="info-bar">
        No customers with renewal dates configured.
      </div>

      <div v-for="row in filtered" :key="row.id" :class="['rc', row.risk]" @click="goToCustomer(row.id, 'overview')">
        <div :class="['rc-edge', row.risk]"></div>
        <div class="rc-body">
          <div class="rc-head">
            <span class="rc-name">{{ row.name }}</span>
            <span :class="['tier-badge', tierClass(row.tier)]">{{ row.tier }}</span>
            <span :class="['risk-pill', row.risk]">{{ row.risk }}</span>
            <div style="margin-left:auto;display:flex;align-items:center;gap:12px;flex-shrink:0">
              <div class="rc-stat">
                <span :class="['rc-val', renewalUrgency(row.renewal_days)]">
                  {{ row.renewal_days !== null ? `${row.renewal_days}d` : '—' }}
                </span>
                <span class="rc-lbl">Renewal</span>
              </div>
              <div class="rc-stat">
                <span class="rc-val" style="color:var(--text2)">{{ planName(row.tier) }}</span>
                <span class="rc-lbl">Package</span>
              </div>
              <div class="rc-stat">
                <span :class="['rc-val', tempUrgency(row.temperature)]">{{ row.temperature }}</span>
                <span class="rc-lbl">Temp</span>
              </div>
              <div class="rc-stat">
                <span :class="['rc-val', secClass(row.security_score)]">{{ row.security_score }}</span>
                <span class="rc-lbl">Security</span>
              </div>
            </div>
          </div>

          <div class="rc-detail">
            <div class="rc-badges">
              <span :class="['infra-badge', infraClass(row.infra)]">{{ row.infra }} infra</span>
              <span v-if="row.wildfly8" class="wf8-badge">WF8 pending</span>
              <span v-if="!row.sso || row.sso === 'None'" class="warn-badge">No SSO</span>
              <span v-if="row.sla_breaching_count > 0" class="breach-badge">
                {{ row.sla_breaching_count }} SLA breach{{ row.sla_breaching_count !== 1 ? 'es' : '' }}
              </span>
              <span v-if="row.training_gap_count > 0" class="gap-badge">
                {{ row.training_gap_count }} training gap{{ row.training_gap_count !== 1 ? 's' : '' }}
              </span>
              <span
                v-if="row.hypercare_until"
                class="hc-badge"
                :title="row.hypercare_reason || ''"
                @click.stop="toggleHypercareEdit(row)"
              >🔥 Hypercare until {{ row.hypercare_until }}</span>
              <button v-else class="hc-set-btn" @click.stop="toggleHypercareEdit(row)">+ Set hypercare</button>
            </div>

            <div v-if="expandedHypercareId === row.id" class="hc-edit" @click.stop>
              <input type="date" class="inp" style="width:130px" v-model="hypercareDraft.until">
              <input class="inp" style="flex:1;min-width:160px" placeholder="Reason" v-model="hypercareDraft.reason">
              <button class="btn btn-sm" :disabled="!hypercareDraft.until || savingHypercare" @click="saveHypercare(row)">
                {{ savingHypercare ? 'Saving…' : 'Save' }}
              </button>
              <button v-if="row.hypercare_until" class="btn btn-g btn-sm" :disabled="savingHypercare" @click="clearHypercareRow(row)">Clear</button>
              <button class="btn btn-g btn-sm" @click="expandedHypercareId = null">Cancel</button>
            </div>
            <div class="rc-cases">
              <span style="font-size:9px;color:var(--text3)">
                {{ row.active_case_count }} active case{{ row.active_case_count !== 1 ? 's' : '' }}
              </span>
              <span v-if="row.active_case_count > 0" style="margin-left:6px">
                <a
                  v-for="c in row.active_cases.slice(0, 3)"
                  :key="c.id"
                  :class="['case-chip', c.sla_breaching ? 'chip-breach' : '']"
                  :href="jiraUrl(c.jira_ref)"
                  target="_blank"
                  rel="noopener"
                  title="Open in Jira"
                  @click.stop
                >{{ c.jira_ref }}</a>
                <span v-if="row.active_cases.length > 3" style="font-size:9px;color:var(--text3)">
                  +{{ row.active_cases.length - 3 }} more
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { api, jiraUrl, planName, type CustomerTriageCard } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCustomer: goToCustomer } = useCustomerDrill()

// Inline hypercare quick-set — same PATCH/clear-hypercare calls the Customer
// Drill Panel's own edit form already uses, just exposed here too since
// this screen (unlike that panel) only ever lists customers with a real
// renewal_date, and CSMs work from here first.
const expandedHypercareId = ref<number | null>(null)
const hypercareDraft = reactive({ until: '', reason: '' })
const savingHypercare = ref(false)

function toggleHypercareEdit(row: CustomerTriageCard) {
  if (expandedHypercareId.value === row.id) {
    expandedHypercareId.value = null
    return
  }
  hypercareDraft.until = row.hypercare_until ?? ''
  hypercareDraft.reason = row.hypercare_reason ?? ''
  expandedHypercareId.value = row.id
}

async function saveHypercare(row: CustomerTriageCard) {
  if (!hypercareDraft.until) return
  savingHypercare.value = true
  try {
    await api.customers.patch(row.id, {
      hypercare_until: hypercareDraft.until,
      hypercare_reason: hypercareDraft.reason || null,
    })
    row.hypercare_until = hypercareDraft.until
    row.hypercare_reason = hypercareDraft.reason || null
    expandedHypercareId.value = null
  } finally {
    savingHypercare.value = false
  }
}

async function clearHypercareRow(row: CustomerTriageCard) {
  savingHypercare.value = true
  try {
    await api.customers.clearHypercare(row.id)
    row.hypercare_until = null
    row.hypercare_reason = null
    expandedHypercareId.value = null
  } finally {
    savingHypercare.value = false
  }
}

const customers = ref<CustomerTriageCard[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

async function load() {
  error.value = null
  loading.value = true
  try {
    const res = await api.customers.triage()
    customers.value = res.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Failed to load customer data'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const withRenewal = computed(() =>
  customers.value
    .filter(c => c.renewal_days !== null)
    .sort((a, b) => {
      if (a.renewal_days! !== b.renewal_days!) return a.renewal_days! - b.renewal_days!
      const riskOrder: Record<string, number> = { high: 0, action: 1, monitor: 2 }
      return riskOrder[a.risk] - riskOrder[b.risk]
    })
)

const filtered = computed(() => withRenewal.value)

const renewingIn30 = computed(() =>
  withRenewal.value.filter(c => (c.renewal_days ?? Infinity) <= 30).length
)
const renewingIn90 = computed(() =>
  withRenewal.value.filter(c => {
    const d = c.renewal_days ?? Infinity
    return d > 30 && d <= 90
  }).length
)
const highRisk = computed(() =>
  withRenewal.value.filter(c =>
    (c.renewal_days ?? Infinity) <= 90 && (c.risk === 'high' || c.risk === 'action')
  ).length
)
const arrAtRisk = computed(() =>
  withRenewal.value
    .filter(c => (c.renewal_days ?? Infinity) <= 90 && c.risk !== 'monitor')
    .reduce((sum, c) => sum + c.arr_gbp, 0)
)

function formatArr(n: number): string {
  return n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : `${Math.round(n / 1000)}K`
}

function renewalUrgency(days: number | null): string {
  if (days === null) return ''
  return days <= 30 ? 'ren-urgent' : days <= 60 ? 'ren-soon' : ''
}

function tempUrgency(t: number): string {
  return t > 60 ? 'temp-hot' : t > 40 ? 'temp-warm' : ''
}

function secClass(s: number): string {
  return s <= 40 ? 'sec-critical' : s <= 65 ? 'sec-risk' : ''
}

function tierClass(tier: string): string {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}

function infraClass(infra: string): string {
  return infra === 'New' ? 'in' : infra === 'Old' ? 'io' : 'im'
}
</script>

<style scoped>
.rc {
  display: flex;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 9px;
  margin-bottom: 10px;
  overflow: hidden;
  transition: border-color .15s, background .15s;
  cursor: pointer;
}
.rc:hover { border-color: var(--accent); background: var(--surface2); }

.rc-edge { width: 4px; flex-shrink: 0; }
.rc-edge.high    { background: var(--red); }
.rc-edge.action  { background: var(--amber); }
.rc-edge.monitor { background: var(--teal); }

.rc-body { flex: 1; padding: 12px 14px; min-width: 0; }

.rc-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.rc-name { font-size: 13px; font-weight: 800; color: var(--text); }

.risk-pill {
  font-size: 8px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: .06em;
  padding: 1px 5px;
  border-radius: 3px;
}
.risk-pill.high    { background: var(--red-dim); color: var(--red); }
.risk-pill.action  { background: var(--amber-dim); color: var(--amber); }
.risk-pill.monitor { background: var(--border); color: var(--text3); }

.rc-stat {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.rc-val {
  font-size: 13px;
  font-weight: 800;
  font-family: 'SF Mono', monospace;
  color: var(--text2);
  line-height: 1.2;
}
.rc-lbl {
  font-size: 8px;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--text3);
  font-weight: 700;
}

.ren-urgent { color: var(--red) !important; }
.ren-soon   { color: var(--amber) !important; }
.temp-hot   { color: var(--red); }
.temp-warm  { color: var(--amber); }
.sec-critical { color: var(--red); }
.sec-risk     { color: var(--amber); }

.rc-detail {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.rc-badges {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  align-items: center;
}

.warn-badge {
  font-size: 8px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--amber-dim);
  color: var(--amber);
}
.breach-badge {
  font-size: 8px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--red-dim);
  color: var(--red);
}
.gap-badge {
  font-size: 9px;
  color: var(--purple);
  background: var(--purple-dim);
  padding: 1px 6px;
  border-radius: 3px;
}
.wf8-badge {
  font-size: 8px;
  font-weight: 800;
  color: var(--amber);
  background: var(--amber-dim);
  padding: 1px 5px;
  border-radius: 3px;
}

.hc-badge {
  font-size: 8px;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--red-dim);
  color: var(--red);
  cursor: pointer;
}
.hc-badge:hover { filter: brightness(1.15); }
.hc-set-btn {
  font-size: 8px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--surface2);
  border: 1px solid var(--border2);
  color: var(--text3);
  cursor: pointer;
}
.hc-set-btn:hover { color: var(--text); border-color: var(--accent); }
.hc-edit {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border2);
}

.rc-cases { display: flex; align-items: center; flex-wrap: wrap; }

.case-chip {
  display: inline-block;
  font-size: 9px;
  font-family: monospace;
  color: var(--accent);
  background: var(--accent-dim);
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: 4px;
  cursor: pointer;
  text-decoration: none;
}
.case-chip:hover { filter: brightness(1.3); }
.chip-breach { color: var(--red); background: var(--red-dim); }
</style>
