<template>
  <div class="view">
    <div class="sh">
      <div><h2>Knowledge</h2><p>Categorized institutional knowledge mined by the local Ollama model from real Slack context pasted into Ops Notes — trends, systems, processes, procedures, challenges, and how things relate to each other. Unlike the advisory-only supervisor, this is genuine extraction from raw text — every entry traces back to its real source note.</p></div>
    </div>

    <div class="tw" style="padding:12px 15px;margin-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <FilterPills v-model="categoryFilter" all-label="All categories" :options="categoryOptions" />
      <button class="btn btn-g btn-sm" style="margin-left:auto" :disabled="extracting" @click="extractNow">
        {{ extracting ? 'Started — check back in a few minutes…' : '🧠 Extract now' }}
      </button>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>
    <div v-else-if="!extracts.length" class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:32px 0">
      Nothing extracted yet. Paste some Slack context into Ops Notes, then run extraction — a full pass over long notes can take several minutes (each note is chunked and processed sequentially against the local model).
    </div>

    <div v-else class="kn-list">
      <div v-for="k in extracts" :key="k.id" class="tw kn-card">
        <div class="kn-head">
          <span class="flag-pill" :style="categoryStyle(k.category)">{{ k.category }}</span>
          <span v-if="k.source_label" class="flag-pill" style="background:var(--surface3);color:var(--text3)">{{ k.source_label }}</span>
          <span v-if="k.jira_ref" class="jref" @click="openCase(k.jira_ref!)">{{ k.jira_ref }}</span>
          <span v-if="k.customer_id" class="td-name" style="cursor:pointer" @click="goToCustomer(k.customer_id!, 'overview')">customer #{{ k.customer_id }}</span>
          <span class="sub" style="margin-left:auto;font-size:9px;color:var(--text3)">{{ formatDate(k.created_at) }}</span>
          <span class="jref" style="font-size:9px" @click="dismiss(k.id)">✕ dismiss</span>
        </div>
        <div class="sub" style="font-size:11.5px;color:var(--text2);margin-top:6px">{{ k.summary }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api, type KnowledgeExtract } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { useCaseDrill } from '@/composables/useCaseDrill'
import FilterPills from '@/components/FilterPills.vue'

const { openCustomer: goToCustomer } = useCustomerDrill()
const { openCase } = useCaseDrill()

const extracts = ref<KnowledgeExtract[]>([])
const loading = ref(true)
const extracting = ref(false)
const categoryFilter = ref('')

const categoryOptions = [
  { value: 'Trend', label: 'Trend' },
  { value: 'System', label: 'System' },
  { value: 'Process', label: 'Process' },
  { value: 'Procedure', label: 'Procedure' },
  { value: 'Challenge', label: 'Challenge' },
  { value: 'Relationship', label: 'Relationship' },
]

const CATEGORY_COLORS: Record<string, string> = {
  Trend: 'background:rgba(59,127,245,.12);color:var(--accent)',
  System: 'background:var(--surface3);color:var(--text2)',
  Process: 'background:rgba(15,186,129,.12);color:var(--green)',
  Procedure: 'background:rgba(15,186,129,.12);color:var(--green)',
  Challenge: 'background:var(--red-dim);color:var(--red)',
  Relationship: 'background:rgba(240,160,48,.12);color:var(--amber)',
}
function categoryStyle(category: string): string {
  return CATEGORY_COLORS[category] ?? 'background:var(--surface3);color:var(--text3)'
}

function formatDate(d: string) {
  return new Date(d).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadExtracts() {
  loading.value = true
  try {
    const res = await api.knowledge.list(categoryFilter.value ? { category: categoryFilter.value } : {})
    extracts.value = res.data
  } finally {
    loading.value = false
  }
}

async function dismiss(id: number) {
  await api.knowledge.dismiss(id)
  await loadExtracts()
}

async function extractNow() {
  extracting.value = true
  try {
    await api.knowledge.extractNow()
  } finally {
    // Stays "started" for a bit rather than resetting instantly — the real
    // work continues in the background well past this response returning.
    setTimeout(() => { extracting.value = false }, 15000)
  }
}

watch(categoryFilter, loadExtracts)

onMounted(loadExtracts)
</script>

<style scoped>
.kn-list { display: flex; flex-direction: column; gap: 10px; }
.kn-card { padding: 12px 14px; }
.kn-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
</style>
