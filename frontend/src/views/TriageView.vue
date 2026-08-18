<template>
  <div class="view">
    <div class="stats-row sr-5">
      <div class="sc alert">
        <div class="lbl">SLA Breaching</div>
        <div class="val">{{ stats?.sla_breaching ?? '—' }}</div>
      </div>
      <div class="sc warn">
        <div class="lbl">Awaiting Dev</div>
        <div class="val">{{ stats?.awaiting_dev ?? '—' }}</div>
        <div v-if="awaitingDevAvg" class="sub">avg {{ awaitingDevAvg }}d waiting</div>
      </div>
      <div class="sc warn">
        <div class="lbl">Awaiting Customer</div>
        <div class="val">{{ stats?.awaiting_customer ?? '—' }}</div>
      </div>
      <div class="sc good">
        <div class="lbl">Resolved Today</div>
        <div class="val">{{ stats?.resolved_today ?? '—' }}</div>
      </div>
      <div class="sc">
        <div class="lbl">Total Active</div>
        <div class="val">{{ stats?.total_active ?? '—' }}</div>
        <div class="sub">across all types</div>
      </div>
    </div>

    <div v-if="blockedCases.length" class="alert-bar">
      ⊘ {{ blockedCases[0].jira_ref }} ({{ blockedCases[0].customer_name }} {{ blockedCases[0].environment }} upgrade) is blocked — {{ blockedCases[0].blocked_reason }}
    </div>

    <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      <input class="inp" style="width:200px" placeholder="Search queue..." v-model="search">
      <select class="sel" v-model="filterType">
        <option value="">All types</option>
        <option>Upgrade</option>
        <option>Defect</option>
        <option>Support</option>
        <option>Training Gap</option>
      </select>
      <select class="sel" v-model="filterStatus">
        <option value="">All statuses</option>
        <option>Active</option>
        <option>Awaiting Dev</option>
        <option>Awaiting Customer</option>
        <option>Awaiting DevOps</option>
      </select>
      <select class="sel" v-model="filterTier">
        <option value="">All tiers</option>
        <option>Premier</option>
        <option>Strategic</option>
        <option>Scale</option>
      </select>
    </div>

    <!-- SLA Breaching -->
    <template v-if="slaCases.length">
      <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--red);margin-bottom:8px">⚠ SLA Breaching</div>
      <div v-for="c in slaCases" :key="c.id" class="qi sla-red">
        <div :class="['health-dot', healthDot(c)]"></div>
        <div class="qi-left">
          <div class="qi-customer">
            {{ c.customer_name }}
            <span :class="['tier-badge', tierClass(c.customer_tier)]">{{ c.customer_tier }}</span>
          </div>
          <div class="qi-summary">{{ c.jira_ref }} — {{ c.title }}</div>
          <div class="qi-meta">
            <span class="flag-pill" :style="typeStyle(c.case_type)">{{ c.case_type }}</span>
            <span :class="['env-badge', envClass(c.environment)]">{{ c.environment }}</span>
            <span class="vm" style="color:var(--text3)">{{ c.days_open }}d open</span>
            <span style="font-size:9px;color:var(--text3)">{{ c.status }}</span>
          </div>
        </div>
        <div class="qi-right">
          <span :class="['sla-timer', slaTimerClass(c)]">{{ c.days_open - (c.sla_days ?? 0) }}d over SLA</span>
          <span style="font-size:9px;color:var(--text3)">SLA: {{ c.sla_days }}d</span>
          <button class="btn btn-sm btn-red">Chase Dev</button>
        </div>
      </div>
    </template>

    <!-- Active -->
    <template v-if="activeCases.length">
      <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin:14px 0 8px">Active</div>
      <div v-for="c in activeCases" :key="c.id" class="qi">
        <div :class="['health-dot', 'ha']"></div>
        <div class="qi-left">
          <div class="qi-customer">
            {{ c.customer_name }}
            <span :class="['tier-badge', tierClass(c.customer_tier)]">{{ c.customer_tier }}</span>
          </div>
          <div class="qi-summary">{{ c.jira_ref }} — {{ c.title }}</div>
          <div class="qi-meta">
            <span class="flag-pill" :style="typeStyle(c.case_type)">{{ c.case_type }}</span>
            <span :class="['env-badge', envClass(c.environment)]">{{ c.environment }}</span>
            <span v-if="c.defect_status" style="font-size:9px;color:var(--amber)">Dev: {{ c.defect_status }}</span>
            <span v-if="c.root_cause" style="font-size:9px;color:var(--purple)">Root cause: {{ c.root_cause }}</span>
            <span style="font-size:9px;color:var(--text3)">{{ c.status }} · {{ c.days_open }}d</span>
          </div>
        </div>
        <div class="qi-right">
          <span :class="['sla-timer', slaOkClass(c)]">{{ slaRemaining(c) }}</span>
          <span v-if="c.sla_days" style="font-size:9px;color:var(--text3)">SLA: {{ c.sla_days }}d</span>
          <button class="btn btn-sm btn-g">Follow up</button>
        </div>
      </div>
    </template>

    <div v-if="loading" class="info-bar">Loading queue…</div>
    <div v-if="!loading && !cases.length" class="info-bar">No open cases found.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type Case, type TriageStats } from '@/api/client'

