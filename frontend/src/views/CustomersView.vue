<template>
  <div class="view">
    <div class="sh">
      <div><h2>Customer Intelligence</h2><p>Every customer · full context · click to open 360 view</p></div>
      <div style="display:flex;gap:6px">
        <RouterLink to="/customers/comms" class="btn btn-g btn-sm" style="text-decoration:none">📢 Customer Comms</RouterLink>
        <button class="btn btn-g btn-sm" @click="showDiscovery = true">🔍 Discover Tenants</button>
        <button class="btn btn-g btn-sm" @click="showExport = true">⭳ Export</button>
        <button class="btn btn-g btn-sm">Import CSV</button>
        <button class="btn" @click="toggleAddForm">{{ showAddForm ? '✕ Cancel' : '+ Add Customer' }}</button>
      </div>
    </div>

    <TenantDiscoveryModal :open="showDiscovery" @close="showDiscovery = false" />
    <CustomerExportModal
      :open="showExport"
      :customer-ids="exportCustomerIds"
      v-model:sort-key="exportSortKey"
      v-model:sort-dir="exportSortDir"
      @close="showExport = false"
    />

    <!-- Add Customer Form -->
    <div v-if="showAddForm" style="background:var(--surface2);border:1px solid var(--border2);border-radius:9px;padding:14px 16px;margin-bottom:16px">
      <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">New Customer</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Name *</label>
          <input class="inp" style="width:200px" placeholder="Acme Shipping Ltd" v-model="newCustomer.name" @input="confirmedDuplicate = false">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Tier</label>
          <select class="sel" v-model="newCustomer.tier">
            <option>Premier</option>
            <option>Strategic</option>
            <option>Scale</option>
          </select>
          <span style="font-size:8.5px;color:var(--text3)">{{ tierUpgradeLimit(newCustomer.tier) }} upgrades/yr</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">CSM *</label>
          <input class="inp" style="width:100px" placeholder="Asaph" v-model="newCustomer.csm">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">ARR (GBP)</label>
          <input class="inp" type="number" style="width:90px" placeholder="50000" v-model.number="newCustomer.arr_gbp">
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Infra</label>
          <select class="sel" style="width:80px" v-model="newCustomer.infra">
            <option>Old</option>
            <option>New</option>
            <option>Mixed</option>
          </select>
        </div>
        <div style="display:flex;flex-direction:column;gap:3px">
          <label style="font-size:9px;color:var(--text3)">Prod Version</label>
          <input class="inp" style="width:100px" placeholder="8.30.0-R" v-model="newCustomer.prod_version">
        </div>
        <button class="btn"
          :disabled="!newCustomer.name || !newCustomer.csm || creatingCustomer || (!!duplicateMatch && !confirmedDuplicate)"
          @click="addCustomer">
          {{ creatingCustomer ? 'Adding…' : (duplicateMatch && !confirmedDuplicate) ? 'Name already exists' : 'Add' }}
        </button>
      </div>
      <div v-if="duplicateMatch && !confirmedDuplicate" class="alert-bar" style="margin-top:10px;display:flex;align-items:center;gap:10px;font-size:11px">
        ⚠ A customer named "{{ duplicateMatch.name }}" already exists ({{ duplicateMatch.tier }}, CSM {{ duplicateMatch.csm }}) — likely the same one, not a new customer.
        <button class="btn btn-g btn-sm" style="margin-left:auto" @click="confirmedDuplicate = true">Add anyway</button>
      </div>
    </div>

    <!-- Infrastructure Strip — replaced the old ARR-denominated strip.
         All 4 cards are scoped to real VMS customers (product ILIKE '%VMS%'),
         not the full active-customer list — confirmed live that `infra` is
         a leftover/default field on non-VMS accounts too (533 of 558 active
         customers show infra="Old", but only 53 of those are actually VMS
         customers with real AWS infrastructure to migrate at all). Version
         data (CustomerTenantInfo, since Customer.prod_version is fake seed
         data) is real but sparse, so it's reported with an honest "of known"
         subtitle rather than pretending fleet-wide coverage. -->
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:16px">
      <div class="sc alert" style="cursor:pointer" @click="filterInfra = 'Old'; vmsOnly = true" title="Filter the list to Old infra, VMS customers only">
        <div class="lbl">On Old Infra</div>
        <div class="val">{{ stats?.vms_old_infra_count ?? '—' }}</div>
        <div class="sub">of {{ stats?.vms_customer_count ?? 0 }} VMS customers still to migrate</div>
      </div>
      <RouterLink to="/operations?tab=migrations" class="sc" style="text-decoration:none;color:inherit;display:block">
        <div class="lbl">Migration In Progress</div>
        <div class="val">{{ stats?.migration_active_count ?? '—' }}</div>
        <div class="sub">active migration projects, VMS customers</div>
      </RouterLink>
      <RouterLink to="/operations?tab=migrations" class="sc warn" style="text-decoration:none;color:inherit;display:block">
        <div class="lbl">Stalled Migrations</div>
        <div class="val">{{ stats?.stalled_migration_count ?? '—' }}</div>
        <div class="sub">VMS customers, no movement, needs a nudge</div>
      </RouterLink>
      <RouterLink to="/releases" class="sc warn" style="text-decoration:none;color:inherit;display:block" title="See Release Intelligence's Customers Below This Version panel">
        <div class="lbl">Confirmed Outdated</div>
        <div class="val">{{ stats?.confirmed_outdated_count ?? '—' }}</div>
        <div class="sub">of {{ stats?.tenant_known_count ?? 0 }} of {{ stats?.vms_customer_count ?? 0 }} VMS customers with known version data</div>
      </RouterLink>
    </div>

    <div class="tw">
      <div class="ttb">
        <input class="inp" style="width:190px" placeholder="Search customers..." v-model="search">
        <select class="sel" v-model="filterTier">
          <option value="">All tiers</option>
          <option>Premier</option>
          <option>Strategic</option>
          <option>Scale</option>
        </select>
        <select class="sel" v-model="filterCsm">
          <option value="">All CSMs</option>
          <option v-for="csm in csms" :key="csm">{{ csm }}</option>
        </select>
        <select class="sel" v-model="filterInfra">
          <option value="">All infra</option>
          <option>Old</option>
          <option>New</option>
          <option>Mixed</option>
        </select>
        <select class="sel" v-model="filterHealth">
          <option value="">All health</option>
          <option value="red">Red (&lt;45)</option>
          <option value="amber">Amber (45–70)</option>
          <option value="green">Green (&gt;70)</option>
        </select>
        <select class="sel" v-model="filterEngagement" title="Real last-support-case date, refreshed weekly from live Jira">
          <option value="">All engagement</option>
          <option value="quiet">Quiet (6mo+)</option>
          <option value="dormant">Dormant (12mo+)</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text2);white-space:nowrap;cursor:pointer" title="Hides Email-only, CompassAir-only, and no-product-tagged customers — everyone whose product tag doesn't include VMS">
          <input type="checkbox" v-model="vmsOnly">
          VMS customers only
        </label>
      </div>
      <table>
        <thead>
          <tr>
            <th v-for="col in columns" :key="col.key" class="sortable" @click="toggleSort(col.key)">
              {{ col.label }}<span class="sort-arrow" v-if="sortKey === col.key">{{ sortDir === 1 ? '▲' : '▼' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in sorted" :key="c.id" class="cust-row" @click="openCustomer(c.id)">
            <td>
              <div class="hc-mini">
                <div :class="['health-dot', healthDot(c.health_score)]"></div>
                <span class="hc-score" :style="healthColor(c.health_score)">{{ c.health_score }}</span>
              </div>
            </td>
            <td class="td-name">
              {{ c.name }}
              <span v-if="c.jvm_client" class="jvm-badge" title="Still on the old Java desktop client, not the web app">JVM</span>
              <span
                v-if="engagementTier(c.last_case_activity_at)"
                :class="['dormant-badge', engagementTier(c.last_case_activity_at)]"
                :title="c.last_case_activity_at ? `Last case: ${formatRenewal(c.last_case_activity_at)}` : 'No case on record'"
              >{{ engagementTier(c.last_case_activity_at) === 'dormant' ? 'Dormant' : 'Quiet' }}</span>
            </td>
            <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
            <td>{{ c.csm }}</td>
            <td>{{ planName(c.tier) }}</td>
            <td class="vm" :style="versionColor(c.prod_version)">{{ c.prod_version ?? '—' }}</td>
            <td><span :class="['infra-badge', infraClass(c.infra)]">{{ c.infra }}</span></td>
            <td :style="daysSinceColor(daysSinceUpgrade(c.id))">{{ daysSinceLabel(c.id) }}</td>
            <td>
              <div class="ub">
                <div class="bt"><div :class="['bf', upgradeBarClass(c)]" :style="{ width: upgradeBarWidth(c) }"></div></div>
                <span style="font-size:9px" :style="upgradeUsageColor(c)">{{ c.upgrades_used }}/{{ c.upgrades_limit }}</span>
              </div>
            </td>
            <td :style="renewalColor(c.renewal_date)">{{ formatRenewal(c.renewal_date) }}</td>
            <td>{{ openCasesFor(c.id) }}</td>
            <td><span :style="migStyle(c.id)">{{ migStatus(c.id) }}</span></td>
          </tr>
          <tr v-if="loading">
            <td colspan="12" style="text-align:center;color:var(--text3);padding:20px">Loading customers…</td>
          </tr>
          <tr v-else-if="!filtered.length">
            <td colspan="12" style="text-align:center;color:var(--text3);padding:20px">No customers match filters.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api, planName, engagementTier, type Customer, type CustomerStats, type Upgrade, type MigrationProject } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import TenantDiscoveryModal from '@/components/TenantDiscoveryModal.vue'
import CustomerExportModal from '@/components/CustomerExportModal.vue'

const showDiscovery = ref(false)
const showExport = ref(false)
// The export's own sort — defaults to whatever's currently on screen, but
// stays independent of it so choosing a different export order doesn't
// re-sort the live table underneath the user.
const exportSortKey = ref<SortKey>('name')
const exportSortDir = ref<1 | -1>(1)
watch(showExport, (open) => {
  if (open) {
    exportSortKey.value = sortKey.value
    exportSortDir.value = sortDir.value
  }
})

const { openCustomer } = useCustomerDrill()

const customers = ref<Customer[]>([])
// Real, live-Jira open-case count per customer_id — replaced the old
// allCases-based local-table count (see openCasesFor() below).
const openCaseCounts = ref<Record<number, number>>({})
const allUpgrades = ref<Upgrade[]>([])
const allMigrations = ref<MigrationProject[]>([])
const stats = ref<CustomerStats | null>(null)
const loading = ref(true)

const search = ref('')
const filterTier = ref('')
const filterCsm = ref('')
const filterInfra = ref('')
const filterHealth = ref('')
const filterEngagement = ref('')
// Default ON — confirmed live (2026-09-01) that hiding only Email-only
// customers still left 239 visible (126 CompassAir-only, 30 with no
// product tag at all, only 81 genuinely VMS) — real clutter for
// VMS-specific contact/migration work either way. Shows only customers
// whose `product` includes "VMS" in any combo (e.g. "Email, VMS").
const vmsOnly = ref(true)

const showAddForm = ref(false)
const creatingCustomer = ref(false)
const newCustomer = ref({ name: '', tier: 'Strategic', csm: '', arr_gbp: 0, infra: 'Old', prod_version: '' })

// Soft warning, not a hard block — real companies can legitimately share a
// near-identical rendered name (Ltd vs Limited, a subsidiary), so this asks
// rather than prevents. Catches the accidental-duplicate class of mistake
// (the real Harren/Oslo duplicate-customer incident this session) without
// blocking a genuine edge case.
const confirmedDuplicate = ref(false)
const duplicateMatch = computed(() => {
  const name = newCustomer.value.name.trim().toLowerCase()
  if (!name) return null
  return customers.value.find(c => c.name.trim().toLowerCase() === name) ?? null
})

// Real Dataloy plan allowances (dataloy-systems.com/plans) — Scale=Starter,
// Strategic=Professional, Premier=Enterprise. The backend enforces this on
// create/update regardless of what's sent; this is just for the live label.
function tierUpgradeLimit(tier: string): number {
  return tier === 'Premier' ? 12 : tier === 'Strategic' ? 8 : 4
}

onMounted(async () => {
  // Not part of the Promise.all below, deliberately — real_open_counts_by_
  // customer() is a live-Jira aggregate (cheap once team_open_stats()'s
  // cache is warm, but a real cold fetch otherwise) and shouldn't hold up
  // the rest of this page (names/tiers/ARR) rendering while it resolves.
  api.customers.openCaseCounts()
    .then(res => { openCaseCounts.value = res.data.counts })
    .catch(() => { openCaseCounts.value = {} })

  try {
    const [custRes, statsRes, upgRes, migRes] = await Promise.all([
      api.customers.list(),
      api.customers.stats(),
      api.upgrades.list(),
      api.migrations.list(),
    ])
    customers.value = custRes.data
    stats.value = statsRes.data
    allUpgrades.value = upgRes.data
    allMigrations.value = migRes.data
  } finally {
    loading.value = false
  }
})

const csms = computed(() => [...new Set(customers.value.map(c => c.csm))].sort())

const filtered = computed(() =>
  customers.value.filter(c => {
    if (search.value && !c.name.toLowerCase().includes(search.value.toLowerCase())) return false
    if (filterTier.value && c.tier !== filterTier.value) return false
    if (filterCsm.value && c.csm !== filterCsm.value) return false
    if (filterInfra.value && c.infra !== filterInfra.value) return false
    if (filterHealth.value === 'red' && c.health_score > 45) return false
    if (filterHealth.value === 'amber' && (c.health_score <= 45 || c.health_score > 70)) return false
    if (filterHealth.value === 'green' && c.health_score <= 70) return false
    if (filterEngagement.value && engagementTier(c.last_case_activity_at) !== filterEngagement.value) return false
    // Show only real VMS customers — anyone whose product tag doesn't
    // contain "VMS" (Email-only, CompassAir-only, or untagged) is hidden;
    // a mixed tag like "Email, VMS" still counts as a real VMS customer.
    if (vmsOnly.value && !(c.product ?? '').toLowerCase().includes('vms')) return false
    return true
  })
)

const migMap = computed(() => {
  const m: Record<number, MigrationProject> = {}
  for (const mg of allMigrations.value) m[mg.customer_id] = mg
  return m
})

// Column sorting — click a header to sort by it, click again to flip
// direction. Each column gets a real comparator matched to its actual data
// (tier/package by rank not alphabet, version by numeric parts not a naive
// parseFloat — the same "8.30 < 8.9" bug already flagged elsewhere in this
// app — dates/numbers with nulls always sorting to the end).
type SortKey = 'health' | 'name' | 'tier' | 'csm' | 'package' | 'prod_version' | 'infra' | 'days_since_upgrade' | 'upgrades' | 'renewal' | 'open_cases' | 'migration'
const columns: { key: SortKey; label: string }[] = [
  { key: 'health', label: 'Health' },
  { key: 'name', label: 'Customer' },
  { key: 'tier', label: 'Tier' },
  { key: 'csm', label: 'CSM' },
  { key: 'package', label: 'Package' },
  { key: 'prod_version', label: 'Prod Version' },
  { key: 'infra', label: 'Infra' },
  { key: 'days_since_upgrade', label: 'Days Since Upgrade' },
  { key: 'upgrades', label: 'Upgrades' },
  { key: 'renewal', label: 'Renewal' },
  { key: 'open_cases', label: 'Open Cases' },
  { key: 'migration', label: 'Migration' },
]
const sortKey = ref<SortKey>('name')
const sortDir = ref<1 | -1>(1)
function toggleSort(key: SortKey) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 1 ? -1 : 1
  else { sortKey.value = key; sortDir.value = 1 }
}

