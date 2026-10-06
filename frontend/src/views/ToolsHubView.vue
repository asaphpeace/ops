<template>
  <div class="hub-tabs">
    <button v-for="t in tabs" :key="t.id" class="hub-tab" :class="{ active: activeTab === t.id }" @click="setTab(t.id)">
      {{ t.label }}
    </button>
  </div>
  <component :is="activeComponent" />
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// One nav destination for founder-only tooling (Jira Mapping, VMS
// Sandbox, Platform Incidents, Ops Notes, Ollama, Knowledge) — previously
// 6 separate top-level sidebar icons, visually identical in weight to
// customer-facing views despite being a completely different audience
// (only ever you). Same hub pattern as CustomersHubView.vue — mounts the
// existing, untouched view components, only switches which one shows.
const tabs = [
  { id: 'jira', label: 'Jira Mapping' },
  { id: 'vms-sandbox', label: 'VMS Sandbox' },
  { id: 'incidents', label: 'Platform Incidents' },
  { id: 'ops-notes', label: 'Ops Notes' },
  { id: 'ollama', label: 'Ollama' },
  { id: 'troubleshoot', label: 'Troubleshoot' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'teams', label: 'Teams & Routing' },
  { id: 'audit-log', label: 'Audit Log' },
] as const
type TabId = typeof tabs[number]['id']

const components: Record<TabId, ReturnType<typeof defineAsyncComponent>> = {
  jira: defineAsyncComponent(() => import('@/views/JiraMappingView.vue')),
  'vms-sandbox': defineAsyncComponent(() => import('@/views/VmsSandboxView.vue')),
  incidents: defineAsyncComponent(() => import('@/views/IncidentsView.vue')),
  'ops-notes': defineAsyncComponent(() => import('@/views/OpsNotesView.vue')),
  ollama: defineAsyncComponent(() => import('@/views/OllamaControlView.vue')),
  troubleshoot: defineAsyncComponent(() => import('@/views/TroubleshootView.vue')),
  knowledge: defineAsyncComponent(() => import('@/views/KnowledgeView.vue')),
  teams: defineAsyncComponent(() => import('@/views/TeamsRoutingView.vue')),
  'audit-log': defineAsyncComponent(() => import('@/views/AuditLogView.vue')),
}

const route = useRoute()
const router = useRouter()

const validTabIds = tabs.map(t => t.id)
const activeTab = computed<TabId>(() =>
  validTabIds.includes(route.query.tab as TabId) ? (route.query.tab as TabId) : 'jira'
)
const activeComponent = computed(() => components[activeTab.value])

function setTab(id: TabId) {
  router.replace({ path: '/tools', query: id === 'jira' ? {} : { tab: id } })
}
</script>

<style scoped>
.hub-tabs { display: flex; gap: 4px; padding: 20px 20px 0; flex-wrap: wrap; }
.hub-tab { background: var(--surface); border: 1px solid var(--border); color: var(--text3); font-size: 11px; font-weight: 700; padding: 7px 14px; border-radius: 7px; cursor: pointer; }
.hub-tab:hover { color: var(--text2); }
.hub-tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
</style>
