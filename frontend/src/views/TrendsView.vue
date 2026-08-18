<template>
  <div class="view">
    <div class="sh">
      <div><h2>Trends & Fleet Health</h2><p>Derived intelligence · revenue-weighted · feeds management summary</p></div>
      <button class="btn btn-g btn-sm">Export Summary</button>
    </div>

    <div class="stats-row sr-5" v-if="loaded">
      <div class="sc alert">
        <div class="lbl">No Upgrade 12mo+</div>
        <div class="val">{{ noUpgrade12m.length }}</div>
        <div class="sub">{{ formatArr(noUpgrade12mArr) }} ARR</div>
      </div>
      <div class="sc alert">
        <div class="lbl">ARR — Red Health</div>
        <div class="val">{{ formatArr(stats?.arr_red_health) }}</div>
        <div class="sub">{{ stats?.red_health_count ?? '—' }} customers</div>
      </div>
      <div class="sc warn">
        <div class="lbl">At Upgrade Limit</div>
        <div class="val">{{ atLimit.length }}</div>
        <div class="sub">{{ formatArr(atLimitArr) }} ARR</div>
      </div>
      <div class="sc good">
        <div class="lbl">Migration Rate</div>
        <div class="val">{{ migrationRate }}%</div>
        <div class="sub">{{ migratedCount }} / {{ totalCustomers }} migrated</div>
      </div>
      <div class="sc info">
        <div class="lbl">SLA Breaching</div>
        <div class="val">{{ triage?.sla_breaching ?? '—' }}</div>
        <div class="sub">active today</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:4px">
      <!-- No upgrade 12m+ -->
      <div>
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">No Upgrade in 12+ Months</div>
        <div v-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div class="tw" v-if="noUpgrade12m.length">
          <table>
            <thead>
              <tr><th>Customer</th><th>Tier</th><th>Version</th><th>ARR</th><th>Last Upgrade</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in noUpgrade12m" :key="c.id">
                <td class="td-name">{{ c.name }}</td>
                <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
                <td class="vm" style="color:var(--red)">{{ c.prod_version ?? '—' }}</td>
                <td>{{ formatArr(c.arr_gbp) }}</td>
                <td style="color:var(--text3);font-size:10px">{{ lastUpgrade(c.id) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else-if="!loading" style="color:var(--text3);font-size:11px;padding:8px 0">All customers upgraded within 12 months.</div>
      </div>

      <!-- At upgrade limit -->
      <div>
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">Approaching / At Upgrade Limit</div>
        <div v-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div class="tw" v-if="atLimitOrNear.length">
          <table>
            <thead>
              <tr><th>Customer</th><th>Tier</th><th>ARR</th><th>Used / Limit</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in atLimitOrNear" :key="c.id">
                <td class="td-name">{{ c.name }}</td>
                <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
                <td>{{ formatArr(c.arr_gbp) }}</td>
                <td>
                  <span :style="limitColor(c)">{{ c.upgrades_used }} / {{ c.upgrades_limit }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else-if="!loading" style="color:var(--text3);font-size:11px;padding:8px 0">No customers near upgrade limit.</div>

        <!-- Version distribution -->
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px;margin-top:18px">Version Distribution</div>
        <div v-for="[version, count] in versionDist" :key="version" style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <div style="font-size:10px;color:var(--text2);width:80px;font-variant-numeric:tabular-nums">{{ version }}</div>
          <div style="flex:1;background:var(--surface2);border-radius:2px;height:6px;overflow:hidden">
            <div :style="{ width: `${count / customers.length * 100}%`, background: versionBarColor(version) }" style="height:100%;border-radius:2px;transition:width .4s"></div>
          </div>
          <div style="font-size:10px;font-weight:700;color:var(--text);width:16px;text-align:right">{{ count }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type Customer, type CustomerStats, type TriageStats, type Upgrade } from '@/api/client'

const customers = ref<Customer[]>([])
const upgrades = ref<Upgrade[]>([])
const stats = ref<CustomerStats | null>(null)
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
    stats.value = statRes.data
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

function lastUpgrade(id: number) {
  const d = lastUpgradeDateFor(id)
  if (!d) return 'Never'
  return d.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}

const noUpgrade12m = computed(() =>
  customers.value.filter(c => {
    const last = lastUpgradeDateFor(c.id)
    return !last || last < cutoff12m
  })
)

const noUpgrade12mArr = computed(() => noUpgrade12m.value.reduce((a, c) => a + c.arr_gbp, 0))

const atLimit = computed(() => customers.value.filter(c => c.upgrades_used >= c.upgrades_limit))
const atLimitArr = computed(() => atLimit.value.reduce((a, c) => a + c.arr_gbp, 0))
const atLimitOrNear = computed(() => customers.value.filter(c => c.upgrades_used >= Math.floor(c.upgrades_limit * 0.7)))

const totalCustomers = computed(() => customers.value.length)

const migratedCount = computed(() =>
  customers.value.filter(c => c.infra === 'New').length
)

const migrationRate = computed(() => {
  if (!totalCustomers.value) return 0
  return Math.round(migratedCount.value / totalCustomers.value * 100)
})

const versionDist = computed((): [string, number][] => {
  const dist: Record<string, number> = {}
  customers.value.forEach(c => {
    const v = c.prod_version ?? 'Unknown'
    dist[v] = (dist[v] ?? 0) + 1
  })
  return Object.entries(dist).sort((a, b) => b[0].localeCompare(a[0]))
})

function versionBarColor(v: string) {
  const num = parseFloat(v.replace('-R', ''))
  if (isNaN(num)) return 'var(--text3)'
  if (num < 8.23) return 'var(--red)'
  if (num < 8.27) return 'var(--amber)'
  return 'var(--green)'
}

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