const tierRankMap: Record<string, number> = { Premier: 0, Strategic: 1, Scale: 2 }
function tierRank(tier?: string | null) {
  return tier != null && tier in tierRankMap ? tierRankMap[tier] : 99
}
const infraRankMap: Record<string, number> = { Old: 0, Mixed: 1, New: 2 }
function infraRank(infra?: string | null) {
  return infra != null && infra in infraRankMap ? infraRankMap[infra] : 99
}
function versionTuple(v?: string | null): number[] {
  const nums = v?.match(/\d+/g)
  return nums ? nums.map(Number) : []
}
function compareVersions(a?: string | null, b?: string | null): number {
  const ta = versionTuple(a), tb = versionTuple(b)
  if (!ta.length || !tb.length) return (ta.length ? 0 : 1) - (tb.length ? 0 : 1)
  for (let i = 0; i < Math.max(ta.length, tb.length); i++) {
    const d = (ta[i] ?? 0) - (tb[i] ?? 0)
    if (d !== 0) return d
  }
  return 0
}
function compareNullableNumber(a: number | null | undefined, b: number | null | undefined): number {
  if (a == null || b == null) return (a == null ? 1 : 0) - (b == null ? 1 : 0)
  return a - b
}
function compareNullableDate(a?: string | null, b?: string | null): number {
  if (!a || !b) return (a ? 0 : 1) - (b ? 0 : 1)
  return new Date(a).getTime() - new Date(b).getTime()
}

