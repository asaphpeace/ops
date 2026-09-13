<template>
  <div class="view">
    <div class="sh" style="align-items:flex-end;flex-wrap:wrap">
      <div>
        <h2>Customer × environment</h2>
        <p>Every environment side by side — release, hosting, real AWS resource, and a risk score you can open.</p>
      </div>
      <input class="inp em-search" placeholder="customer, subdomain, instance id, release…" v-model="search">
    </div>

    <div class="em-chips">
      <FilterPills :options="envOptions" v-model="filterEnv" all-label="All Env" />
      <FilterPills :options="tierOptions" v-model="filterTier" all-label="All Tiers" />
      <FilterPills :options="hostingOptions" v-model="filterHosting" all-label="All Hosting" />
      <FilterPills :options="releaseOptions" v-model="filterRelease" all-label="All Releases" />
      <label class="em-toggle">
        <input type="checkbox" v-model="filterBehind">
        Behind current
      </label>
      <label class="em-toggle" title="Rows whose release comes from a JVM-mode tenant's /info endpoint — real, but not authoritative">
        <input type="checkbox" v-model="filterJvms">
        JVM mode only
      </label>
      <label class="em-toggle">
        <input type="checkbox" v-model="showGaps">
        Show {{ gapCount }} with no data on file
      </label>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>

    <template v-else-if="result">
      <div class="tw" style="overflow-x:auto">
        <div class="em-grid em-head">
          <div></div><div>Customer</div><div>Tier</div><div>Env</div><div>Subdomain</div><div>Release</div>
          <div>Hosting</div><div>AWS Resource</div><div style="text-align:center">CPU</div>
          <div style="text-align:center">Bugs</div><div style="text-align:center">Inc</div><div style="text-align:right">Risk</div>
        </div>
        <div v-for="r in filteredRows" :key="r.customer_id + r.environment" class="em-grid em-row" :class="{ 'em-gap': !r.has_data }" @click="goToCustomer(r.customer_id, r.environment)">
          <div><span class="em-dot" :class="riskDotClass(r)"></span></div>
          <div class="td-name em-ellipsis">{{ r.customer_name }}</div>
          <div class="sub" style="font-size:11px">{{ r.customer_tier }}</div>
          <div><span :class="['env-badge', envClass(r.environment)]" style="font-size:9px">{{ r.environment }}</span></div>
          <div class="sub em-ellipsis" style="font-size:11px">{{ r.subdomain || (r.has_data ? '—' : 'no data on file') }}</div>
          <div class="sub" :class="releaseColorClass(r)" style="font-variant-numeric:tabular-nums;font-size:11px" :title="r.is_jvms_mode ? 'JVM-mode tenant — this release value is from an unreliable endpoint, confirm with DevOps before trusting it' : ''">
            {{ r.release || '—' }}<span v-if="r.is_jvms_mode" style="color:var(--amber)"> ⚠</span>
          </div>
          <div class="sub" style="font-size:11px">{{ r.hosting_model || '—' }}</div>
          <div class="sub em-ellipsis em-mono" style="font-size:10.5px">
            <span v-if="r.aws_resource">{{ r.aws_resource.resource_id }}</span>
            <span v-else-if="r.has_data" style="font-style:italic">unmatched</span>
            <span v-else>—</span>
          </div>
          <div style="text-align:center;font-variant-numeric:tabular-nums" :class="cpuColorClass(r)">{{ r.cpu_utilization_pct != null ? r.cpu_utilization_pct.toFixed(0) + '%' : '—' }}</div>
          <div style="text-align:center;font-variant-numeric:tabular-nums" :class="countColorClass(r.reported_issues_count)">{{ r.reported_issues_count }}</div>
          <div style="text-align:center;font-variant-numeric:tabular-nums" :class="countColorClass(r.open_incident_count)">{{ r.open_incident_count }}</div>
          <div style="text-align:right;font-size:10.5px;letter-spacing:.04em" :class="riskTextClass(r)">{{ r.risk_label || '—' }}</div>
        </div>
        <div v-if="!filteredRows.length" class="sub" style="text-align:center;padding:16px;font-size:11px">No rows match{{ search ? ` "${search}"` : '' }}.</div>
      </div>
      <div class="sub" style="font-size:10px;color:var(--text3);margin-top:10px;text-align:center">
        {{ result.tenant_row_count }} of {{ result.vms_customer_count * 3 }} customer×environment slots have real tenant data on file
        ({{ result.vms_customer_count }} real VMS customers) · {{ result.matched_aws_count }} matched to a real AWS resource.
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type EnvironmentMatrixResult, type EnvironmentMatrixRow } from '@/api/client'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'
import FilterPills from '@/components/FilterPills.vue'

const { openEngineeringCustomer: goToCustomer } = useEngineeringDrill()

const loading = ref(true)
const result = ref<EnvironmentMatrixResult | null>(null)
const search = ref('')
const showGaps = ref(false)
const filterEnv = ref('')
const filterTier = ref('')
const filterHosting = ref('')
const filterRelease = ref('')
const filterBehind = ref(false)
const filterJvms = ref(false)

