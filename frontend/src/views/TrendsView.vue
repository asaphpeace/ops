<template>
  <div class="view">
    <div class="sh">
      <div><h2>Trends & Fleet Health</h2><p>Derived intelligence · revenue-weighted · feeds Gisele summary</p></div>
      <button class="btn btn-g btn-sm" @click="exportSummary">Export Management Summary</button>
    </div>

    <div class="stats-row sr-5" v-if="loaded">
      <div class="sc alert">
        <div class="lbl">No Upgrade 12mo+</div>
        <div class="val">{{ noUpgrade12m.length }}</div>
        <div class="sub">{{ formatArr(noUpgrade12mArr) }} ARR stagnating</div>
      </div>
      <div class="sc alert">
        <div class="lbl">ARR — Red Health</div>
        <div class="val">{{ formatArr(customerStats?.arr_red_health) }}</div>
        <div class="sub">{{ customerStats?.red_health_count ?? '—' }} customers</div>
      </div>
      <div class="sc warn">
        <div class="lbl">At Upgrade Limit</div>
        <div class="val">{{ atLimit.length }}</div>
        <div class="sub">{{ atLimit.slice(0, 2).map(c => c.name.split(' ')[0]).join(' · ') }}{{ atLimit.length > 2 ? ' · others' : '' }}</div>
      </div>
      <div class="sc good">
        <div class="lbl">Migration Rate</div>
        <div class="val">{{ migratedCount }}</div>
        <div class="sub">complete · {{ remainingMigrations }} to go</div>
      </div>
      <div class="sc info">
        <div class="lbl">SLA Breaching</div>
        <div class="val">{{ triage?.sla_breaching ?? '—' }}</div>
        <div class="sub">active today</div>
      </div>
    </div>

    <!-- 4-panel tg grid -->
    <div class="tg">
      <!-- Version Distribution — real CustomerTenantInfo data (VMS customers
           only), fetched from /releases/version-distribution. Used to read
           the fake Customer.prod_version field with a broken comparator;
           see backend/app/routers/releases.py::version_distribution(). -->
      <div class="tc">
        <h4>Version Distribution — Prod Environments (VMS customers)</h4>
        <template v-for="bucket in versionDistribution?.buckets ?? []" :key="bucket.label">
          <div class="vbr">
            <div class="vl">{{ bucket.label }}</div>
            <div class="vt">
              <div :class="['vf', bucket.cls]" :style="{ width: `${bucket.pct}%`, overflow: 'hidden', whiteSpace: 'nowrap' }">
                {{ bucket.count }} customer{{ bucket.count !== 1 ? 's' : '' }}
              </div>
            </div>
          </div>
        </template>
        <div v-if="versionDistribution" style="color:var(--text3);font-size:10px;margin-top:6px">
          Of {{ versionDistribution.vms_customer_count }} real VMS customers.
        </div>
      </div>

      <!-- Revenue at Risk -->
      <div class="tc">
        <h4>Revenue at Risk — Four Lenses</h4>
        <div class="tli">
          <span class="tli-n">On old infrastructure (VMS customers)</span>
          <span style="font-family:monospace;font-size:11px;color:var(--red);font-weight:700">{{ formatArr(vmsArrOldInfra) }}</span>
        </div>
        <div class="tli">
          <span class="tli-n">Red health score</span>
          <span style="font-family:monospace;font-size:11px;color:var(--red);font-weight:700">{{ formatArr(customerStats?.arr_red_health) }}</span>
        </div>
        <div class="tli">
          <span class="tli-n">Renewing within 60d · amber/red health</span>
          <span style="font-family:monospace;font-size:11px;color:var(--amber);font-weight:700">{{ formatArr(customerStats?.arr_renewal_risk) }}</span>
        </div>
        <div class="tli">
          <span class="tli-n">Has open defects</span>
          <span style="font-family:monospace;font-size:11px;color:var(--amber);font-weight:700">{{ formatArr(customerStats?.arr_open_defects) }}</span>
        </div>
        <div style="margin-top:10px;padding:9px;background:var(--red-dim);border-radius:6px;font-size:10px;color:var(--red)">
          Total addressable risk — overlaps possible across lenses.
        </div>
      </div>

      <!-- Pipeline Dwell Time -->
      <div class="tc">
        <h4>Pipeline Dwell Time</h4>
        <template v-if="dwellStats.total > 0">
          <div v-for="phase in dwellPhases" :key="phase.label" class="vbr" style="margin-bottom:6px">
            <div class="vl" style="width:130px;flex-shrink:0">{{ phase.label }}</div>
            <div class="vt" style="flex:1">
              <div :class="['vf', phase.cls]" :style="{ width: `${phase.pct}%`, minWidth: phase.avg > 0 ? '18px' : '0' }">
                {{ phase.avg > 0 ? `${phase.avg}d` : '' }}
              </div>
            </div>
            <div style="font-size:9px;color:var(--text3);width:28px;text-align:right;flex-shrink:0">{{ phase.n }}</div>
          </div>
          <div style="margin-top:8px;padding:8px;background:var(--surface2);border-radius:6px;font-size:10px;color:var(--text2)">
            Avg cycle <span style="color:var(--text);font-weight:700;font-family:monospace">{{ dwellStats.total }}d</span> · based on {{ dwellStats.count }} completed upgrade{{ dwellStats.count !== 1 ? 's' : '' }}
          </div>
        </template>
        <div v-else style="font-size:10px;color:var(--text3);padding:6px 0">No completed upgrades with timestamp data yet.</div>
      </div>

      <!-- CSM Workload -->
      <div class="tc">
        <h4>CSM Workload & Fleet Health</h4>
        <div v-for="csm in csmWorkload" :key="csm.name" class="tli">
          <span class="tli-n">{{ csm.name }}</span>
          <div style="display:flex;gap:6px;align-items:center">
            <span style="font-size:10px;color:var(--text3)">{{ csm.count }} accounts · {{ formatArr(csm.arr) }}</span>
            <div :class="['health-dot', csm.healthDot]"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Approaching upgrade limit -->
    <div v-if="atLimitOrNear.length" style="margin-top:4px">
      <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">Approaching / At Upgrade Limit</div>
      <div class="tw">
        <table>
          <thead><tr><th>Customer</th><th>Tier</th><th>Package</th><th>Used / Limit</th></tr></thead>
          <tbody>
            <tr v-for="c in atLimitOrNear" :key="c.id" class="trend-cust-row" @click="goToCustomer(c.id, 'overview')">
              <td class="td-name">{{ c.name }}</td>
              <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
              <td>{{ planName(c.tier) }}</td>
              <td><span :style="limitColor(c)">{{ c.upgrades_used }} / {{ c.upgrades_limit }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, planName, type Customer, type CustomerStats, type TriageStats, type Upgrade, type VersionDistributionStats } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCustomer: goToCustomer } = useCustomerDrill()