function compareCustomers(key: SortKey, a: Customer, b: Customer): number {
  switch (key) {
    case 'health': return a.health_score - b.health_score
    case 'name': return a.name.localeCompare(b.name)
    case 'tier': return tierRank(a.tier) - tierRank(b.tier)
    case 'csm': return (a.csm || '').localeCompare(b.csm || '')
    case 'package': return tierRank(a.tier) - tierRank(b.tier)
    case 'prod_version': return compareVersions(a.prod_version, b.prod_version)
    case 'infra': return infraRank(a.infra) - infraRank(b.infra)
    case 'days_since_upgrade': return compareNullableNumber(daysSinceUpgrade(a.id), daysSinceUpgrade(b.id))
    case 'upgrades': {
      const pa = a.upgrades_limit ? a.upgrades_used / a.upgrades_limit : 0
      const pb = b.upgrades_limit ? b.upgrades_used / b.upgrades_limit : 0
      return pa - pb
    }
    case 'renewal': return compareNullableDate(a.renewal_date, b.renewal_date)
    case 'open_cases': return compareNullableNumber(openCaseCounts.value[a.id], openCaseCounts.value[b.id])
    case 'migration': return migStatus(a.id).localeCompare(migStatus(b.id))
    default: return 0
  }
}

const sorted = computed(() => [...filtered.value].sort((a, b) => sortDir.value * compareCustomers(sortKey.value, a, b)))

