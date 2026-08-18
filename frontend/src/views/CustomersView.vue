<template>
  <div class="view">
    <div class="sh">
      <div><h2>Customer Intelligence</h2><p>Every customer · full context · click to open 360 view</p></div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-g btn-sm">Import CSV</button>
        <button class="btn">+ Add Customer</button>
      </div>
    </div>

    <!-- ARR Risk Strip -->
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:16px">
      <div class="sc alert">
        <div class="lbl">ARR on Old Infra</div>
        <div class="val">{{ formatArr(stats?.arr_old_infra) }}</div>
        <div class="sub">{{ stats?.old_infra_count ?? '—' }} customers</div>
      </div>
      <div class="sc alert">
        <div class="lbl">ARR — Red Health</div>
        <div class="val">{{ formatArr(stats?.arr_red_health) }}</div>
        <div class="sub">{{ stats?.red_health_count ?? '—' }} customers</div>
      </div>
      <div class="sc warn">
        <div class="lbl">ARR at Renewal Risk</div>
        <div class="val">{{ formatArr(stats?.arr_renewal_risk) }}</div>
        <div class="sub">renewing within 60d</div>
      </div>
      <div class="sc warn">
        <div class="lbl">Total ARR</div>
        <div class="val">{{ formatArr(totalArr) }}</div>
        <div class="sub">{{ stats?.total ?? '—' }} customers</div>
      </div>
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
      </div>
      <table>
        <thead>
          <tr>
            <th>Health</th><th>Customer</th><th>Tier</th><th>CSM</th><th>ARR</th>
            <th>Prod Version</th><th>Infra</th><th>Open Cases</th><th>Renewal</th><th>Migration</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in filtered" :key="c.id" @click="openPanel(c)">
            <td>
              <div class="hc-mini">
                <div :class="['health-dot', healthDot(c.health_score)]"></div>
                <span class="hc-score" :style="healthColor(c.health_score)">{{ c.health_score }}</span>
              </div>
            </td>
            <td class="td-name">{{ c.name }}</td>
            <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
            <td>{{ c.csm }}</td>
            <td>{{ formatArr(c.arr_gbp) }}</td>
            <td class="vm" :style="versionColor(c.prod_version)">{{ c.prod_version ?? '—' }}</td>
            <td><span :class="['infra-badge', infraClass(c.infra)]">{{ c.infra }}</span></td>
            <td>{{ openCasesFor(c.id) }}</td>
            <td :style="renewalColor(c.renewal_date)">{{ formatRenewal(c.renewal_date) }}</td>
            <td><span :class="migClass(c.id)">{{ migStatus(c.id) }}</span></td>
          </tr>
          <tr v-if="loading">
            <td colspan="10" style="text-align:center;color:var(--text3);padding:20px">Loading customers…</td>
          </tr>
          <tr v-else-if="!filtered.length">
            <td colspan="10" style="text-align:center;color:var(--text3);padding:20px">No customers match filters.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Customer Detail Panel -->
    <div :class="['overlay', panelOpen ? 'open' : '']" @click="closePanel"></div>
    <div :class="['dp', panelOpen ? 'open' : '']" v-if="selected">
      <div class="dp-h" style="position:relative">
        <button class="cbx" @click="closePanel">✕</button>
        <h3>{{ selected.name }}</h3>
        <div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap">
          <span :class="['tier-badge', tierClass(selected.tier)]">{{ selected.tier }}</span>
          <span :class="['infra-badge', infraClass(selected.infra)]">{{ selected.infra }} Infra</span>
          <span style="font-size:10px;color:var(--text3)">{{ selected.csm }} · {{ formatArr(selected.arr_gbp) }}</span>
        </div>
        <div style="margin-top:6px;display:flex;gap:6px;align-items:center">
          <div :class="['health-dot', healthDot(selected.health_score)]"></div>
          <span style="font-size:11px;font-weight:700" :style="healthColor(selected.health_score)">Health {{ selected.health_score }}/100</span>
          <span style="font-size:10px;color:var(--text3)">·</span>
          <span style="font-size:10px" :style="churnColor(selected.churn_risk)">Churn risk: {{ selected.churn_risk }}</span>
          <span style="font-size:10px;color:var(--text3)">· Renews: {{ formatRenewal(selected.renewal_date) }}</span>
          <span style="font-size:10px" :style="sentimentColor(selected.sentiment)">· {{ selected.sentiment }}</span>
        </div>
      </div>
      <div class="dp-tabs">
        <div v-for="tab in tabs" :key="tab.id" :class="['dt', activeTab === tab.id ? 'active' : '']" @click="activeTab = tab.id">{{ tab.label }}</div>
      </div>
      <div class="dp-body">
        <!-- Overview -->
        <div v-if="activeTab === 'overview'">
          <div class="ds"><h4>Commercial</h4>
            <div class="fg">
              <div class="fr">Product <span style="color:var(--text)">{{ selected.product }}</span></div>
              <div class="fr">Plan <span style="color:var(--text)">{{ selected.plan }}</span></div>
              <div class="fr">Region <span style="color:var(--text)">{{ selected.region }}</span></div>
              <div class="fr">Timezone <span style="color:var(--text)">{{ selected.timezone }}</span></div>
              <div class="fr">Contacts <span style="color:var(--text)">{{ selected.contacts }}</span></div>
              <div class="fr">SLA <span style="color:var(--text)">{{ selected.sla_tier }}</span></div>
              <div class="fr">Seats <span style="color:var(--text)">{{ selected.seats }}</span></div>
              <div class="fr">SSO <span style="color:var(--text)">{{ selected.sso }}</span></div>
              <div class="fr">Integrations <span :style="selected.integrations !== 'None' ? 'color:var(--amber)' : ''">{{ selected.integrations }}</span></div>
              <div class="fr">API Customer <span :style="selected.api_customer ? 'color:var(--green);font-weight:700' : 'color:var(--text3)'">{{ selected.api_customer ? 'YES' : 'No' }}</span></div>
              <div class="fr">Upgrades Used <span :style="upgradeUsageColor(selected)">{{ selected.upgrades_used }}/{{ selected.upgrades_limit }}</span></div>
              <div class="fr">WildFly 8 <span :style="selected.wildfly8 ? 'color:var(--amber);font-weight:700' : 'color:var(--text3)'">{{ selected.wildfly8 ? 'Active — check after migration' : 'No' }}</span></div>
            </div>
          </div>
          <div class="ds"><h4>Scheduling Preferences</h4>
            <div class="fg">
              <div class="fr">Preferred days <span style="color:var(--text)">{{ selected.pref_days }}</span></div>
              <div class="fr">Notice required <span style="color:var(--text)">{{ selected.notice_required }}</span></div>
              <div class="fr">Blackout periods <span :style="selected.blackout_periods && selected.blackout_periods !== 'None' ? 'color:var(--amber)' : ''">{{ selected.blackout_periods }}</span></div>
            </div>
          </div>
        </div>

        <!-- Cases tab -->
        <div v-if="activeTab === 'cases'">
          <div class="info-bar">Jira links — local status tracked here.</div>
          <div v-if="customerCases.length === 0" style="color:var(--text3);font-size:11px;padding:8px 0">No cases linked.</div>
          <div v-for="c in customerCases" :key="c.id" class="jr">
            <span class="jref">↗ {{ c.jira_ref }}</span>
            <div style="flex:1">
              <div class="jtitle">{{ c.title }}</div>
              <div v-if="c.defect_status" style="font-size:9px;color:var(--amber);margin-top:2px">Dev: {{ c.defect_status }}</div>
              <div v-if="c.root_cause" style="font-size:9px;color:var(--purple);margin-top:2px">Root cause: {{ c.root_cause }}</div>
            </div>
            <span :class="['env-badge', envClass(c.environment)]">{{ c.environment }}</span>
            <span class="jst" :style="c.status.includes('Awaiting') ? 'color:var(--amber)' : ''">{{ c.status }}</span>
            <span style="font-size:9px;color:var(--text3)">{{ c.days_open }}d</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type Customer, type Case, type CustomerStats } from '@/api/client'

