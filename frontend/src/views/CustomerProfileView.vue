<template>
  <div class="view cp">
    <RouterLink to="/customers" class="cp-back">← Customers</RouterLink>

    <div v-if="loadError" class="alert-bar">{{ loadError }}</div>
    <div v-else-if="!customer" class="cp-muted">Loading…</div>

    <template v-else>
      <CustomerHeader :customer="customer" :notes="notes" @update:customer="customer = $event" @notes-changed="reloadNotes" />

      <div class="cp-tabs">
        <button v-for="t in TABS" :key="t.id" class="cp-tab" :class="{ active: tab === t.id }" :title="t.question" @click="setTab(t.id)">
          {{ t.label }}
        </button>
      </div>

      <ContactAccountTab v-if="tab === 'contact'" :customer="customer" />
      <ConnectivityTab v-else-if="tab === 'connectivity'" :customer="customer" @update:customer="customer = $event" />
      <CasesTab v-else-if="tab === 'cases'" :customer="customer" :tech="tech" :tech-loading="techLoading" />
      <UpgradesProjectsTab v-else-if="tab === 'upgrades'" :customer="customer" :tech="tech" :tech-loading="techLoading" />
      <ActivityTab v-else :key="`${customer.id}-${notesVersion}`" :customer-id="customer.id" @notes-changed="reloadNotes" />
    </template>
  </div>
</template>

<script setup lang="ts">
// The one full-page customer profile (replaces the retired slide-over).
// Organised by the question you're asking:
//   Header               — who is this, and are they OK right now?
//   Contact & Account    — who do I talk to, what have they bought?
//   Connectivity         — what do they run, can I reach it, how do I get in?
//   Cases                — what support problems, is there a pattern?
//   Upgrades & Projects  — what's changing for them, what constrains it?
//   Notes & Activity     — what has happened, in order?
// Each tab loads its own data when opened; the slow fleet-wide engineering
// scan is fetched once here and shared by Cases and Upgrades & Projects.
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type Customer, type CustomerNoteEntry, type CustomerTechnical } from '@/api/client'
import CustomerHeader from '@/components/customer/CustomerHeader.vue'
import ContactAccountTab from '@/components/customer/ContactAccountTab.vue'
import ConnectivityTab from '@/components/customer/ConnectivityTab.vue'
import CasesTab from '@/components/customer/CasesTab.vue'
import UpgradesProjectsTab from '@/components/customer/UpgradesProjectsTab.vue'
import ActivityTab from '@/components/customer/ActivityTab.vue'

const TABS = [
  { id: 'contact', label: 'Contact & Account', question: 'Who do I talk to, and what have they bought?' },
  { id: 'connectivity', label: 'Connectivity', question: 'What do they run, can I reach it, and how do I get in?' },
  { id: 'cases', label: 'Cases', question: 'What support problems do they have, and is there a pattern?' },
  { id: 'upgrades', label: 'Upgrades & Projects', question: "What's changing for them, and what constrains it?" },
  { id: 'activity', label: 'Notes & Activity', question: 'What has happened with them, in order?' },
] as const
type TabId = typeof TABS[number]['id']

const route = useRoute()
const router = useRouter()

const customer = ref<Customer | null>(null)
const notes = ref<CustomerNoteEntry[]>([])
const notesVersion = ref(0)
const loadError = ref('')
const tech = ref<CustomerTechnical | null>(null)
const techLoading = ref(false)
let techFor: number | null = null

const id = computed(() => Number(route.params.id))
const tab = computed<TabId>(() => (TABS.some(t => t.id === route.query.tab) ? route.query.tab as TabId : 'contact'))
function setTab(t: TabId) {
  router.replace({ query: t === 'contact' ? {} : { tab: t } })
}

async function reloadNotes() {
  notes.value = (await api.customers.notes(id.value)).data
  notesVersion.value++
}

function ensureTech() {
  if (techFor === id.value) return
  techFor = id.value
  tech.value = null
  techLoading.value = true
  api.engineering.customerTechnical(id.value)
    .then(r => { if (techFor === r.data.customer_id) tech.value = r.data })
    .catch(() => { tech.value = null })
    .finally(() => { techLoading.value = false })
}

