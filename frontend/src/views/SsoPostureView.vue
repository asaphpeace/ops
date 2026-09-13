<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>SSO Posture</h2>
        <p>Single sign-on status across all VMS customers · security score and priority outreach</p>
      </div>
    </div>

    <div v-if="loading" class="info-bar">Loading SSO data…</div>
    <div v-if="error" class="info-bar" style="border-color:var(--red);color:var(--red);background:rgba(232,68,90,.06)">
      ⚠ {{ error }} — <button class="btn btn-g btn-sm" style="font-size:10px;padding:1px 7px" @click="load">Retry</button>
    </div>

    <template v-if="!loading && !error">
      <div class="stats-row sr-4" style="margin-bottom:16px">
        <div class="sc info">
          <div class="lbl">VMS Customers</div>
          <div class="val">{{ customers.length }}</div>
        </div>
        <div class="sc" :class="missing.length ? 'alert' : 'good'">
          <div class="lbl">No SSO</div>
          <div class="val">{{ missing.length }}</div>
        </div>
        <div class="sc good">
          <div class="lbl">SSO Configured</div>
          <div class="val">{{ configured.length }}</div>
        </div>
        <div class="sc" :class="priorityList.length ? 'warn' : 'good'">
          <div class="lbl">Priority Outreach</div>
          <div class="val">{{ priorityList.length }}</div>
          <div class="sub">Strategic/Premier, no SSO</div>
        </div>
      </div>

      <div class="filter-bar" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
        <input v-model="search" class="inp" placeholder="Search customer…" style="width:200px" />
        <select v-model="filterTier" class="sel">
          <option value="">All tiers</option>
          <option>Strategic</option>
          <option>Premier</option>
          <option>Scale</option>
        </select>
        <select v-model="filterSso" class="sel">
          <option value="">All SSO states</option>
          <option value="missing">Missing SSO</option>
          <option value="configured">SSO configured</option>
        </select>
        <select v-model="sortBy" class="sel" style="margin-left:auto">
          <option value="security">↑ Security score (worst first)</option>
          <option value="name">Name A–Z</option>
          <option value="tier">Tier</option>
          <option value="arr">ARR (high first)</option>
        </select>
      </div>

      <div v-if="!filtered.length" style="color:var(--text3);font-size:11px;padding:24px 0">
        No customers match your filters.
      </div>

      <div v-else class="tw" style="margin-bottom:24px">
        <table>
          <thead>
            <tr>
              <th>Customer</th>
              <th>Tier</th>
              <th>SSO</th>
              <th>Infra</th>
              <th style="text-align:center">WF8</th>
              <th style="text-align:right">Security</th>
              <th style="text-align:right">ARR</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filtered" :key="c.id" style="cursor:pointer" @click="goToCustomer(c.id, 'overview')">
              <td class="td-name">{{ c.name }}</td>
              <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
              <td><span :class="['sso-pill', c.sso === 'None' || !c.sso ? 'sso-none' : 'sso-ok']">{{ c.sso === 'None' || !c.sso ? 'No SSO' : c.sso }}</span></td>
              <td><span :class="['env-badge', infraClass(c.infra)]">{{ c.infra }}</span></td>
              <td style="text-align:center">
                <span v-if="c.wildfly8" class="wf8-badge">WF8</span>
                <span v-else style="color:var(--text3);font-size:10px">—</span>
              </td>
              <td style="text-align:right"><span :class="['sec-score', secClass(c.security_score)]">{{ c.security_score }}</span></td>
              <td style="text-align:right;color:var(--text2);font-size:11px;font-variant-numeric:tabular-nums">£{{ formatArr(c.arr_gbp) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <template v-if="priorityList.length">
        <div class="sh" style="margin-top:0">
          <div>
            <h2>Priority Outreach — Missing SSO</h2>
            <p>Strategic and Premier customers with no SSO configured · highest ARR first</p>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px">
          <div v-for="c in priorityList" :key="c.id" class="pl-row" @click="goToCustomer(c.id, 'overview')">
            <span :class="['tier-badge', tierClass(c.tier)]" style="flex-shrink:0">{{ c.tier }}</span>
            <span class="pl-name">{{ c.name }}</span>
            <span class="sso-pill sso-none">No SSO</span>
            <span :class="['env-badge', infraClass(c.infra)]">{{ c.infra }}</span>
            <span v-if="c.wildfly8" class="wf8-badge">WF8</span>
            <span style="margin-left:auto;color:var(--text2);font-size:11px;font-variant-numeric:tabular-nums">£{{ formatArr(c.arr_gbp) }} ARR</span>
            <span :class="['sec-score', secClass(c.security_score)]">{{ c.security_score }} sec</span>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
// Rebuilt from a real, working prototype view that existed in an earlier,
// never-merged branch of this app and was found to have no current
// equivalent — its backing data (CustomerTriageCard.sso/wildfly8/
// security_score, via the already-live GET /customers/triage endpoint,
// same one CsmRenewalView.vue already depends on) was still fully intact
// and unused for this purpose. No backend changes — this is a pure
// read-only frontend consumer of an existing, unmodified endpoint.
// Modernized with real drill-through (the original had none) and the
// house tier/infra badge conventions already used elsewhere in this file's
// sibling, CsmRenewalView.vue.
import { ref, computed, onMounted } from 'vue'
import { api, type CustomerTriageCard } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCustomer: goToCustomer } = useCustomerDrill()

const customers = ref<CustomerTriageCard[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const search = ref('')
const filterTier = ref('')
const filterSso = ref('')
const sortBy = ref('security')

async function load() {
  error.value = null
  loading.value = true
  try {
    const res = await api.customers.triage()
    customers.value = res.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Failed to load customer data'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const missing = computed(() => customers.value.filter(c => c.sso === 'None' || !c.sso))
const configured = computed(() => customers.value.filter(c => c.sso && c.sso !== 'None'))

const tierOrder: Record<string, number> = { Premier: 0, Strategic: 1, Scale: 2 }

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  const result = customers.value.filter(c => {
    if (q && !c.name.toLowerCase().includes(q)) return false
    if (filterTier.value && c.tier !== filterTier.value) return false
    if (filterSso.value === 'missing' && c.sso !== 'None' && c.sso) return false
    if (filterSso.value === 'configured' && (c.sso === 'None' || !c.sso)) return false
    return true
  })
  return [...result].sort((a, b) => {
    switch (sortBy.value) {
      case 'security': return a.security_score - b.security_score
      case 'name': return a.name.localeCompare(b.name)
      case 'tier': return (tierOrder[a.tier] ?? 9) - (tierOrder[b.tier] ?? 9)
      case 'arr': return b.arr_gbp - a.arr_gbp
      default: return 0
    }
  })
})

// Strategic + Premier customers missing SSO, sorted by ARR desc — the real
// "who to call first" list.
const priorityList = computed(() =>
  customers.value
    .filter(c => (c.sso === 'None' || !c.sso) && (c.tier === 'Strategic' || c.tier === 'Premier'))
    .sort((a, b) => b.arr_gbp - a.arr_gbp)
)

function formatArr(n: number): string {
  return n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : `${Math.round(n / 1000)}K`
}

function tierClass(tier: string): string {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}

function infraClass(infra: string): string {
  return infra === 'New' ? 'in' : infra === 'Old' ? 'io' : 'im'
}

function secClass(s: number): string {
  return s >= 65 ? 'sec-green' : s >= 40 ? 'sec-amber' : 'sec-red'
}
</script>

<style scoped>
.sso-pill { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; letter-spacing: .04em; }
.sso-none { background: rgba(255,80,80,.15); color: var(--red); border: 1px solid rgba(255,80,80,.3); }
.sso-ok   { background: rgba(80,220,120,.12); color: var(--green); border: 1px solid rgba(80,220,120,.25); }

.wf8-badge { display: inline-block; padding: 1px 5px; border-radius: 3px; font-size: 9px; font-weight: 800; background: rgba(255,180,40,.15); color: var(--amber); border: 1px solid rgba(255,180,40,.3); letter-spacing: .04em; }

.sec-score { font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 4px; }
.sec-green { color: var(--green); background: rgba(80,220,120,.1); }
.sec-amber { color: var(--amber); background: rgba(255,180,40,.1); }
.sec-red   { color: var(--red);   background: rgba(255,80,80,.1); }

.pl-row { display: flex; align-items: center; gap: 8px; padding: 9px 12px; background: var(--surface2); border: 1px solid var(--border); border-radius: 7px; font-size: 11px; cursor: pointer; }
.pl-row:hover { border-color: var(--border2); }
.pl-name { font-weight: 600; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