const customers = ref<Customer[]>([])
const upgrades = ref<Upgrade[]>([])
const customerStats = ref<CustomerStats | null>(null)
const triage = ref<TriageStats | null>(null)
const versionDistribution = ref<VersionDistributionStats | null>(null)
const loading = ref(true)
const loaded = ref(false)

onMounted(async () => {
  try {
    const [custRes, upgRes, statRes, triRes] = await Promise.all([
      api.customers.list(),
      api.upgrades.list(),
      api.customers.stats(),
      api.cases.triage(),
    ])
    customers.value = custRes.data
    upgrades.value = upgRes.data
    customerStats.value = statRes.data
    triage.value = triRes.data
    loaded.value = true
  } finally {
    loading.value = false
  }
  // Separate, non-blocking fetch — real but sparse CustomerTenantInfo data;
  // degrade quietly (chart just stays empty) rather than failing the page.
  try {
    versionDistribution.value = (await api.releases.versionDistribution()).data
  } catch { /* chart shows nothing rather than a stale/fake distribution */ }
})

const cutoff12m = new Date(Date.now() - 365 * 24 * 3600 * 1000)

function lastUpgradeDateFor(customerId: number): Date | null {
  const done = upgrades.value
    .filter(u => u.customer_id === customerId && u.stage === 'Verified Done' && u.environment === 'PROD' && u.date_done)
    .sort((a, b) => new Date(b.date_done!).getTime() - new Date(a.date_done!).getTime())
  return done.length ? new Date(done[0].date_done!) : null
}