const customers = ref<Customer[]>([])
const allCases = ref<Case[]>([])
const stats = ref<CustomerStats | null>(null)
const loading = ref(true)

const search = ref('')
const filterTier = ref('')
const filterCsm = ref('')
const filterInfra = ref('')
const filterHealth = ref('')

const panelOpen = ref(false)
const selected = ref<Customer | null>(null)
const activeTab = ref('overview')

const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'cases', label: 'Cases' },
  { id: 'upgrades', label: 'Upgrades' },
  { id: 'migration', label: 'Migration' },
]

onMounted(async () => {
  try {
    const [custRes, casesRes, statsRes] = await Promise.all([
      api.customers.list(),
      api.cases.list(),
      api.customers.stats(),
    ])
    customers.value = custRes.data
    allCases.value = casesRes.data
    stats.value = statsRes.data
  } finally {
    loading.value = false
  }
})

const csms = computed(() => [...new Set(customers.value.map(c => c.csm))].sort())

const totalArr = computed(() => customers.value.reduce((a, c) => a + c.arr_gbp, 0))

const filtered = computed(() =>
  customers.value.filter(c => {
    if (search.value && !c.name.toLowerCase().includes(search.value.toLowerCase())) return false
    if (filterTier.value && c.tier !== filterTier.value) return false
    if (filterCsm.value && c.csm !== filterCsm.value) return false
    if (filterInfra.value && c.infra !== filterInfra.value) return false
    if (filterHealth.value === 'red' && c.health_score > 45) return false
    if (filterHealth.value === 'amber' && (c.health_score <= 45 || c.health_score > 70)) return false
    if (filterHealth.value === 'green' && c.health_score <= 70) return false
    return true
  })
)

const customerCases = computed(() =>
  selected.value ? allCases.value.filter(c => c.customer_id === selected.value!.id) : []
)

function openCasesFor(id: number) {
  const n = allCases.value.filter(c => c.customer_id === id).length
  return n || '0'
}

function migStatus(id: number): string {
  return '—'
}
function migClass(id: number): string {
  return ''
}

function openPanel(c: Customer) {
  selected.value = c
  activeTab.value = 'overview'
  panelOpen.value = true
}
function closePanel() {
  panelOpen.value = false
}

function formatArr(v?: number | null) {
  if (v == null) return '—'
  if (v >= 1_000_000) return `£${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `£${(v / 1_000).toFixed(0)}K`
  return `£${v.toLocaleString()}`
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
function churnColor(risk: string) {
  return risk === 'High' || risk === 'Critical' ? 'color:var(--red)' : 'color:var(--text3)'
}
function sentimentColor(s: string) {
  return s === 'Frustrated' || s === 'Escalating' ? 'color:var(--red)' : s === 'Happy' ? 'color:var(--green)' : 'color:var(--text3)'
}
function tierClass(tier?: string | null) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
function infraClass(infra: string) {
  return infra === 'New' ? 'in' : infra === 'Old' ? 'io' : 'im'
}
function envClass(env: string) {
  return env === 'PROD' ? 'ep' : env === 'TEST' ? 'et' : 'ed'
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
  return 'color:var(--green)'
}
</script>
