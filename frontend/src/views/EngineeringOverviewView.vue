<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Estate posture</h2>
        <p>What technical reality are we operating? Every number below resolves to named customers and environments — nothing here is a counter you cannot open.</p>
      </div>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>

    <template v-else-if="ov">
      <div class="eo-kpis">
        <div v-for="k in kpiTiles" :key="k.label" class="tw eo-kpi-tile" @click="k.go && k.go()">
          <div class="eo-kpi-label">{{ k.label }}</div>
          <div style="display:flex;align-items:baseline;gap:8px">
            <span class="eo-kpi-value">{{ k.value }}</span>
            <span v-if="k.deltaText" class="eo-kpi-delta" :style="{ color: k.deltaColor }">{{ k.deltaText }}</span>
          </div>
          <div class="sub" style="font-size:11.5px">{{ k.sub }}</div>
        </div>
      </div>

      <div class="eo-grid">
        <div style="display:flex;flex-direction:column;gap:11px">
          <div style="display:flex;align-items:baseline;justify-content:space-between">
            <h3 class="eo-h3">Version × infrastructure</h3>
            <span class="sub" style="font-size:10.5px">production environments</span>
          </div>
          <div class="tw" style="padding:14px">
            <div class="eo-vm-grid eo-vm-head">
              <div>Release band</div>
              <div style="text-align:center">Docker / ECS</div>
              <div style="text-align:center">EC2</div>
              <div style="text-align:center">Legacy VM</div>
              <div style="text-align:center">Unmatched</div>
              <div style="text-align:right">Total</div>
            </div>
            <div v-for="row in ov.version_infra_matrix.rows" :key="row.band" class="eo-vm-grid eo-vm-row">
              <div>{{ row.band }}</div>
              <div style="text-align:center" class="sub">{{ row.by_hosting['Docker / ECS'] || '—' }}</div>
              <div style="text-align:center" class="sub">{{ row.by_hosting['EC2'] || '—' }}</div>
              <div style="text-align:center" class="sub">{{ row.by_hosting['Legacy VM'] || '—' }}</div>
              <div style="text-align:center" class="sub">{{ row.by_hosting['Unmatched'] || '—' }}</div>
              <div style="text-align:right;font-variant-numeric:tabular-nums">{{ row.total }}</div>
            </div>
            <div class="sub" style="font-size:11px;margin-top:10px">{{ vmVerdict }}</div>
          </div>

          <div style="display:flex;align-items:baseline;justify-content:space-between;margin-top:5px">
            <h3 class="eo-h3">Engineering health</h3>
            <span class="sub" style="font-size:10.5px">{{ ov.kpis.estate.since ? `vs. ${ov.kpis.estate.since}` : 'no prior snapshot yet' }}</span>
          </div>
          <div class="tw" style="padding:2px 14px">
            <div v-for="h in healthRows" :key="h.label" class="eo-health-row">
              <span style="font-size:12.5px">{{ h.label }}</span>
              <span style="font-weight:700;font-variant-numeric:tabular-nums">{{ h.now }}</span>
              <span class="sub" style="font-variant-numeric:tabular-nums">{{ h.prev }}</span>
              <span style="font-size:11.5px" :style="{ color: h.color }">{{ h.trend }}</span>
            </div>
          </div>
        </div>

        <div style="display:flex;flex-direction:column;gap:11px">
          <div style="display:flex;align-items:baseline;justify-content:space-between">
            <h3 class="eo-h3">Needs a decision</h3>
            <span class="sub" style="font-size:10.5px">ranked by customer exposure</span>
          </div>
          <div v-if="!ov.attention_signals.length" class="tw sub" style="padding:20px;text-align:center;font-size:11px">No customer is currently hit by 2 or more real signals at once.</div>
          <div v-for="c in ov.attention_signals" :key="c.customer_id" class="tw eo-decision-card" :style="{ borderLeftColor: scoreColor(c.priority_score) }">
            <div style="display:flex;align-items:center;gap:8px">
              <span style="font-size:9.5px;text-transform:uppercase;letter-spacing:.08em;font-weight:700" :style="{ color: scoreColor(c.priority_score) }">Score {{ c.priority_score }}</span>
              <span class="tier-badge" :class="tierClass(c.customer_tier)" style="margin-left:auto">{{ c.customer_tier }}</span>
            </div>
            <div style="font-weight:700;font-size:14px" class="eo-cust" @click="goToCustomer(c.customer_id, 'overview')">{{ c.customer_name }}</div>
            <div class="sub" style="font-size:11.5px">{{ c.narrative }}</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:2px">
              <button class="btn btn-g btn-sm" @click="goToCustomer(c.customer_id, 'overview')">View customer</button>
              <RouterLink to="/engineering?tab=technical-risk" class="btn btn-g btn-sm" style="text-decoration:none">Open Technical Risk</RouterLink>
            </div>
          </div>
        </div>
      </div>

      <div class="tw eo-ri-strip">
        <div class="eo-ri-head">
          <span class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);font-weight:800">Also on Release Intelligence</span>
          <RouterLink to="/releases" class="jref" style="font-size:9.5px">Open Release Intelligence →</RouterLink>
        </div>
        <div class="eo-ri-chips">
          <span class="eo-ri-chip"><strong>{{ ov.version_exposure.length }}</strong> defects with fleet exposure</span>
          <span class="eo-ri-chip"><strong>{{ ov.missing_releases.length }}</strong> fixed, not released</span>
          <span class="eo-ri-chip"><strong>{{ ov.bug_fix_upgrades_overdue.length }}</strong> bug-fix upgrades overdue</span>
          <span class="eo-ri-chip"><strong>{{ ov.pending_upgrade_queue_count }}</strong> pending upgrade queue</span>
          <span class="eo-ri-chip" v-if="ov.engineer_impact[0]"><strong>{{ ov.engineer_impact[0].assignee }}</strong> top engineer impact</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, type EngineeringOverview } from '@/api/client'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'

