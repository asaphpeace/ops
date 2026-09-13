<template>
  <div class="view">
    <div class="sh">
      <div><h2>Customer Education</h2><p>Training gaps across your customer base · feeds Sedna Academy content priorities</p></div>
      <button class="btn" @click="toggleForm">{{ showForm ? '✕ Cancel' : '+ Log Training Session' }}</button>
    </div>
    <div class="info-bar">ℹ Training gap data here feeds directly into the Sedna Academy LMS content roadmap. The most common gaps = the most needed course modules.</div>

    <!-- SUGGESTED TRAINING — VERSION-DRIVEN -->
    <div class="tw" style="padding:15px 17px;margin-bottom:20px">
      <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
        <span>Suggested Training — Version-Driven <span class="md-period">· real customers behind on real, feature-bearing releases</span></span>
        <button class="btn btn-g btn-sm" :disabled="refreshingNotes" @click="refreshReleaseNotes">
          {{ refreshingNotes ? 'Refreshing…' : '🔄 Refresh Release Notes' }}
        </button>
      </div>
      <div v-if="refreshResult" class="sub" style="font-size:10px;color:var(--text3);margin:6px 0">
        Fetched {{ refreshResult.fetched.length }} new version(s){{ refreshResult.failed.length ? `, ${refreshResult.failed.length} failed` : '' }}{{ refreshResult.empty.length ? `, ${refreshResult.empty.length} had no parseable new-feature content` : '' }}.
      </div>

      <div v-if="trLoading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>
      <div v-else-if="!trainingRecs.length" class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:20px 0">No customers currently behind on a release with real cached feature content — try "Refresh Release Notes" if this looks wrong.</div>

      <div v-else class="tr-list">
        <div v-for="c in trainingRecs" :key="c.customer_id" class="tr-row">
          <div class="tr-head" @click="toggleTr(c.customer_id)">
            <span class="tr-caret">{{ expandedTr === c.customer_id ? '▾' : '▸' }}</span>
            <span class="td-name">{{ c.customer_name }}</span>
            <span :class="['tier-badge', tierClass(c.customer_tier)]">{{ c.customer_tier }}</span>
            <span class="sub" style="color:var(--text3)">{{ c.current_version }} → {{ c.latest_version }}</span>
            <span class="flag-pill" style="background:var(--purple-dim);color:var(--purple);margin-left:auto">{{ c.feature_count }} real feature{{ c.feature_count === 1 ? '' : 's' }} shipped since</span>
          </div>
          <div v-if="expandedTr === c.customer_id" class="tr-detail">
            <div v-if="narrationFor(c.customer_id)" class="sub tr-narration">🤖 {{ narrationFor(c.customer_id) }}</div>
            <div v-for="f in c.features" :key="f.ticket_id ?? f.title" class="tr-feature-row">
              <span class="sub" style="color:var(--text3);min-width:42px">{{ f.version }}</span>
              <span style="font-size:9px;color:var(--purple);font-weight:700">{{ f.topic_area }}</span>
              <span style="color:var(--text2)">{{ f.title }}</span>
              <span v-if="f.ticket_id" class="sub" style="color:var(--text3);margin-left:auto">{{ f.ticket_id }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Log Training Session Form -->
    <div v-if="showForm" style="background:var(--surface2);border:1px solid var(--border2);border-radius:9px;padding:14px 16px;margin-bottom:14px">
      <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">Log Training Session</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Customer *</label>
          <select class="sel" v-model="newSess.customer_id">
            <option :value="0" disabled>Select customer…</option>
            <option v-for="c in customers" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Date *</label>
          <input class="inp" type="date" style="width:130px" v-model="newSess.session_date">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Topic Area *</label>
          <select class="sel" style="width:160px" v-model="newSess.topic_area">
            <option value="" disabled>Select area…</option>
            <option>Voyage Management</option>
            <option>Cargo Operations</option>
            <option>Period-End Closing</option>
            <option>Port Expenses</option>
            <option>Fleet Planning</option>
            <option>Reporting & Analytics</option>
            <option>User Administration</option>
            <option>Integrations</option>
            <option>Other</option>
          </select>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Format</label>
          <select class="sel" style="width:110px" v-model="newSess.format">
            <option value="">—</option>
            <option>Webinar</option>
            <option>Workshop</option>
            <option>1:1</option>
            <option>Group</option>
            <option>On-site</option>
          </select>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Delivered By</label>
          <input class="inp" style="width:100px" v-model="newSess.delivered_by">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Follow-up needed?</label>
          <select class="sel" style="width:100px" v-model="newSess.follow_up_needed">
            <option :value="false">No</option>
            <option :value="true">Yes</option>
          </select>
        </div>
        <div v-if="newSess.follow_up_needed" style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Follow-up note</label>
          <input class="inp" style="width:200px" placeholder="What needs follow-up?" v-model="newSess.follow_up_text">
        </div>
        <button class="btn"
          :disabled="!newSess.customer_id || !newSess.session_date || !newSess.topic_area || creating"
          @click="createSession">
          {{ creating ? 'Logging…' : 'Log Session' }}
        </button>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
      <!-- Top Training Gaps -->
      <div class="tc">
        <h4>Top Training Gaps — Fleet Wide (last 90 days)</h4>
        <template v-if="stats">
          <div v-for="item in stats.top_areas" :key="item.area" class="gap-bar">
            <div class="gap-label">{{ item.area }}</div>
            <div class="gap-track">
              <div class="gap-fill" :style="{ width: barWidth(item.count) }">{{ item.count }} cases</div>
            </div>
          </div>
          <div style="margin-top:12px;font-size:10px;color:var(--text3)">→ Priority for Sedna Academy: {{ stats.top_areas.slice(0, 3).map(a => a.area).join(' · ') }}</div>
        </template>
        <div v-else-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-else style="color:var(--text3);font-size:11px">No gap data.</div>
      </div>

      <!-- Customers with Recurring Gaps -->
      <div class="tc">
        <h4>Customers with Recurring Gaps (2+ in same area)</h4>
        <template v-if="recurringGaps.length">
          <div v-for="item in recurringGaps" :key="item.customer_name + item.area" class="tli tli-click" @click="goToCustomer(item.customer_id, 'education')">
            <span class="tli-n">{{ item.customer_name }}</span>
            <div style="display:flex;gap:6px;align-items:center">
              <span :class="['tier-badge', tierClass(item.customer_tier)]">{{ item.customer_tier }}</span>
              <span style="font-size:10px;color:var(--purple);font-weight:700">{{ item.area }} (×{{ item.count }})</span>
            </div>
          </div>
          <div style="margin-top:12px;padding:9px;background:var(--purple-dim);border:1px solid rgba(155,108,245,.2);border-radius:6px;font-size:10px;color:var(--purple)">
            {{ recurringGaps.length }} customer{{ recurringGaps.length > 1 ? 's' : '' }} recommended for dedicated training sessions. Consider proactive outreach via CSM.
          </div>
        </template>
        <div v-else-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-else style="color:var(--text3);font-size:11px;padding:8px 0">No recurring gaps identified.</div>
      </div>
    </div>

    <!-- Training Log -->
    <div class="sh"><div><h2>Training Log</h2><p>All sessions delivered</p></div></div>
    <div class="tw">
      <table>
        <thead>
          <tr>
            <th>Date</th><th>Customer</th><th>Tier</th><th>CSM</th>
            <th>Topic Area</th><th>Format</th><th>Delivered By</th><th>Follow-up Needed</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sessions" :key="s.id" class="edu-row" @click="goToCustomer(s.customer_id, 'education')">
            <td style="color:var(--text3)">{{ formatDate(s.session_date) }}</td>
            <td class="td-name">{{ s.customer_name }}</td>
            <td><span :class="['tier-badge', tierClass(s.customer_tier)]">{{ s.customer_tier }}</span></td>
            <td>{{ s.customer_csm ?? '—' }}</td>
            <td>{{ s.topic_area }}</td>
            <td>{{ s.format ?? '—' }}</td>
            <td>{{ s.delivered_by }}</td>
            <td>
              <span v-if="s.follow_up_needed" style="color:var(--amber)">Yes · {{ s.follow_up_text ?? '' }}</span>
              <span v-else style="color:var(--green)">Resolved</span>
            </td>
          </tr>
          <tr v-if="loading">
            <td colspan="8" style="text-align:center;color:var(--text3);padding:20px">Loading…</td>
          </tr>
          <tr v-else-if="!sessions.length">
            <td colspan="8" style="text-align:center;color:var(--text3);padding:20px">No sessions logged.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type Customer, type TrainingGap, type TrainingSession, type EducationStats, type TrainingRecommendation, type ReleaseNotesRefreshResult, type AiObservation } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCustomer: goToCustomer } = useCustomerDrill()

