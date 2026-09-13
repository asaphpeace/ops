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

// Mirrors CustomersHubView.vue's/ToolsHubView.vue's exact hub-tab pattern:
// tab state lives in ?tab=, the default tab omits it entirely.
const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'matrix', label: 'Environment Matrix' },
  { id: 'versions', label: 'Versions' },
  { id: 'defects', label: 'Defects' },
  { id: 'deployments', label: 'Deployments' },
  { id: 'technical-risk', label: 'Technical Risk' },
  { id: 'infrastructure', label: 'Infrastructure' },
  { id: 'certificates', label: 'SSL Certificates' },
  { id: 'logs', label: 'Logs' },
] as const
type TabId = typeof tabs[number]['id']

const components: Record<TabId, ReturnType<typeof defineAsyncComponent>> = {
  overview: defineAsyncComponent(() => import('@/views/EngineeringOverviewView.vue')),
  matrix: defineAsyncComponent(() => import('@/views/EnvironmentMatrixView.vue')),
  versions: defineAsyncComponent(() => import('@/views/EngineeringVersionsView.vue')),
  defects: defineAsyncComponent(() => import('@/views/EngineeringDefectsView.vue')),
  deployments: defineAsyncComponent(() => import('@/views/EngineeringDeploymentsView.vue')),
  'technical-risk': defineAsyncComponent(() => import('@/views/TechnicalRiskView.vue')),
  infrastructure: defineAsyncComponent(() => import('@/views/EngineeringInfrastructureView.vue')),
  certificates: defineAsyncComponent(() => import('@/views/EngineeringCertificatesView.vue')),
  logs: defineAsyncComponent(() => import('@/views/EngineeringLogsView.vue')),
}

const route = useRoute()
const router = useRouter()

const validTabIds = tabs.map(t => t.id)
const activeTab = computed<TabId>(() =>
  validTabIds.includes(route.query.tab as TabId) ? (route.query.tab as TabId) : 'overview'
)
const activeComponent = computed(() => components[activeTab.value])

function setTab(id: TabId) {
  router.replace({ path: '/engineering', query: id === 'overview' ? {} : { tab: id } })
}
</script>

<style scoped>
.hub-tabs { display: flex; gap: 4px; padding: 20px 20px 0; }
.hub-tab { background: var(--surface); border: 1px solid var(--border); color: var(--text3); font-size: 11px; font-weight: 700; padding: 7px 14px; border-radius: 7px; cursor: pointer; }
.hub-tab:hover { color: var(--text2); }
.hub-tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
</style>