const { openEngineeringCustomer: goToCustomer } = useEngineeringDrill()
const router = useRouter()

const loading = ref(true)
const ov = ref<EngineeringOverview | null>(null)

function tierClass(tier: string) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
function scoreColor(score: number) {
  return score >= 12 ? 'var(--red)' : score >= 8 ? 'var(--amber)' : 'var(--accent)'
}

function deltaText(delta: number | null): string | null {
  if (delta === null) return null
  if (delta === 0) return '±0'
  return delta > 0 ? `+${delta}` : `${delta}`
}

const kpiTiles = computed(() => {
  if (!ov.value) return []
  const k = ov.value.kpis
  return [
    {
      label: 'Estate', value: k.estate.value, deltaText: deltaText(k.estate.delta),
      deltaColor: 'var(--text3)', sub: `${ov.value.coverage.vms_customer_count} real VMS customers tracked`,
      go: () => router.push('/engineering?tab=matrix'),
    },
    {
      label: 'On Current Release', value: k.on_current_release.value, deltaText: deltaText(k.on_current_release.delta),
      deltaColor: (k.on_current_release.delta ?? 0) >= 0 ? 'var(--green)' : 'var(--red)',
      sub: 'PROD environments on the latest version', go: () => router.push('/engineering?tab=matrix'),
    },
    {
      label: 'Customer Exposure', value: k.customer_exposure.value, deltaText: deltaText(k.customer_exposure.delta),
      deltaColor: (k.customer_exposure.delta ?? 0) <= 0 ? 'var(--green)' : 'var(--red)',
      sub: 'reported or silently exposed to a known defect', go: () => router.push('/releases'),
    },
    {
      label: 'Legacy Footprint', value: k.legacy_footprint.value, deltaText: deltaText(k.legacy_footprint.delta),
      deltaColor: (k.legacy_footprint.delta ?? 0) <= 0 ? 'var(--green)' : 'var(--red)',
      sub: 'confirmed on Old AWS infrastructure', go: () => router.push('/engineering?tab=infrastructure'),
    },
  ]
})