async function load() {
  customer.value = null
  loadError.value = ''
  techFor = null
  try {
    const [c, n] = await Promise.all([api.customers.get(id.value), api.customers.notes(id.value)])
    customer.value = c.data
    notes.value = n.data
    document.title = `${c.data.name} · Sedna Ops`
  } catch {
    loadError.value = 'Could not load this customer.'
  }
}
watch(id, load, { immediate: true })
watch([tab, id], ([t]) => { if (t === 'cases' || t === 'upgrades') ensureTech() }, { immediate: true })
onBeforeUnmount(() => { document.title = 'Sedna Ops' })
</script>

<!-- Not scoped: shared by the section components under components/customer/. Everything is .cp-prefixed. -->
<style>
.cp .cp-back { display: inline-block; font-size: 11px; color: var(--text3); text-decoration: none; margin-bottom: 10px; }
.cp .cp-back:hover { color: var(--accent); }
.cp .cp-muted { font-size: 10.5px; color: var(--text3); font-weight: 400; }
.cp .cp-mono { font-family: 'SF Mono', monospace; }
.cp .cp-nowrap { white-space: nowrap; }
.cp .cp-push { margin-left: auto; }
.cp .cp-gap { margin-top: 14px; }
.cp .cp-gap-sm { margin-top: 8px; margin-bottom: 8px; }
.cp .ok { color: var(--green) !important; }
.cp .warn { color: var(--amber) !important; }
.cp .bad { color: var(--red) !important; }
.cp .cp-warn-text { color: var(--amber); }
.cp .cp-bad-text { font-size: 10px; color: var(--red); margin-top: 2px; }
.cp .cp-link { background: none; border: none; padding: 0; font-size: 10.5px; color: var(--accent); cursor: pointer; }
.cp .cp-link:hover { text-decoration: underline; }
.cp .cp-check { display: inline-flex; align-items: center; gap: 5px; }
.cp .cp-error { font-size: 10.5px; color: var(--red); margin-top: 6px; }
.cp .cp-row-end { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 8px; }
.cp .cp-row-wrap { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }

/* Header */
.cp .cp-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.cp .cp-name { font-size: 22px; font-weight: 800; letter-spacing: -.02em; color: var(--text); margin: 0 0 6px; }
.cp .cp-head-actions { display: flex; gap: 6px; flex-shrink: 0; }
.cp .cp-badge { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; background: var(--surface2); border: 1px solid var(--border2); color: var(--text2); }
.cp .cp-status { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px 0 10px; }
.cp .cp-stat { font-size: 11.5px; font-weight: 600; color: var(--text); padding: 5px 10px; border-radius: 7px; background: var(--surface); border: 1px solid var(--border); }
.cp .cp-stat.ok { border-color: rgba(15, 186, 129, .35); }
.cp .cp-stat.warn { border-color: rgba(240, 160, 48, .4); }
.cp .cp-stat.bad { border-color: rgba(232, 68, 90, .45); }
.cp .cp-stat.info { border-color: rgba(59, 127, 245, .35); }
.cp .cp-stat-lbl { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); margin-right: 4px; }
.cp .cp-stat.ok .cp-stat-lbl { color: var(--green); }
.cp .cp-stat.warn .cp-stat-lbl { color: var(--amber); }
.cp .cp-stat.bad .cp-stat-lbl { color: var(--red); }
.cp .cp-edit { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: flex-end; margin-bottom: 10px; }
.cp .cp-edit label { display: flex; flex-direction: column; gap: 3px; font-size: 9.5px; color: var(--text3); }
.cp .cp-edit .inp { width: 140px; }
.cp .cp-edit-wide { flex: 1; min-width: 220px; }
.cp .cp-edit-wide .inp { width: 100%; }
.cp .cp-edit-actions { display: flex; gap: 6px; }
.cp .cp-sticky { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.cp .cp-sticky-text { flex: 1; font-size: 11.5px; color: var(--text); white-space: pre-wrap; }

/* Tabs */
.cp .cp-tabs { display: flex; gap: 4px; flex-wrap: wrap; margin: 14px 0; }
.cp .cp-tab { background: var(--surface); border: 1px solid var(--border); color: var(--text3); font-size: 11.5px; font-weight: 700; padding: 7px 14px; border-radius: 7px; cursor: pointer; }
.cp .cp-tab:hover { color: var(--text2); }
.cp .cp-tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }

/* Cards, facts, chips */
.cp .cp-card { padding: 14px 16px; }
.cp .cp-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.cp .cp-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px; align-items: start; }
/* Grid/flex children default to min-width:auto, so one long no-wrap title
   would widen the column and the whole page — let them shrink instead. */
.cp .cp-grid > *, .cp .cp-instances > *, .cp .cp-kpis > * { min-width: 0; }
.cp .cp-fact { display: flex; justify-content: space-between; gap: 12px; font-size: 11.5px; color: var(--text3); padding: 5px 0; border-bottom: 1px solid var(--border); }
.cp .cp-fact b { color: var(--text); font-weight: 600; text-align: right; }
.cp .cp-missing { margin-top: 8px; }
.cp .cp-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.cp .cp-chip { display: inline-flex; gap: 6px; font-size: 11px; padding: 4px 10px; border-radius: 6px; background: var(--surface2); color: var(--text3); }
.cp .cp-chip b { color: var(--text); font-weight: 600; }
.cp .cp-chip.warn b { color: var(--amber); }
.cp .cp-chip.ok b { color: var(--green); }
.cp .cp-pill { font-size: 8.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .05em; padding: 1px 6px; border-radius: 3px; background: var(--surface3); color: var(--text2); }
.cp .cp-pill.ok { background: var(--green-dim); color: var(--green) !important; }
.cp .cp-pill.warn { background: var(--amber-dim); color: var(--amber) !important; }
.cp .cp-pill.purple { background: var(--purple-dim); color: var(--purple); }
.cp .cp-inline-form { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; align-items: center; }
.cp .cp-inline-form .inp { flex: 1; min-width: 120px; }
.cp .cp-warnbox { font-size: 10.5px; color: var(--amber); background: var(--surface2); border-radius: 6px; padding: 7px 9px; margin: 6px 0; }
.cp .cp-notebox { margin-top: 10px; padding: 9px; background: var(--surface2); border-radius: 6px; font-size: 10.5px; color: var(--text2); white-space: pre-wrap; }
.cp .cp-scroll-x { overflow-x: auto; }
.cp .cp-json { font-size: 10px; background: var(--surface2); border-radius: 6px; padding: 9px; overflow: auto; max-height: 260px; white-space: pre-wrap; margin-top: 8px; }

/* Contact */
.cp .cp-contact { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 6px 0; border-bottom: 1px solid var(--border); }
.cp .cp-email { font-size: 12px; color: var(--text); text-decoration: none; }
.cp .cp-email:hover { color: var(--accent); }
.cp .cp-hidden-note { padding: 6px 0 2px; }

/* Connectivity */
.cp .cp-instances { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; margin-top: 12px; }
.cp .cp-inst { padding: 14px 16px; }
.cp .cp-inst.empty { border-style: dashed; background: transparent; }
.cp .cp-inst-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.cp .cp-env { font-size: 9px; font-weight: 800; letter-spacing: .06em; padding: 2px 7px; border-radius: 3px; background: var(--surface3); color: var(--text2); }
.cp .cp-env.prod { background: var(--red-dim); color: var(--red); }
.cp .cp-env.test { background: var(--amber-dim); color: var(--amber); }
.cp .cp-env.dev { background: var(--teal-dim); color: var(--teal); }
.cp .cp-host { font-family: 'SF Mono', monospace; font-size: 12.5px; font-weight: 700; color: var(--accent); text-decoration: none; word-break: break-all; }
.cp .cp-host:hover { text-decoration: underline; }
.cp .cp-sub-edit { margin-bottom: 8px; }
.cp .cp-hint { margin-top: 4px; }
.cp .cp-inst-status { display: flex; align-items: center; gap: 7px; font-size: 11.5px; color: var(--text2); margin-bottom: 8px; }
.cp .cp-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text3); flex-shrink: 0; }
.cp .cp-dot.ok { background: var(--green); }
.cp .cp-dot.bad { background: var(--red); }
.cp .cp-flags { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 8px; }
.cp .cp-flag { font-size: 9.5px; padding: 1px 7px; border-radius: 10px; background: var(--surface2); color: var(--text3); text-decoration: line-through; opacity: .7; }
.cp .cp-flag.on { color: var(--teal); background: var(--teal-dim); text-decoration: none; opacity: 1; }
.cp .cp-inst-actions { display: flex; gap: 8px; margin-top: 12px; }
.cp .cp-add-env { border: 1px dashed var(--border2); background: transparent; color: var(--text3); border-radius: 9px; font-size: 11px; cursor: pointer; min-height: 60px; }
.cp .cp-add-env:hover { color: var(--accent); border-color: var(--accent); }