const gaps = ref<TrainingGap[]>([])
const sessions = ref<TrainingSession[]>([])
const stats = ref<EducationStats | null>(null)
const customers = ref<Customer[]>([])
const loading = ref(true)

// Suggested Training — Version-Driven
const trainingRecs = ref<TrainingRecommendation[]>([])
const trLoading = ref(true)
const expandedTr = ref<number | null>(null)
const refreshingNotes = ref(false)
const refreshResult = ref<ReleaseNotesRefreshResult | null>(null)
const observations = ref<AiObservation[]>([])

function toggleTr(customerId: number) {
  expandedTr.value = expandedTr.value === customerId ? null : customerId
}

function narrationFor(customerId: number): string | null {
  const obs = observations.value.find(o => o.kind === 'training_priority' && o.customer_id === customerId)
  return obs ? obs.summary : null
}

async function loadTrainingRecommendations() {
  trLoading.value = true
  try {
    const res = await api.education.trainingRecommendations()
    trainingRecs.value = res.data.customers
    try {
      const obsRes = await api.aiObservations.list()
      observations.value = obsRes.data
    } catch { /* Ollama observations are optional */ }
  } finally {
    trLoading.value = false
  }
}

async function refreshReleaseNotes() {
  refreshingNotes.value = true
  try {
    const res = await api.education.refreshReleaseNotes()
    refreshResult.value = res.data
    await loadTrainingRecommendations()
  } finally {
    refreshingNotes.value = false
  }
}

