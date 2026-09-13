<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Deployments</h2>
        <p>Pipeline history joined to the estate — so "did anything change before it broke?" is one glance, not an archaeology session.</p>
      </div>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>

    <template v-else-if="result">
      <div class="dp-stats">
        <div class="tw dp-stat-tile">
          <div class="dp-stat-label">Last 7 Days</div>
          <div class="dp-stat-value">{{ result.stats.last_7_days }}</div>
          <div class="sub" style="font-size:11.5px">real Upgrade completions</div>
        </div>
        <div class="tw dp-stat-tile">
          <div class="dp-stat-label">Success Rate</div>
          <div class="dp-stat-value">{{ result.stats.success_rate }}</div>
          <div class="sub" style="font-size:11.5px">verified vs. cancelled, last 7d</div>
        </div>
        <div class="tw dp-stat-tile">
          <div class="dp-stat-label">Cancelled <span class="sub" style="font-size:9px;text-transform:none">(failed proxy)</span></div>
          <div class="dp-stat-value" :style="{ color: result.stats.failed_cancelled_7d ? 'var(--red)' : 'var(--text)' }">{{ result.stats.failed_cancelled_7d }}</div>
          <div class="sub" style="font-size:11.5px">last 7 days — no dedicated "Failed" stage exists yet</div>
        </div>
        <div class="tw dp-stat-tile">
          <div class="dp-stat-label">Manual Deploys Remaining</div>
          <div class="dp-stat-value">{{ result.stats.manual_deploys_remaining }}</div>
          <div class="sub" style="font-size:11.5px">Requested / DevOps Approval / Cust. Confirmed</div>
        </div>
      </div>

      <div class="dp-body">
        <div class="tw" style="padding:0;overflow:hidden">
          <div class="dp-grid dp-head">
            <div>When</div><div>Customer</div><div>Env</div><div>Move</div><div>Duration</div><div>Status</div><div style="text-align:right">Note</div>
          </div>
          <div v-for="d in result.deployments" :key="d.id" class="dp-grid dp-row" @click="d.customer_id && goToCustomer(d.customer_id, d.environment)">
            <div class="dp-mono">{{ formatDate(d.verified_at) }}</div>
            <div class="dp-ellipsis">{{ d.customer_name || '—' }}</div>
            <div style="font-size:10px" :class="d.environment === 'PROD' ? 'dp-env-prod' : 'dp-env-test'">{{ d.environment }}</div>
            <div class="sub" style="font-variant-numeric:tabular-nums">{{ d.move }}</div>
            <div class="sub">{{ d.duration_minutes }}m</div>
            <div style="color:var(--green)">{{ d.status }}</div>
            <div class="sub dp-ellipsis" style="text-align:right;font-size:11px">{{ d.note || '—' }}</div>
          </div>
          <div v-if="!result.deployments.length" class="sub" style="text-align:center;padding:20px;font-size:11px">No verified upgrades on file yet.</div>
        </div>

        <div style="display:flex;flex-direction:column;gap:11px">
          <div class="tw" style="padding:14px">
            <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);font-weight:800;margin-bottom:10px">
              {{ result.rollout.target_version || 'Latest release' }} rollout
            </div>
            <div v-for="b in result.rollout.buckets" :key="b.label" style="margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;font-size:11.5px">
                <span>{{ b.label }}</span><span class="sub">{{ b.count }}</span>
              </div>
              <div class="dp-bar-track"><div class="dp-bar-fill" :style="{ width: b.share, background: b.color }"></div></div>
              <div class="sub" style="font-size:10px;margin-top:3px">{{ b.note }}</div>
            </div>
          </div>
          <div class="tw" style="padding:14px">
            <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);font-weight:800;margin-bottom:8px">Scheduled</div>
            <div v-for="(u, i) in result.upcoming" :key="i" class="dp-upcoming-row">
              <span class="sub" style="font-size:10.5px;min-width:52px">{{ u.when }}</span>
              <span style="font-size:11.5px;flex:1">{{ u.what }}</span>
            </div>
            <div v-if="!result.upcoming.length" class="sub" style="font-size:10.5px">Nothing scheduled right now.</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, type DeploymentsResult } from '@/api/client'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'

const { openEngineeringCustomer: goToCustomer } = useEngineeringDrill()

const loading = ref(true)
const result = ref<DeploymentsResult | null>(null)

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

onMounted(async () => {
  try {
    const res = await api.engineering.deployments()
    result.value = res.data
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dp-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 11px; margin-bottom: 16px; }
.dp-stat-tile { padding: 14px; }
.dp-stat-label { font-size: 10px; letter-spacing: .1em; text-transform: uppercase; color: var(--accent); }
.dp-stat-value { font-weight: 700; font-size: 26px; margin-top: 6px; }

.dp-body { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 300px); gap: 16px; align-items: start; }
.dp-grid { display: grid; grid-template-columns: 1fr 2fr 0.7fr 1.3fr 0.8fr 1fr 1.1fr; gap: 8px; align-items: center; padding: 8px 14px; font-size: 12.5px; }
.dp-head { font-size: 9px; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); box-shadow: inset 0 -1px 0 var(--border); font-weight: 700; }
.dp-row { cursor: pointer; box-shadow: inset 0 -1px 0 var(--border2); }
.dp-row:hover { background: var(--surface2); }
.dp-mono { font-family: ui-monospace, monospace; font-size: 11.5px; color: var(--text2); }
.dp-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dp-env-prod { color: var(--red); }
.dp-env-test { color: var(--amber); }

.dp-bar-track { height: 4px; border-radius: 2px; background: var(--border2); margin-top: 5px; }
.dp-bar-fill { height: 4px; border-radius: 2px; }
.dp-upcoming-row { display: flex; gap: 8px; align-items: baseline; padding: 6px 0; box-shadow: inset 0 -1px 0 var(--border2); }
.dp-upcoming-row:last-child { box-shadow: none; }
</style>
