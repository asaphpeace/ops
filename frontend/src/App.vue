<template>
  <nav class="sidebar">
    <div class="logo">SO</div>

    <RouterLink to="/" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        📊<span class="tip">Command Center</span>
      </button>
    </RouterLink>

    <RouterLink to="/my-desk" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        🖥<span class="tip">My Desk</span>
      </button>
    </RouterLink>

    <RouterLink to="/operations" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ⊞<span class="tip">Operations</span>
      </button>
    </RouterLink>

    <RouterLink to="/support-signals" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ∿<span class="tip">Support Signals</span>
      </button>
    </RouterLink>

    <div class="nb-divider"></div>

    <RouterLink to="/customers" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ◎<span class="tip">Customers</span>
      </button>
    </RouterLink>

    <RouterLink to="/releases" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ▤<span class="tip">Releases</span>
      </button>
    </RouterLink>

    <RouterLink to="/engineering" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        ⚙<span class="tip">Engineering</span>
      </button>
    </RouterLink>

    <RouterLink to="/tools" custom v-slot="{ isActive, navigate }">
      <button class="nb" :class="{ active: isActive }" @click="navigate">
        🛠<span class="tip">Tools</span>
      </button>
    </RouterLink>
  </nav>

  <div class="main">
    <div class="topbar">
      <div>
        <div class="topbar-title">{{ currentTitle }}</div>
        <div class="topbar-sub">Your L2 operational hub · {{ today }}</div>
      </div>
      <div class="topbar-right">
        <div class="spill" v-if="triage">
          <div class="dot" style="background:var(--red)"></div>{{ triage.sla_breaching }} SLA breaching
        </div>
        <div class="spill" v-if="triage">
          <div class="dot" style="background:var(--amber)"></div>{{ triage.awaiting_dev }} awaiting dev
        </div>
        <div class="spill" v-if="triage">
          <div class="dot" style="background:var(--green)"></div>{{ triage.resolved_today }} done today
        </div>
        <NotificationBell />
        <AiObservationBell />
        <RouterLink to="/weekly-report">
          <button class="btn btn-g btn-sm">🗞 Weekly Report</button>
        </RouterLink>
        <RouterLink to="/snapshot">
          <button class="btn btn-g btn-sm">📋 Snapshot</button>
        </RouterLink>
      </div>
    </div>

    <RouterView />
  </div>

  <CaseDrillPanel />
  <CustomerDrillPanel />
  <BugDrillPanel />
  <EngineeringEntityPanel />
  <ToastHost />
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, type TriageStats } from '@/api/client'
import CaseDrillPanel from '@/components/CaseDrillPanel.vue'
import CustomerDrillPanel from '@/components/CustomerDrillPanel.vue'
import BugDrillPanel from '@/components/BugDrillPanel.vue'
import EngineeringEntityPanel from '@/components/EngineeringEntityPanel.vue'
import ToastHost from '@/components/ToastHost.vue'
import NotificationBell from '@/components/NotificationBell.vue'
import AiObservationBell from '@/components/AiObservationBell.vue'

const route = useRoute()
const triage = ref<TriageStats | null>(null)

onMounted(async () => {
  try {
    const res = await api.cases.triage()
    triage.value = res.data
  } catch { /* non-fatal */ }
})

const titles: Record<string, string> = {
  '/':                 'Command Center',
  '/my-desk':          'My Desk',
  '/operations':       'Operations',
  '/support-signals':  'Support Signals',
  '/customers':        'Customer Intelligence',
  '/customers/comms':  'Customer Comms',
  '/releases':         'Release Intelligence',
  '/engineering':      'Engineering',
  '/tools':            'Tools',
  '/snapshot':         'Handover Snapshot',
  '/weekly-report':    'Weekly Ops Report',
}

// /customers and /tools each host several real sub-sections as tabs (see
// CustomersHubView.vue / ToolsHubView.vue) — a per-tab title reads better
// in the topbar than the bare hub name for all of them, including the
// default tab (no ?tab= param at all — matches each hub's own
// query-less-default convention, so the fallback below has to supply the
// default tab id itself rather than only reading it from the URL).
const defaultTabs: Record<string, string> = { '/customers': 'customers', '/tools': 'jira', '/engineering': 'overview' }
const tabTitles: Record<string, Record<string, string>> = {
  '/customers': {
    customers: 'Customer Intelligence',
    'csm-risk': 'CSM Renewal Risk',
    trends: 'Trends & Health',
    education: 'Customer Education',
  },
  '/tools': {
    jira: 'Jira Mapping',
    'vms-sandbox': 'VMS Sandbox',
    incidents: 'Platform Incidents',
    'ops-notes': 'Ops Notes',
    ollama: 'Ollama',
    troubleshoot: 'Troubleshoot',
    knowledge: 'Knowledge',
  },
  '/engineering': {
    overview: 'Engineering Overview',
    matrix: 'Environment Matrix',
    versions: 'Version Intelligence',
    defects: 'Defect Intelligence',
    deployments: 'Deployments',
    'technical-risk': 'Technical Risk',
    infrastructure: 'Infrastructure',
    certificates: 'SSL Certificates',
    logs: 'Logs',
  },
}

const currentTitle = computed(() => {
  const tab = (route.query.tab as string | undefined) ?? defaultTabs[route.path]
  if (tab && tabTitles[route.path]?.[tab]) return tabTitles[route.path][tab]
  return titles[route.path] ?? 'Sedna Ops'
})

const today = computed(() => {
  return new Date().toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  })
})
</script>
