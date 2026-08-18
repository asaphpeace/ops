<template>
  <div class="view">
    <div class="sh">
      <div><h2>Trends & Fleet Health</h2><p>Derived intelligence · revenue-weighted · feeds Gisele summary</p></div>
      <button class="btn btn-g btn-sm">Export Management Summary</button>
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
      <!-- Version Distribution -->
      <div class="tc">
        <h4>Version Distribution — Prod Environments</h4>
        <template v-for="bucket in versionBuckets" :key="bucket.label">
          <div class="vbr">
            <div class="vl">{{ bucket.label }}</div>
            <div class="vt">
              <div :class="['vf', bucket.cls]" :style="{ width: `${bucket.pct}%`, overflow: 'hidden', whiteSpace: 'nowrap' }">
                {{ bucket.count }} customer{{ bucket.count !== 1 ? 's' : '' }}
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Revenue at Risk -->
      <div class="tc">
        <h4>Revenue at Risk — Four Lenses</h4>
        <div class="tli">
          <span class="tli-n">On old infrastructure</span>
          <span style="font-family:monospace;font-size:11px;color:var(--red);font-weight:700">{{ formatArr(customerStats?.arr_old_infra) }}</span>
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

      <!-- No Upgrade 12m+ detail -->
      <div class="tc">
        <h4>No Upgrade in 12+ Months</h4>
        <template v-if="noUpgrade12m.length">
          <div v-for="c in noUpgrade12m.slice(0, 6)" :key="c.id" class="tli">
            <span class="tli-n">{{ c.name }}</span>
            <div style="display:flex;gap:6px;align-items:center">
              <span style="font-size:10px;color:var(--text3)">{{ c.prod_version ?? '—' }}</span>
              <span style="font-family:monospace;font-size:10px;color:var(--red)">{{ formatArr(c.arr_gbp) }}</span>
            </div>
          </div>
          <div v-if="noUpgrade12m.length > 6" style="margin-top:8px;font-size:9px;color:var(--text3)">+ {{ noUpgrade12m.length - 6 }} more</div>
        </template>
        <div v-else style="font-size:10px;color:var(--green);padding:6px 0">All customers upgraded within 12 months ✓</div>
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
          <thead><tr><th>Customer</th><th>Tier</th><th>ARR</th><th>Used / Limit</th></tr></thead>
          <tbody>
            <tr v-for="c in atLimitOrNear" :key="c.id">
              <td class="td-name">{{ c.name }}</td>
              <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
              <td>{{ formatArr(c.arr_gbp) }}</td>
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
import { api, type Customer, type CustomerStats, type TriageStats, type Upgrade } from '@/api/client'

const customers = ref<Customer[]>([])
const upgrades = ref<Upgrade[]>([])
const customerStats = ref<CustomerStats | null>(null)
const triage = ref<TriageStats | null>(null)
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

const migratedCount = computed(() => customers.value.filter(c => c.infra === 'New').length)
const remainingMigrations = computed(() => customers.value.filter(c => c.infra !== 'New').length)

// Version buckets matching the prototype
const versionBuckets = computed(() => {
  const total = customers.value.length || 1
  const buckets = [
    { label: '8.30.x', min: 8.30, max: 99,   cls: 'v-new' },
    { label: '8.28–29', min: 8.28, max: 8.30, cls: 'v-new' },
    { label: '8.25–27', min: 8.25, max: 8.28, cls: 'v-mid' },
    { label: '8.23–24', min: 8.23, max: 8.25, cls: 'v-mid' },
    { label: '< 8.23',  min: 8.17, max: 8.23, cls: 'v-old' },
    { label: '< 8.17',  min: 0,    max: 8.17, cls: 'v-old' },
  ]
  return buckets.map(b => {
    const count = customers.value.filter(c => {
      if (!c.prod_version) return false
      const v = parseFloat(c.prod_version.replace('-R', ''))
      return !isNaN(v) && v >= b.min && v < b.max
    }).length
    return { ...b, count, pct: Math.round(count / total * 100) }
  }).filter(b => b.count > 0)
})

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

function limitColor(c: Customer) {
  if (c.upgrades_used >= c.upgrades_limit) return 'color:var(--red);font-weight:700'
  if (c.upgrades_used >= c.upgrades_limit * 0.7) return 'color:var(--amber)'
  return 'color:var(--green)'
}
</script>
