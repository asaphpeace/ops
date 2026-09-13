<template>
  <div class="view wr-page">
    <div class="sh">
      <div>
        <h2>Weekly Ops Report</h2>
        <p>Support · Bugs · Upgrades · Migrations · Incidents — for the DevOps priority meeting</p>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <select class="sel" v-model="selectedWeek" @change="loadWeek(selectedWeek)">
          <option v-for="w in weeks" :key="w.week" :value="w.week">{{ w.week }} ({{ w.status }})</option>
          <option v-if="!weeks.some(w => w.week === currentWeek)" :value="currentWeek">{{ currentWeek }} (not generated)</option>
        </select>
        <button class="btn btn-sm btn-g" :disabled="generating" @click="generate">{{ generating ? 'Generating…' : '↻ Generate' }}</button>
        <button v-if="report" class="btn btn-sm" :disabled="publishing" @click="togglePublish">
          {{ report.status === 'Draft' ? (publishing ? 'Publishing…' : 'Publish') : 'Unpublish' }}
        </button>
        <a v-if="report" :href="pdfUrl" target="_blank" class="btn btn-sm btn-g">⬇ PDF</a>
      </div>
    </div>

    <div v-if="loading" class="wr-empty">Loading…</div>
    <div v-else-if="!report" class="wr-empty">No report for {{ selectedWeek }} yet. Click Generate.</div>

    <template v-else>
      <div class="tw md-card" style="margin-bottom:14px">
        <div class="md-eyebrow">{{ report.period_start }} → {{ report.period_end }} · generated {{ formatDt(report.generated_at) }} · <span :class="['wr-status', report.status.toLowerCase()]">{{ report.status }}</span></div>
        <p class="wr-bluf">{{ snap.bluf }}</p>
        <div class="wr-rag-grid">
          <div v-for="(status, area) in snap.rag" :key="area" :class="['wr-rag-cell', status.toLowerCase()]">
            <div class="wr-rag-area">{{ area }}</div>
            <div class="wr-rag-status">{{ status }}</div>
          </div>
        </div>
      </div>

      <!-- Support -->
      <div class="tw puq" style="margin-bottom:14px">
        <div class="puq-head" style="cursor:pointer" @click="s.support = !s.support">
          <span>Support Cases <span class="puq-toggle">{{ s.support ? '▾' : '▸' }}</span></span>
          <span class="puq-count">{{ snap.support.scorecard.logged_count }} logged</span>
        </div>
        <div class="puq-body" v-show="s.support">
          <div class="wr-kpi-row">
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.support.scorecard.logged_count }}</div><div class="wr-kpi-l">Logged</div></div>
            <div class="wr-kpi good"><div class="wr-kpi-v">{{ snap.support.scorecard.resolved_count }}</div><div class="wr-kpi-l">Resolved</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.support.scorecard.fresh_resolved_count ?? '—' }}</div><div class="wr-kpi-l">Fresh Resolved</div></div>
            <div class="wr-kpi" :class="{ warn: snap.support.scorecard.sla_breach_tickets.length }"><div class="wr-kpi-v">{{ snap.support.scorecard.sla_breach_tickets.length }}</div><div class="wr-kpi-l">SLA Breaches</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.support.scorecard.replies_count ?? '—' }}</div><div class="wr-kpi-l">Replies</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.support.scorecard.comments_count ?? '—' }}</div><div class="wr-kpi-l">Comments</div></div>
          </div>
          <div class="wr-kpi-row" style="margin-top:8px">
            <div class="wr-kpi"><div class="wr-kpi-v">{{ round1(snap.support.scorecard.ttfr_median_hours) }}h</div><div class="wr-kpi-l">TTFR Median</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ round1(snap.support.scorecard.ttr_median_hours) }}h</div><div class="wr-kpi-l">TTR Median</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ round1(snap.support.scorecard.median_time_to_first_move_hours) }}h</div><div class="wr-kpi-l">Time to First Move</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ round1(snap.support.scorecard.waiting_on_me_median_hours) }}h</div><div class="wr-kpi-l">Waiting-On-Me</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.support.scorecard.open_load ?? snap.support.aging.total_open }}</div><div class="wr-kpi-l">Open Load (now)</div></div>
            <div class="wr-kpi" :class="loadTrendClass">
              <div class="wr-kpi-v">{{ snap.support.scorecard.open_load_vs_baseline_pct != null ? (snap.support.scorecard.open_load_vs_baseline_pct > 0 ? '+' : '') + round1(snap.support.scorecard.open_load_vs_baseline_pct) + '%' : '—' }}</div>
              <div class="wr-kpi-l">vs. 28d Baseline</div>
            </div>
          </div>

          <div class="wr-sublist">
            <div class="wr-sublist-h">Team breakdown — logged / assigned / resolved / replies / comments</div>
            <table class="wr-table">
              <thead><tr><th>Engineer</th><th>Logged</th><th>Assigned</th><th>Resolved</th><th>Fresh Resolved</th><th>Replies</th><th>Comments</th></tr></thead>
              <tbody>
                <tr v-for="(m, name) in snap.support.scorecard.by_engineer" :key="name">
                  <td>{{ name }}</td>
                  <td>{{ m?.logged ?? '—' }}</td>
                  <td>{{ m?.assigned ?? '—' }}</td>
                  <td>{{ m?.resolved ?? '—' }}</td>
                  <td>{{ m?.fresh_resolved ?? '—' }}</td>
                  <td>{{ m?.replies ?? '—' }}</td>
                  <td>{{ m?.comments ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="wr-sublist">
            <div class="wr-sublist-h">Case mix by status</div>
            <div v-for="cm in snap.support.scorecard.case_mix" :key="cm.status" class="wr-row">
              <span style="min-width:160px;font-weight:600">{{ cm.status }}</span>
              <span class="wr-badge">{{ cm.count }} total</span>
              <span class="wr-badge good">{{ cm.your_count }} yours</span>
            </div>
          </div>

          <div class="wr-sublist">
            <div class="wr-sublist-h">Aged cases</div>
            <div v-for="a in snap.support.scorecard.aged_cases" :key="a.label" class="wr-row">
              <span style="min-width:110px;font-weight:600">{{ a.label }}</span>
              <span class="wr-badge" :class="{ alert: a.count }">{{ a.count }}</span>
              <span v-for="ref in a.example_refs" :key="ref" class="jref" @click="openCase(ref)" style="margin-right:4px">{{ ref }}</span>
            </div>
          </div>

          <div class="wr-sublist">
            <div class="wr-sublist-h">Blocked cases ({{ snap.support.blocked_cases.length }})</div>
            <template v-if="snap.support.blocked_cases.length">
              <div v-for="c in snap.support.blocked_cases.slice(0, 10)" :key="c.jira_ref" class="wr-row">
                <span class="jref" @click="openCase(c.jira_ref)">{{ c.jira_ref }}</span>
                <span class="wr-cust" @click="goToCustomer(c.customer_id!, 'overview')">{{ c.customer_name }}</span>
                <span v-if="c.customer_tier" class="tier-badge" :class="tierClass(c.customer_tier)">{{ c.customer_tier }}</span>
                <span class="wr-reason">{{ c.blocked_reason }}</span>
              </div>
            </template>
            <div v-else class="wr-none">No blocked cases this week.</div>
          </div>
        </div>
      </div>

      <!-- Bugs -->
      <div class="tw puq" style="margin-bottom:14px">
        <div class="puq-head" style="cursor:pointer" @click="s.bugs = !s.bugs">
          <span>Bug Cases <span class="puq-toggle">{{ s.bugs ? '▾' : '▸' }}</span></span>
          <span class="puq-count">{{ snap.bugs.version_exposure.length }} exposed defects</span>
        </div>
        <div class="puq-body" v-show="s.bugs">
          <div class="wr-kpi-row">
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.bugs.fix_to_relief.median_days ?? '—' }}d</div><div class="wr-kpi-l">Fix→Relief Median</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.bugs.fix_to_relief.still_waiting_count }}</div><div class="wr-kpi-l">Still Waiting</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.bugs.missing_releases.length }}</div><div class="wr-kpi-l">Fixed, Not Released</div></div>
            <div class="wr-kpi"><div class="wr-kpi-v">{{ snap.bugs.bug_fix_upgrades_overdue.length }}</div><div class="wr-kpi-l">Bug-Fix Upgrades Overdue</div></div>
          </div>
          <div class="wr-sublist">
            <div class="wr-sublist-h">Defects with silently-exposed customers (top 8 by exposure)</div>
            <div v-for="b in topExposure" :key="b.vms_ref" class="wr-row">
              <span class="jref" @click="openBug(b.vms_ref)">{{ b.vms_ref }}</span>
              <span class="wr-reason">{{ b.fix_version ? `fix ${b.fix_version}` : 'no fix version' }} · {{ b.assignee || 'unassigned' }}</span>
              <span class="wr-badge alert">{{ b.silently_exposed_customers.length }} exposed, unreported</span>
              <span class="wr-badge">{{ b.reported_customers.length }} reported</span>
            </div>
          </div>
          <div class="wr-sublist">
            <div class="wr-sublist-h">Engineer impact</div>
            <table class="wr-table">
              <thead><tr><th>Engineer</th><th>Bugs Fixed</th><th>Customers Impacted</th><th>Top Bug</th></tr></thead>
              <tbody>
                <tr v-for="e in snap.bugs.engineer_impact.slice(0, 8)" :key="e.assignee">
                  <td>{{ e.assignee }}</td>
                  <td>{{ e.bugs_fixed }}</td>
                  <td>{{ e.customers_impacted }}</td>
                  <td><span v-if="e.top_bug" class="jref" @click="openBug(e.top_bug)">{{ e.top_bug }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Upgrades -->
      <div class="tw puq" style="margin-bottom:14px">
        <div class="puq-head" style="cursor:pointer" @click="s.upgrades = !s.upgrades">
          <span>Upgrade Cases <span class="puq-toggle">{{ s.upgrades ? '▾' : '▸' }}</span></span>
          <span class="puq-count">{{ snap.upgrades.pipeline.active_total }} active</span>
        </div>
        <div class="puq-body" v-show="s.upgrades">
          <div class="wr-kpi-row">
            <div v-for="stage in Object.keys(snap.upgrades.pipeline.stages)" :key="stage" class="wr-kpi">
              <div class="wr-kpi-v">{{ snap.upgrades.pipeline.stages[stage].length }}</div>
              <div class="wr-kpi-l">{{ stage }}</div>
            </div>
          </div>
          <div class="wr-kpi-row">
            <div class="wr-kpi warn"><div class="wr-kpi-v">{{ snap.upgrades.pipeline.blocked }}</div><div class="wr-kpi-l">Blocked</div></div>
            <div class="wr-kpi warn"><div class="wr-kpi-v">{{ snap.upgrades.unconfirmed.length }}</div><div class="wr-kpi-l">Unconfirmed</div></div>
            <div class="wr-kpi warn"><div class="wr-kpi-v">{{ snap.upgrades.superseded.length }}</div><div class="wr-kpi-l">Superseded</div></div>
            <div class="wr-kpi warn"><div class="wr-kpi-v">{{ snap.upgrades.pending_missing_case.length }}</div><div class="wr-kpi-l">Pending, Missing Case</div></div>
          </div>
          <div v-if="snap.upgrades.unconfirmed.length" class="wr-sublist">
            <div class="wr-sublist-h">Needs confirmation (DevOps and/or customer)</div>
            <div v-for="u in snap.upgrades.unconfirmed.slice(0, 10)" :key="u.id" class="wr-row">
              <span v-if="u.jira_ref" class="jref" @click="openCase(u.jira_ref!)">{{ u.jira_ref }}</span>
              <span class="wr-cust" @click="goToCustomer(u.customer_id, 'overview')">{{ u.customer_name }}</span>
              <span v-if="u.customer_tier" class="tier-badge" :class="tierClass(u.customer_tier)">{{ u.customer_tier }}</span>
              <span class="wr-badge" :class="u.devops_confirmed ? 'good' : 'alert'">DevOps {{ u.devops_confirmed ? '✓' : '—' }}</span>
              <span class="wr-badge" :class="u.customer_confirmed ? 'good' : 'alert'">Customer {{ u.customer_confirmed ? '✓' : '—' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Migrations -->
      <div class="tw puq" style="margin-bottom:14px">
        <div class="puq-head" style="cursor:pointer" @click="s.migrations = !s.migrations">
          <span>Migration Cases <span class="puq-toggle">{{ s.migrations ? '▾' : '▸' }}</span></span>
          <span class="puq-count">{{ snap.migrations.priority.customers.length }} scored</span>
        </div>
        <div class="puq-body" v-show="s.migrations">
          <div class="wr-kpi-row">
            <div v-for="stage in Object.keys(snap.migrations.board.stages)" :key="stage" class="wr-kpi">
              <div class="wr-kpi-v">{{ snap.migrations.board.stages[stage].length }}</div>
              <div class="wr-kpi-l">{{ stage }}</div>
            </div>
          </div>
          <div class="wr-sublist">
            <div class="wr-sublist-h">Migration priority — top bundling opportunities</div>
            <div v-for="c in snap.migrations.priority.customers.slice(0, 10)" :key="c.customer_id" class="wr-row">
              <span class="wr-cust" @click="goToCustomer(c.customer_id, 'overview')">{{ c.customer_name }}</span>
              <span class="tier-badge" :class="tierClass(c.customer_tier)">{{ c.customer_tier }}</span>
              <span class="wr-badge">{{ c.infra }} infra</span>
              <span class="wr-badge">{{ c.migration_stage }}</span>
              <span class="wr-badge">score {{ c.priority_score }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Incidents -->
      <div class="tw puq" style="margin-bottom:14px">
        <div class="puq-head" style="cursor:pointer" @click="s.incidents = !s.incidents">
          <span>Incidents <span class="puq-toggle">{{ s.incidents ? '▾' : '▸' }}</span></span>
          <span class="puq-count">{{ snap.incidents.open.length }} open</span>
        </div>
        <div class="puq-body" v-show="s.incidents">
          <div v-if="!snap.incidents.open.length" class="wr-none">No open incidents.</div>
          <div v-for="inc in snap.incidents.open" :key="inc.id" class="wr-incident">
            <div class="wr-row">
              <span :class="['flag-pill', inc.severity === 'Critical' || inc.severity === 'High' ? 'fip' : 'fup']">{{ inc.severity }}</span>
              <span class="wr-badge">{{ inc.phase }}</span>
              <strong>{{ inc.title }}</strong>
            </div>
            <div v-for="r in inc.remediations" :key="r.id" class="wr-row" style="margin-left:14px">
              <span class="wr-cust" @click="goToCustomer(r.customer_id, 'overview')">{{ r.customer_name }}</span>
              <span v-if="r.customer_tier" class="tier-badge" :class="tierClass(r.customer_tier)">{{ r.customer_tier }}</span>
              <span class="wr-badge" :class="r.derived_status === 'Done' ? 'good' : 'alert'">{{ r.derived_status }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Customers at risk -->
      <div class="tw puq" style="margin-bottom:14px">
        <div class="puq-head" style="cursor:pointer" @click="s.risk = !s.risk">
          <span>Customers at Risk <span class="puq-toggle">{{ s.risk ? '▾' : '▸' }}</span></span>
          <span class="puq-count">{{ snap.customers_at_risk.length }}</span>
        </div>
        <div class="puq-body" v-show="s.risk">
          <div v-for="c in snap.customers_at_risk.slice(0, 15)" :key="c.customer_id" class="wr-row" style="align-items:flex-start">
            <span class="wr-cust" @click="goToCustomer(c.customer_id, 'overview')">{{ c.customer_name }}</span>
            <span v-if="c.customer_tier" class="tier-badge" :class="tierClass(c.customer_tier)">{{ c.customer_tier }}</span>
            <span class="wr-badge alert">{{ c.signals.length }} signals</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type WeeklyReportMeta, type WeeklyReportSnapshot } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useBugDrill } from '@/composables/useBugDrill'

const { openCustomer: goToCustomer } = useCustomerDrill()
const { openCase } = useCaseDrill()
const { openBug } = useBugDrill()

function currentIsoWeek(): string {
  const d = new Date()
  const target = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const day = (target.getUTCDay() + 6) % 7
  target.setUTCDate(target.getUTCDate() - day + 3)
  const firstThursday = new Date(Date.UTC(target.getUTCFullYear(), 0, 4))
  const week = 1 + Math.round(((target.getTime() - firstThursday.getTime()) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7)
  return `${target.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
}

const currentWeek = currentIsoWeek()
const selectedWeek = ref(currentWeek)
const weeks = ref<WeeklyReportMeta[]>([])
const report = ref<(WeeklyReportMeta & { snapshot: WeeklyReportSnapshot }) | null>(null)
const loading = ref(false)
const generating = ref(false)
const publishing = ref(false)

const s = ref({ support: true, bugs: false, upgrades: true, migrations: false, incidents: true, risk: false })

const snap = computed(() => report.value!.snapshot)
const pdfUrl = computed(() => `/api/weekly-report/${selectedWeek.value}/pdf`)

const loadTrendClass = computed(() => {
  const pct = snap.value?.support.scorecard.open_load_vs_baseline_pct
  if (pct == null) return ''
  return pct > 0 ? 'warn' : 'good'
})

const topExposure = computed(() =>
  [...snap.value.bugs.version_exposure]
    .sort((a, b) => b.silently_exposed_customers.length - a.silently_exposed_customers.length)
    .slice(0, 8)
)

function round1(v: number | null): string | number {
  return v == null ? '—' : Math.round(v * 10) / 10
}
function formatDt(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
function tierClass(tier: string | null): string {
  if (tier === 'Premier') return 'type-s'
  if (tier === 'Strategic') return 'type-c'
  return ''
}

async function loadList() {
  const res = await api.weeklyReport.list()
  weeks.value = res.data
}

async function loadWeek(week: string) {
  loading.value = true
  report.value = null
  try {
    const res = await api.weeklyReport.get(week)
    report.value = res.data
  } catch {
    report.value = null
  } finally {
    loading.value = false
  }
}

async function generate() {
  generating.value = true
  try {
    const res = await api.weeklyReport.generate(selectedWeek.value)
    await loadList()
    await loadWeek(res.data.week)
  } finally {
    generating.value = false
  }
}

async function togglePublish() {
  if (!report.value) return
  publishing.value = true
  try {
    const newStatus = report.value.status === 'Draft' ? 'Published' : 'Draft'
    await api.weeklyReport.patch(report.value.week, { status: newStatus })
    await loadList()
    await loadWeek(report.value.week)
  } finally {
    publishing.value = false
  }
}

onMounted(async () => {
  await loadList()
  await loadWeek(selectedWeek.value)
})
</script>

<style scoped>
.wr-empty { padding: 40px; text-align: center; color: var(--text3); font-size: 12px; }
.wr-bluf { font-size: 12.5px; color: var(--text2); line-height: 1.6; margin: 4px 0 14px; }
.wr-status { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; padding: 1px 6px; border-radius: 3px; }
.wr-status.draft { background: var(--surface2); color: var(--text3); }
.wr-status.published { background: var(--green-dim); color: var(--green); }

.wr-rag-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.wr-rag-cell { border-radius: 7px; padding: 10px; text-align: center; border: 1px solid var(--border); }
.wr-rag-cell.green { background: var(--green-dim); border-color: rgba(15,186,129,.3); }
.wr-rag-cell.amber { background: var(--amber-dim); border-color: rgba(240,160,48,.3); }
.wr-rag-cell.red { background: var(--red-dim); border-color: rgba(232,68,90,.3); }
.wr-rag-area { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); }
.wr-rag-status { font-size: 13px; font-weight: 800; margin-top: 3px; }
.wr-rag-cell.green .wr-rag-status { color: var(--green); }
.wr-rag-cell.amber .wr-rag-status { color: var(--amber); }
.wr-rag-cell.red .wr-rag-status { color: var(--red); }

.wr-kpi-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.wr-kpi { flex: 1 1 110px; background: var(--surface2); border: 1px solid var(--border); border-radius: 7px; padding: 8px 10px; text-align: center; }
.wr-kpi.warn { border-color: rgba(240,160,48,.3); }
.wr-kpi.warn .wr-kpi-v { color: var(--amber); }
.wr-kpi.good .wr-kpi-v { color: var(--green); }
.wr-kpi-v { font-size: 16px; font-weight: 800; color: var(--text); font-variant-numeric: tabular-nums; }
.wr-kpi-l { font-size: 8.5px; color: var(--text3); text-transform: uppercase; letter-spacing: .04em; margin-top: 2px; }

.wr-sublist { margin-top: 10px; }
.wr-sublist-h { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; color: var(--text3); margin-bottom: 6px; }
.wr-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px dashed var(--border2); font-size: 10.5px; flex-wrap: wrap; }
.wr-row:last-child { border-bottom: none; }
.wr-cust { color: var(--text); cursor: pointer; font-weight: 600; }
.wr-cust:hover { text-decoration: underline; }
.wr-reason { color: var(--text3); font-size: 10px; }
.wr-none { color: var(--text3); font-size: 10.5px; padding: 4px 0; }
.wr-badge { font-size: 9px; padding: 1px 6px; border-radius: 3px; background: var(--surface2); border: 1px solid var(--border); color: var(--text3); }
.wr-badge.good { background: var(--green-dim); color: var(--green); border-color: rgba(15,186,129,.3); }
.wr-badge.alert { background: var(--red-dim); color: var(--red); border-color: rgba(232,68,90,.3); }

.wr-table { width: 100%; border-collapse: collapse; font-size: 10.5px; }
.wr-table th { text-align: left; font-size: 8.5px; text-transform: uppercase; letter-spacing: .04em; color: var(--text3); padding: 4px 8px; border-bottom: 1px solid var(--border); }
.wr-table td { padding: 4px 8px; border-bottom: 1px dashed var(--border2); }

.wr-incident { padding: 8px 0; border-bottom: 1px dashed var(--border2); }
.wr-incident:last-child { border-bottom: none; }

.puq-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid var(--border); font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .1em; color: var(--text3); }
.puq-count { font-size: 9px; font-weight: 700; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 1px 6px; color: var(--text3); text-transform: none; letter-spacing: 0; }
.puq-toggle { font-size: 10px; color: var(--text3); font-family: inherit; text-transform: none; letter-spacing: 0; }
.puq-body { padding: 10px 14px; }
</style>