const envOptions = [{ value: 'PROD', label: 'PROD' }, { value: 'TEST', label: 'TEST' }, { value: 'DEV', label: 'DEV' }]
const tierOptions = [{ value: 'Premier', label: 'Premier' }, { value: 'Strategic', label: 'Strategic' }, { value: 'Scale', label: 'Scale' }]
const hostingOptions = [{ value: 'Docker / ECS', label: 'Docker / ECS' }, { value: 'EC2', label: 'EC2' }, { value: 'Legacy VM', label: 'Legacy VM' }]
const releaseOptions = [
  { value: 'Ageing', label: 'Release: Ageing' },
  { value: 'Legacy', label: 'Release: Legacy' },
  { value: 'End of life', label: 'Release: End of life' },
]

const gapCount = computed(() => result.value?.rows.filter(r => !r.has_data).length ?? 0)

const filteredRows = computed(() => {
  if (!result.value) return []
  let rows = result.value.rows
  if (!showGaps.value) rows = rows.filter(r => r.has_data)
  if (filterEnv.value) rows = rows.filter(r => r.environment === filterEnv.value)
  if (filterTier.value) rows = rows.filter(r => r.customer_tier === filterTier.value)
  if (filterHosting.value) rows = rows.filter(r => r.hosting_model === filterHosting.value)
  if (filterRelease.value) rows = rows.filter(r => r.release_status === filterRelease.value)
  if (filterBehind.value) rows = rows.filter(r => r.behind_current)
  if (filterJvms.value) rows = rows.filter(r => r.is_jvms_mode)
  const q = search.value.trim().toLowerCase()
  if (q) {
    rows = rows.filter(r =>
      r.customer_name.toLowerCase().includes(q) ||
      (r.subdomain || '').toLowerCase().includes(q) ||
      (r.aws_resource?.resource_id || '').toLowerCase().includes(q) ||
      (r.release || '').toLowerCase().includes(q)
    )
  }
  return rows
})

function envClass(env: string) {
  return env === 'PROD' ? 'ep' : env === 'TEST' ? 'et' : 'ed'
}
function riskDotClass(r: EnvironmentMatrixRow): string {
  if (r.risk_label === 'Critical') return 'red'
  if (r.risk_label === 'High') return 'amber'
  if (r.risk_label === 'Medium') return 'accent'
  if (r.risk_label === 'Low') return 'green'
  return ''
}
function riskTextClass(r: EnvironmentMatrixRow): string {
  if (r.risk_label === 'Critical' || r.risk_label === 'High') return 'em-alert'
  if (r.risk_label === 'Medium') return 'em-info'
  if (r.risk_label === 'Low') return 'em-good'
  return ''
}
function releaseColorClass(r: EnvironmentMatrixRow): string {
  if (r.release_status === 'Current') return 'em-good'
  if (r.release_status === 'Ageing') return 'em-warn-text'
  if (r.release_status === 'Legacy' || r.release_status === 'End of life') return 'em-alert'
  return ''
}
function cpuColorClass(r: EnvironmentMatrixRow): string {
  const cpu = r.cpu_utilization_pct
  if (cpu == null) return ''
  if (cpu >= 85) return 'em-alert'
  if (cpu >= 70) return 'em-warn-text'
  return ''
}
function countColorClass(count: number): string {
  return count > 0 ? 'em-warn-text' : ''
}

onMounted(async () => {
  try {
    const res = await api.engineering.matrix()
    result.value = res.data
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.em-search { width: 300px; margin-left: auto; }
.em-chips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 14px; }
.em-toggle { display: flex; align-items: center; gap: 6px; font-size: 10.5px; color: var(--text2); cursor: pointer; white-space: nowrap; }

.em-grid {
  display: grid;
  grid-template-columns: 20px 2fr 0.7fr 0.6fr 1.2fr 0.9fr 1fr 1.4fr 0.6fr 0.6fr 0.6fr 0.9fr;
  gap: 8px;
  align-items: center;
  padding: 8px 14px;
  font-size: 12px;
}
.em-head { font-size: 8.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); border-bottom: 1px solid var(--border); font-weight: 700; }
.em-row { border-bottom: 1px dashed var(--border2); cursor: pointer; transition: background .15s; }
.em-row:hover { background: var(--surface2); }
.em-row:last-child { border-bottom: none; }
.em-gap { opacity: .5; }
.em-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.em-mono { font-family: ui-monospace, monospace; }

.em-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--text3); }
.em-dot.green { background: var(--green); }
.em-dot.accent { background: var(--accent); }
.em-dot.amber { background: var(--amber); }
.em-dot.red { background: var(--red); }

.em-alert { color: var(--red) !important; font-weight: 700; }
.em-warn-text { color: var(--amber) !important; }
.em-good { color: var(--green) !important; }
.em-info { color: var(--accent) !important; }
</style>