// Same filtered set as the live table, but ordered by the export modal's
// own chosen column/direction rather than whatever's currently on screen.
const exportCustomerIds = computed(() =>
  [...filtered.value].sort((a, b) => exportSortDir.value * compareCustomers(exportSortKey.value, a, b)).map(c => c.id)
)

function openCasesFor(id: number) {
  return openCaseCounts.value[id] ?? '—'
}

function migStatus(id: number): string {
  return migMap.value[id]?.stage ?? '—'
}

function migStyle(id: number): string {
  const stage = migMap.value[id]?.stage
  if (!stage) return 'color:var(--text3);font-size:10px'
  if (stage === 'Complete') return 'color:var(--green);font-weight:700;font-size:10px'
  if (stage === 'In Progress') return 'color:var(--teal);font-weight:700;font-size:10px'
  return 'color:var(--text3);font-size:10px'
}

function toggleAddForm() {
  showAddForm.value = !showAddForm.value
  if (showAddForm.value) {
    newCustomer.value = { name: '', tier: 'Strategic', csm: '', arr_gbp: 0, infra: 'Old', prod_version: '' }
    confirmedDuplicate.value = false
  }
}

async function addCustomer() {
  if (!newCustomer.value.name || !newCustomer.value.csm) return
  creatingCustomer.value = true
  try {
    const res = await api.customers.create({
      name: newCustomer.value.name,
      tier: newCustomer.value.tier,
      csm: newCustomer.value.csm,
      arr_gbp: newCustomer.value.arr_gbp || 0,
      infra: newCustomer.value.infra,
      prod_version: newCustomer.value.prod_version || null,
    })
    customers.value.unshift(res.data)
    const statsRes = await api.customers.stats()
    stats.value = statsRes.data
    showAddForm.value = false
  } catch { /* ignore */ } finally {
    creatingCustomer.value = false
  }
}