const showForm = ref(false)
const creating = ref(false)
const newSess = ref({
  customer_id: 0,
  session_date: new Date().toISOString().slice(0, 10),
  topic_area: '',
  format: '',
  delivered_by: 'Asaph',
  follow_up_needed: false,
  follow_up_text: '',
})

onMounted(async () => {
  try {
    const [gapRes, sessRes, statRes, custRes] = await Promise.all([
      api.education.gaps(),
      api.education.sessions(),
      api.education.stats(),
      api.customers.list(),
    ])
    gaps.value = gapRes.data
    sessions.value = sessRes.data
    stats.value = statRes.data
    customers.value = custRes.data
  } finally {
    loading.value = false
  }
  await loadTrainingRecommendations()
})

function toggleForm() {
  showForm.value = !showForm.value
  if (showForm.value) {
    newSess.value = {
      customer_id: 0,
      session_date: new Date().toISOString().slice(0, 10),
      topic_area: '',
      format: '',
      delivered_by: 'Asaph',
      follow_up_needed: false,
      follow_up_text: '',
    }
  }
}

async function createSession() {
  if (!newSess.value.customer_id || !newSess.value.session_date || !newSess.value.topic_area) return
  creating.value = true
  try {
    const res = await api.education.createSession({
      customer_id: newSess.value.customer_id,
      session_date: newSess.value.session_date,
      topic_area: newSess.value.topic_area,
      format: newSess.value.format || null,
      delivered_by: newSess.value.delivered_by,
      follow_up_needed: newSess.value.follow_up_needed,
      follow_up_text: newSess.value.follow_up_text || null,
    })
    sessions.value = [res.data, ...sessions.value]
    showForm.value = false
    // Refresh stats since a new session affects totals
    const statRes = await api.education.stats()
    stats.value = statRes.data
  } finally {
    creating.value = false
  }
}

const maxCount = computed(() => {
  if (!stats.value?.top_areas.length) return 1
  return Math.max(...stats.value.top_areas.map(a => a.count))
})

function barWidth(count: number) {
  return `${Math.round((count / maxCount.value) * 100)}%`
}

const recurringGaps = computed(() => {
  const byCustomerArea: Record<string, { customer_id: number; customer_name: string; customer_tier: string; area: string; count: number }> = {}
  for (const g of gaps.value) {
    const key = `${g.customer_name}|${g.area}`
    if (!byCustomerArea[key]) {
      byCustomerArea[key] = { customer_id: g.customer_id, customer_name: g.customer_name, customer_tier: g.customer_tier, area: g.area, count: 0 }
    }
    byCustomerArea[key].count += g.count
  }
  return Object.values(byCustomerArea).filter(x => x.count >= 2).sort((a, b) => b.count - a.count)
})

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function tierClass(t?: string | null) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}
</script>

<style scoped>
.tli-click { cursor: pointer; transition: background .15s; margin: 0 -4px; padding: 6px 4px !important; border-radius: 4px; }
.tli-click:hover { background: var(--surface2); }
.edu-row { cursor: pointer; transition: background .15s; }
.edu-row:hover { background: var(--surface2); }
.tr-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.tr-row { background: var(--surface2); border-radius: 7px; }
.tr-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 9px 11px; cursor: pointer; font-size: 11px; }
.tr-caret { font-size: 9px; color: var(--text3); width: 10px; flex-shrink: 0; }
.tr-detail { padding: 0 11px 10px 29px; display: flex; flex-direction: column; gap: 5px; }
.tr-narration { font-size: 10.5px; color: var(--text2); padding: 7px 9px; background: var(--surface3); border-radius: 6px; margin-bottom: 2px; }
.tr-feature-row { display: flex; align-items: center; gap: 8px; font-size: 10.5px; flex-wrap: wrap; }
</style>