const noUpgrade12m = computed(() =>
  customers.value.filter(c => {
    const last = lastUpgradeDateFor(c.id)
    return !last || last < cutoff12m
  })
)
const noUpgrade12mArr = computed(() => noUpgrade12m.value.reduce((a, c) => a + c.arr_gbp, 0))

const atLimit = computed(() => customers.value.filter(c => c.upgrades_used >= c.upgrades_limit))
const atLimitOrNear = computed(() => customers.value.filter(c => c.upgrades_used >= Math.floor(c.upgrades_limit * 0.7)))

// Customer.infra defaults to "Old" on every customer regardless of product —
// confirmed live only 53 of 533 "Old"-infra customers are real VMS accounts
// with actual AWS infrastructure to migrate (the rest are Email/CompassAir-
// only, no real infra at all). Migration Rate and the old-infra ARR lens
// below are both scoped to real VMS customers for the same reason the
// Customer Intelligence strip was fixed to be.
const vmsCustomers = computed(() => customers.value.filter(c => c.product && c.product.toUpperCase().includes('VMS')))
const vmsArrOldInfra = computed(() => vmsCustomers.value.filter(c => c.infra === 'Old').reduce((a, c) => a + c.arr_gbp, 0))

const migratedCount = computed(() => vmsCustomers.value.filter(c => c.infra === 'New').length)

function daysBetween(a: string | null, b: string | null): number | null {
  if (!a || !b) return null
  const diff = new Date(b).getTime() - new Date(a).getTime()
  return diff > 0 ? Math.round(diff / 86400000) : null
}

function avgDays(vals: (number | null)[]): { avg: number; n: number } {
  const valid = vals.filter((v): v is number => v !== null)
  return { avg: valid.length ? Math.round(valid.reduce((a, b) => a + b, 0) / valid.length) : 0, n: valid.length }
}

const dwellPhases = computed(() => {
  const done = upgrades.value.filter(u => u.stage === 'Verified Done' && u.verified_at)
  const p1 = done.map(u => daysBetween(u.created_at, u.confirmed_at))
  const p2 = done.map(u => daysBetween(u.confirmed_at, u.scheduled_at))
  const p3 = done.map(u => daysBetween(u.scheduled_at, u.date_done))
  const p4 = done.map(u => daysBetween(u.date_done, u.verified_at))
  const maxAvg = Math.max(...[p1, p2, p3, p4].map(p => avgDays(p).avg), 1)
  return [
    { label: 'Req → Confirmed', ...avgDays(p1), cls: 'v-mid' },
    { label: 'Confirmed → Sched', ...avgDays(p2), cls: 'v-mid' },
    { label: 'Sched → Done', ...avgDays(p3), cls: 'v-new' },
    { label: 'Done → Verified', ...avgDays(p4), cls: 'v-new' },
  ].map(p => ({ ...p, pct: Math.round(p.avg / maxAvg * 100) }))
})

const dwellStats = computed(() => {
  const done = upgrades.value.filter(u => u.stage === 'Verified Done' && u.verified_at && u.created_at)
  const totals = done.map(u => daysBetween(u.created_at, u.verified_at)).filter((v): v is number => v !== null)
  const avg = totals.length ? Math.round(totals.reduce((a, b) => a + b, 0) / totals.length) : 0
  return { total: avg, count: totals.length }
})
const remainingMigrations = computed(() => vmsCustomers.value.filter(c => c.infra !== 'New').length)