function formatRenewal(d?: string | null) {
  if (!d) return '—'
  const dt = new Date(d)
  return dt.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}

function renewalColor(d?: string | null) {
  if (!d) return ''
  const days = (new Date(d).getTime() - Date.now()) / 86400000
  if (days < 60) return 'color:var(--red);font-weight:700'
  if (days < 120) return 'color:var(--amber)'
  return 'color:var(--green)'
}

function healthDot(score: number) {
  return score > 70 ? 'hg' : score > 45 ? 'ha' : 'hr'
}
function healthColor(score: number) {
  return score > 70 ? 'color:var(--green)' : score > 45 ? 'color:var(--amber)' : 'color:var(--red)'
}
function tierClass(tier?: string | null) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
function infraClass(infra: string) {
  return infra === 'New' ? 'in' : infra === 'Old' ? 'io' : 'im'
}

function versionColor(v?: string | null) {
  if (!v) return ''
  const num = parseFloat(v.replace('-R', ''))
  if (num < 8.23) return 'color:var(--red)'
  if (num < 8.27) return 'color:var(--amber)'
  return ''
}
function upgradeUsageColor(c: Customer) {
  if (c.upgrades_used >= c.upgrades_limit) return 'color:var(--red)'
  if (c.upgrades_used > c.upgrades_limit * 0.7) return 'color:var(--amber)'
  return 'color:var(--text3)'
}