const stats = ref<TriageStats | null>(null)
const cases = ref<Case[]>([])
const loading = ref(true)
const search = ref('')
const filterType = ref('')
const filterStatus = ref('')
const filterTier = ref('')

onMounted(async () => {
  try {
    const [statsRes, casesRes] = await Promise.all([
      api.cases.triage(),
      api.cases.list({ status: '' }),
    ])
    stats.value = statsRes.data
    cases.value = casesRes.data
  } finally {
    loading.value = false
  }
})

const filtered = computed(() =>
  cases.value.filter(c => {
    if (search.value && !c.customer_name?.toLowerCase().includes(search.value.toLowerCase()) && !c.jira_ref.toLowerCase().includes(search.value.toLowerCase())) return false
    if (filterType.value && c.case_type !== filterType.value) return false
    if (filterStatus.value && c.status !== filterStatus.value) return false
    if (filterTier.value && c.customer_tier !== filterTier.value) return false
    return true
  })
)

const blockedCases = computed(() => cases.value.filter(c => c.blocked))

const slaCases = computed(() =>
  filtered.value.filter(c => c.sla_days && c.days_open > c.sla_days)
)
const activeCases = computed(() =>
  filtered.value.filter(c => !c.sla_days || c.days_open <= c.sla_days)
)

const awaitingDevAvg = computed(() => {
  const dev = cases.value.filter(c => c.status === 'Awaiting Dev')
  if (!dev.length) return null
  return (dev.reduce((a, c) => a + c.days_open, 0) / dev.length).toFixed(1)
})

function healthDot(c: Case) {
  if (c.sla_days && c.days_open > c.sla_days) return 'hr'
  if (c.days_open > 5) return 'ha'
  return 'hg'
}

function tierClass(tier?: string | null) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}

function envClass(env: string) {
  return env === 'PROD' ? 'ep' : env === 'TEST' ? 'et' : 'ed'
}

function typeStyle(t: string) {
  const map: Record<string, string> = {
    Defect: 'background:var(--red-dim);color:var(--red)',
    Upgrade: 'background:var(--accent-dim);color:var(--accent)',
    Support: 'background:var(--surface3);color:var(--text3)',
    'Training Gap': 'background:var(--purple-dim);color:var(--purple)',
  }
  return map[t] ?? ''
}

function slaTimerClass(c: Case) {
  if (!c.sla_days) return 'sla-g'
  const overBy = c.days_open - c.sla_days
  return overBy > 5 ? 'sla-r' : 'sla-a'
}

function slaOkClass(c: Case) {
  if (!c.sla_days) return 'sla-g'
  const remaining = c.sla_days - c.days_open
  return remaining <= 1 ? 'sla-r' : remaining <= 3 ? 'sla-a' : 'sla-g'
}

function slaRemaining(c: Case) {
  if (!c.sla_days) return `${c.days_open}d open`
  const remaining = c.sla_days - c.days_open
  return remaining > 0 ? `${remaining}d left` : `${Math.abs(remaining)}d over`
}
</script>
