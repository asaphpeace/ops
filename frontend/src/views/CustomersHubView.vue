<template>
  <div class="hub-tabs">
    <button v-for="t in tabs" :key="t.id" class="hub-tab" :class="{ active: activeTab === t.id }" @click="setTab(t.id)">
      {{ t.label }}
    </button>
  </div>
  <component :is="activeComponent" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { defineAsyncComponent } from 'vue'

// One nav destination for everything customer-facing (Customers, CSM
// Renewal Risk, Trends, Education) — previously 4 separate top-level
// sidebar icons with no visual grouping, despite sharing one real
// audience. Mirrors OperationsView.vue's own tab pattern exactly (tab
// state in the ?tab= query param, so a link/bookmark to a specific tab
// still works); the difference is these tabs mount the existing,
// untouched view components directly instead of inlining their markup —
// each one stays a fully independent file, this hub only switches which
// one is on screen.
const tabs = [
  { id: 'customers', label: 'Customers' },
  { id: 'csm-risk', label: 'CSM Renewal Risk' },
  { id: 'trends', label: 'Trends' },
  { id: 'education', label: 'Education' },
] as const
type TabId = typeof tabs[number]['id']

const components: Record<TabId, ReturnType<typeof defineAsyncComponent>> = {
  customers: defineAsyncComponent(() => import('@/views/CustomersView.vue')),
  'csm-risk': defineAsyncComponent(() => import('@/views/CsmRenewalView.vue')),
  trends: defineAsyncComponent(() => import('@/views/TrendsView.vue')),
  education: defineAsyncComponent(() => import('@/views/EducationView.vue')),
}

const route = useRoute()
const router = useRouter()

const validTabIds = tabs.map(t => t.id)
const activeTab = computed<TabId>(() =>
  validTabIds.includes(route.query.tab as TabId) ? (route.query.tab as TabId) : 'customers'
)
const activeComponent = computed(() => components[activeTab.value])

function setTab(id: TabId) {
  router.replace({ path: '/customers', query: id === 'customers' ? {} : { tab: id } })
}
</script>

<style scoped>
.hub-tabs { display: flex; gap: 4px; padding: 20px 20px 0; }
.hub-tab { background: var(--surface); border: 1px solid var(--border); color: var(--text3); font-size: 11px; font-weight: 700; padding: 7px 14px; border-radius: 7px; cursor: pointer; }
.hub-tab:hover { color: var(--text2); }
.hub-tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
</style>