const healthRows = computed(() => {
  if (!ov.value) return []
  const k = ov.value.kpis
  const rows = [
    { label: 'Estate', k: k.estate, goodDown: null as boolean | null },
    { label: 'On Current Release', k: k.on_current_release, goodDown: false },
    { label: 'Customer Exposure', k: k.customer_exposure, goodDown: true },
    { label: 'Legacy Footprint', k: k.legacy_footprint, goodDown: true },
  ]
  return rows.map(r => {
    const prev = r.k.delta !== null ? r.k.value - r.k.delta : null
    let trend = '—'
    let color = 'var(--text3)'
    if (r.k.delta !== null) {
      trend = deltaText(r.k.delta) || '±0'
      if (r.goodDown !== null && r.k.delta !== 0) {
        const good = r.goodDown ? r.k.delta < 0 : r.k.delta > 0
        color = good ? 'var(--green)' : 'var(--red)'
      }
    }
    return { label: r.label, now: r.k.value, prev: prev === null ? '—' : prev, trend, color }
  })
})

const vmVerdict = computed(() => {
  if (!ov.value) return ''
  const rows = ov.value.version_infra_matrix.rows
  const unmatchedTotal = rows.reduce((sum, r) => sum + (r.by_hosting['Unmatched'] || 0), 0)
  const grandTotal = rows.reduce((sum, r) => sum + r.total, 0)
  if (!grandTotal) return 'No PROD tenant data on file yet.'
  if (unmatchedTotal === grandTotal) {
    return `All ${grandTotal} PROD environments are unmatched to a real AWS resource yet — import an AWS export to see hosting type broken out.`
  }
  return `${grandTotal - unmatchedTotal} of ${grandTotal} PROD environments matched to a real, confirmed AWS resource.`
})

onMounted(async () => {
  try {
    const res = await api.engineering.overview()
    ov.value = res.data
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.eo-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 11px; margin-bottom: 20px; }
.eo-kpi-tile { padding: 14px 17px; cursor: pointer; display: flex; flex-direction: column; gap: 6px; }
.eo-kpi-tile:hover { background: var(--surface2); }
.eo-kpi-label { font-size: 10px; letter-spacing: .1em; text-transform: uppercase; color: var(--accent); }
.eo-kpi-value { font-weight: 700; font-size: 28px; line-height: 1; }
.eo-kpi-delta { font-size: 12px; }

.eo-grid { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 20px; margin-bottom: 16px; }
.eo-h3 { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--text2); margin: 0; }

.eo-vm-grid { display: grid; grid-template-columns: 1.4fr repeat(4, 1fr) 0.7fr; gap: 4px; font-size: 11.5px; }
.eo-vm-head { font-size: 9px; letter-spacing: .06em; text-transform: uppercase; color: var(--text3); padding: 5px; box-shadow: inset 0 -1px 0 var(--border); }
.eo-vm-row { padding: 7px 5px; box-shadow: inset 0 -1px 0 var(--border2); align-items: center; }
.eo-vm-row:last-child { box-shadow: none; }

.eo-health-row { display: grid; grid-template-columns: 1fr auto auto auto; gap: 16px; align-items: center; padding: 8px; margin: 0 -8px; box-shadow: inset 0 -1px 0 var(--border2); }
.eo-health-row:last-child { box-shadow: none; }

.eo-decision-card { padding: 14px; display: flex; flex-direction: column; gap: 7px; border-left: 2px solid; }
.eo-cust { cursor: pointer; }
.eo-cust:hover { text-decoration: underline; }

.eo-ri-strip { padding: 10px 15px; margin-bottom: 10px; opacity: .85; }
.eo-ri-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.eo-ri-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.eo-ri-chip { font-size: 9.5px; color: var(--text3); background: var(--surface2); border: 1px solid var(--border); border-radius: 5px; padding: 4px 8px; }
.eo-ri-chip strong { color: var(--text2); }
</style>