const csmWorkload = computed(() => {
  const map: Record<string, { arr: number; count: number; avgHealth: number; totalHealth: number }> = {}
  for (const c of customers.value) {
    if (!map[c.csm]) map[c.csm] = { arr: 0, count: 0, avgHealth: 0, totalHealth: 0 }
    map[c.csm].arr += c.arr_gbp
    map[c.csm].count++
    map[c.csm].totalHealth += c.health_score
  }
  return Object.entries(map).map(([name, d]) => ({
    name,
    arr: d.arr,
    count: d.count,
    avgHealth: d.totalHealth / d.count,
    healthDot: d.totalHealth / d.count > 70 ? 'hg' : d.totalHealth / d.count > 45 ? 'ha' : 'hr',
  })).sort((a, b) => b.arr - a.arr)
})

function formatArr(v?: number | null) {
  if (v == null) return '—'
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}K`
  return `£${v.toLocaleString()}`
}

function tierClass(t?: string | null) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}

function exportSummary() {
  const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  const lines: string[] = [`FLEET HEALTH & TRENDS — ${today}`, '']

  lines.push('KEY METRICS:')
  lines.push(`  No upgrade 12mo+:   ${noUpgrade12m.value.length} customers · ${formatArr(noUpgrade12mArr.value)} ARR stagnating`)
  lines.push(`  Red health score:   ${customerStats.value?.red_health_count ?? '?'} customers · ${formatArr(customerStats.value?.arr_red_health)} ARR`)
  lines.push(`  On old infra (VMS): ${vmsCustomers.value.filter(c => c.infra === 'Old').length} of ${vmsCustomers.value.length} VMS customers · ${formatArr(vmsArrOldInfra.value)} ARR`)
  lines.push(`  Renewal risk (60d): ${formatArr(customerStats.value?.arr_renewal_risk)}`)
  lines.push(`  At upgrade limit:   ${atLimit.value.length} customers`)
  lines.push(`  SLA breaching now:  ${triage.value?.sla_breaching ?? '?'} cases`)
  lines.push('')

  if (noUpgrade12m.value.length) {
    lines.push('NO UPGRADE IN 12+ MONTHS:')
    noUpgrade12m.value.forEach(c => lines.push(`  • ${c.name} — ${c.prod_version ?? '?'} · ${planName(c.tier)}`))
    lines.push('')
  }

  if (atLimit.value.length) {
    lines.push('AT UPGRADE LIMIT:')
    atLimit.value.forEach(c => lines.push(`  • ${c.name} — ${c.upgrades_used}/${c.upgrades_limit} upgrades used`))
    lines.push('')
  }

  lines.push('VERSION DISTRIBUTION (PROD, VMS customers):')
  if (versionDistribution.value) {
    versionDistribution.value.buckets.forEach(b => lines.push(`  ${b.label}: ${b.count} customers (${b.pct}%)`))
  }
  lines.push('')

  lines.push('CSM WORKLOAD:')
  csmWorkload.value.forEach(csm => lines.push(`  ${csm.name}: ${csm.count} accounts · ${formatArr(csm.arr)}`))

  const subject = encodeURIComponent(`Fleet Health Summary — ${today}`)
  const body = encodeURIComponent(lines.join('\n'))
  window.open(`mailto:?subject=${subject}&body=${body}`, '_blank')
}

function limitColor(c: Customer) {
  if (c.upgrades_used >= c.upgrades_limit) return 'color:var(--red);font-weight:700'
  if (c.upgrades_used >= c.upgrades_limit * 0.7) return 'color:var(--amber)'
  return 'color:var(--green)'
}
</script>

<style scoped>
.trend-cust-row { cursor: pointer; transition: background .15s; }
.trend-cust-row:hover { background: var(--surface2); }
</style>