function upgradeBarClass(c: Customer) {
  if (c.upgrades_used >= c.upgrades_limit) return 'da'
  if (c.upgrades_used >= c.upgrades_limit * 0.7) return 'wa'
  return ''
}

function upgradeBarWidth(c: Customer) {
  if (!c.upgrades_limit) return '0%'
  return `${Math.min(100, Math.round(c.upgrades_used / c.upgrades_limit * 100))}%`
}

function daysSinceUpgrade(customerId: number): number | null {
  const done = allUpgrades.value
    .filter(u => u.customer_id === customerId && u.stage === 'Verified Done' && u.environment === 'PROD' && u.date_done)
    .sort((a, b) => new Date(b.date_done!).getTime() - new Date(a.date_done!).getTime())
  if (!done.length) return null
  return Math.floor((Date.now() - new Date(done[0].date_done!).getTime()) / 86400000)
}

function daysSinceLabel(customerId: number) {
  const d = daysSinceUpgrade(customerId)
  return d == null ? 'Never' : `${d}d`
}

function daysSinceColor(days: number | null) {
  if (days == null) return 'color:var(--text3)'
  if (days > 365) return 'color:var(--red)'
  if (days > 90) return 'color:var(--amber)'
  return 'color:var(--green)'
}
</script>

<style scoped>
.cust-row { cursor: pointer; }
</style>