/* Cases */
.cp .cp-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 12px; }
.cp .cp-case-row { display: flex; gap: 10px; align-items: center; padding: 8px 14px; border-bottom: 1px solid var(--border); cursor: pointer; }
.cp .cp-case-row:hover { background: var(--surface2); }
.cp .cp-case-title { flex: 1; min-width: 0; font-size: 11.5px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cp .cp-bars { display: flex; align-items: flex-end; gap: 4px; height: 80px; }
.cp .cp-bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
.cp .cp-bar { width: 100%; background: var(--accent); border-radius: 3px 3px 0 0; opacity: .75; }
.cp .cp-bar-lbl { font-size: 8.5px; color: var(--text3); margin-top: 3px; }
.cp .cp-topic { display: flex; gap: 8px; align-items: center; font-size: 11.5px; color: var(--text); padding: 4px 0; }
.cp .cp-click { cursor: pointer; }
.cp .cp-click:hover td { background: var(--surface2); }
.cp .cp-title-cell { max-width: 440px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text); }

/* Upgrades & projects */
.cp .cp-risk-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.cp .cp-risk-score { font-size: 22px; font-weight: 800; color: var(--text); }
.cp .cp-risk-bar { margin-bottom: 6px; }
.cp .cp-risk-lbl { display: flex; justify-content: space-between; font-size: 10px; color: var(--text3); }
.cp .cp-risk-track { height: 5px; background: var(--surface3); border-radius: 3px; overflow: hidden; margin-top: 2px; }
.cp .cp-risk-fill { height: 100%; background: var(--accent); }
.cp .cp-path { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; font-family: 'SF Mono', monospace; font-size: 11px; color: var(--text2); }

/* Activity */
.cp .cp-note-form { display: flex; flex-direction: column; gap: 4px; }
.cp .cp-filters { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px 0; }
.cp .cp-filter { font-size: 10.5px; font-weight: 700; color: var(--text2); background: var(--surface2); border: 1px solid var(--border2); border-radius: 12px; padding: 3px 10px; cursor: pointer; }
.cp .cp-filter.active { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }
.cp .cp-day { margin-bottom: 12px; }
.cp .cp-day-head { font-size: 9.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; color: var(--text3); padding: 4px 0; border-bottom: 1px solid var(--border); margin-bottom: 4px; }
.cp .cp-act { display: grid; grid-template-columns: 86px 42px 1fr auto; gap: 10px; align-items: baseline; padding: 6px 0; }
.cp .cp-act-kind { font-size: 8.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .05em; padding: 2px 6px; border-radius: 3px; text-align: center; background: var(--surface2); color: var(--text2); }
.cp .cp-act-kind.note { background: var(--accent-dim); color: var(--accent); }
.cp .cp-act-kind.comms { background: var(--purple-dim); color: var(--purple); }
.cp .cp-act-kind.training { background: var(--purple-dim); color: var(--purple); }
.cp .cp-act-kind.escalation { background: var(--red-dim); color: var(--red); }
.cp .cp-act-kind.upgrade { background: var(--green-dim); color: var(--green); }
.cp .cp-act-kind.automation { background: var(--teal-dim); color: var(--teal); }
.cp .cp-act-time { font-size: 10px; color: var(--text3); font-family: 'SF Mono', monospace; }
.cp .cp-act-title { font-size: 12px; color: var(--text); display: flex; gap: 6px; align-items: baseline; flex-wrap: wrap; }
.cp .cp-act-link { color: var(--text); }
.cp .cp-act-link:hover { color: var(--accent); }
.cp .cp-act-detail { font-size: 11px; color: var(--text2); margin-top: 2px; white-space: pre-wrap; }
.cp .cp-act-side { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }

@media (max-width: 860px) {
  .cp .cp-grid { grid-template-columns: 1fr; }
  .cp .cp-kpis { grid-template-columns: repeat(2, 1fr); }
  .cp .cp-head { flex-direction: column; }
  .cp .cp-act { grid-template-columns: 76px 1fr; }
  .cp .cp-act-time, .cp .cp-act-side { display: none; }
}
</style>
