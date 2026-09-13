<template>
  <DrillPanel :open="open" :tabs="tabs" :active-tab="activeTab" @close="close" @update:active-tab="activeTab = $event">
    <template #header>
      <div style="display:flex;align-items:center;gap:8px">
        <h3 style="margin:0">{{ jiraRef }}</h3>
        <a :href="jiraUrl(jiraRef ?? '')" target="_blank" rel="noopener" class="jira-link" title="Open in Jira">↗ Jira</a>
      </div>
      <div v-if="bug" style="display:flex;gap:5px;align-items:center;flex-wrap:wrap;margin-top:4px">
        <span style="font-size:10px;color:var(--text3)" :style="bug.status === 'Done' ? 'color:var(--green)' : ''">{{ bug.status }}</span>
        <span v-if="bug.fix_version" class="flag-pill" style="background:var(--green-dim);color:var(--green)">fix {{ bug.fix_version }}</span>
        <span v-else style="font-size:10px;color:var(--text3)">no fix version yet</span>
        <span v-if="bug.sprint_name" style="font-size:10px;color:var(--text3)">🏃 {{ bug.sprint_name }}</span>
        <span v-if="bug.assignee" style="font-size:10px;color:var(--text3)">· {{ bug.assignee }}</span>
      </div>
    </template>

    <template #body>
      <div v-if="loading" class="sub" style="color:var(--text3)">Loading…</div>
      <template v-else-if="bug">
        <!-- Overview -->
        <div v-if="activeTab === 'overview'">
          <div class="ds"><h4>Bug</h4>
            <div class="fg">
              <div class="fr">Type <span style="color:var(--text)">{{ bug.issue_type }}</span></div>
              <div class="fr">Status <span style="color:var(--text)">{{ bug.status }}</span></div>
              <div class="fr">Fix version <span :style="bug.fix_version ? 'color:var(--green)' : 'color:var(--text3)'">{{ bug.fix_version ?? 'not yet confirmed' }}</span></div>
              <div class="fr" v-if="bug.sprint_name">Sprint <span style="color:var(--text)">{{ bug.sprint_name }}<template v-if="bug.sprint_state"> · {{ bug.sprint_state }}</template></span></div>
              <div class="fr">Assignee <span style="color:var(--text)">{{ bug.assignee ?? 'Unassigned' }}</span></div>
            </div>
            <div v-if="bug.labels.length" style="display:flex;gap:5px;flex-wrap:wrap;margin-top:8px">
              <span v-for="l in bug.labels" :key="l" class="flag-pill" style="background:var(--surface2);color:var(--text2)">{{ l }}</span>
            </div>
          </div>

          <div class="ds"><h4>Linked Cases <span style="color:var(--text3);font-weight:600">· {{ bug.linked_cases.length }}</span></h4>
            <div v-if="!bug.linked_cases.length" class="sub" style="color:var(--text3);font-size:11px">No cases linked to this bug yet.</div>
            <div v-for="c in bug.linked_cases" :key="c.jira_ref" class="jr jr-click" @click="openCase(c.jira_ref)">
              <a class="jref" :href="jiraUrl(c.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>{{ c.jira_ref }}</a>
              <span class="jtitle">{{ c.customer_name ?? 'Unknown' }} · {{ c.title }}</span>
              <span v-if="c.customer_tier" :class="['tier-badge', tierClass(c.customer_tier)]">{{ c.customer_tier }}</span>
              <span class="jst">{{ c.days_open }}d</span>
            </div>
          </div>

          <div class="ds">
            <h4>AI Summary</h4>
            <button class="btn btn-g btn-sm" :disabled="summarizing" @click="onSummaryButtonClick">
              {{ summarizing ? 'Generating…' : (bug.ai_summary ? '✦ View Summary' : '✦ Summarize') }}
            </button>
          </div>

          <div class="ds">
            <h4 style="display:flex;align-items:center;justify-content:space-between">
              <span>External Context</span>
              <span v-if="bug.rovo_context_at" class="sub" style="font-weight:600;color:var(--text3);text-transform:none;letter-spacing:0">{{ formatDate(bug.rovo_context_at) }}</span>
            </h4>
            <div v-if="bug.rovo_context && !editingRovo" style="padding:9px;background:var(--surface2);border-radius:6px;font-size:10px;color:var(--text2);white-space:pre-wrap">{{ bug.rovo_context }}</div>
            <textarea v-if="editingRovo" class="inp" rows="4" style="width:100%" placeholder="Paste context from Rovo Chat or elsewhere…" v-model="rovoContextDraft"></textarea>
            <div style="display:flex;gap:6px;margin-top:6px">
              <button class="btn btn-sm btn-g" @click="toggleRovoEdit">{{ editingRovo ? 'Cancel' : (bug.rovo_context ? 'Edit' : '+ Paste context') }}</button>
              <button v-if="editingRovo" class="btn btn-sm" :disabled="savingRovo" @click="saveRovoContext">{{ savingRovo ? 'Saving…' : 'Save' }}</button>
            </div>
          </div>
        </div>

        <!-- Timeline -->
        <div v-if="activeTab === 'timeline'">
          <div v-if="timelineLoading" class="sub" style="color:var(--text3)">Loading…</div>
          <template v-else>
            <div v-if="!timeline.length" class="sub" style="color:var(--text3);font-size:11px;padding:8px 0">No recorded events for this bug yet.</div>
            <div v-for="(e, i) in timeline" :key="i" class="tl-item">
              <div class="tl-dot" style="background:var(--accent)"></div>
              <div class="tl-content">
                <div class="tl-what">{{ e.action }}<span v-if="e.detail" style="color:var(--text3)"> — {{ e.detail }}</span></div>
                <div class="tl-when">{{ formatDate(e.created_at) }} · {{ e.actor }}</div>
              </div>
            </div>
          </template>
        </div>
      </template>
    </template>
  </DrillPanel>

  <AiSummaryModal
    :open="showSummaryModal"
    :title="jiraRef ?? ''"
    :summary="bug?.ai_summary ?? null"
    :generated-at="bug?.ai_summary_at ?? null"
    :loading="summarizing"
    :error="summaryMessage"
    @close="showSummaryModal = false"
    @regenerate="summarize"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api, jiraUrl, type VmsBug, type BugTimelineEntry } from '@/api/client'
import { useBugDrill } from '@/composables/useBugDrill'
import { useCaseDrill } from '@/composables/useCaseDrill'
import DrillPanel from '@/components/DrillPanel.vue'
import AiSummaryModal from '@/components/AiSummaryModal.vue'

const { openRef, closeBug } = useBugDrill()
const { openCase } = useCaseDrill()

const open = computed(() => openRef.value !== null)
const jiraRef = computed(() => openRef.value)
const bug = ref<VmsBug | null>(null)
const loading = ref(false)
const activeTab = ref('overview')

const timeline = ref<BugTimelineEntry[]>([])
const timelineLoading = ref(false)

const summarizing = ref(false)
const summaryMessage = ref<string | null>(null)
const showSummaryModal = ref(false)

const editingRovo = ref(false)
const savingRovo = ref(false)
const rovoContextDraft = ref('')

const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'timeline', label: 'Timeline' },
]

watch(jiraRef, async (ref) => {
  bug.value = null
  timeline.value = []
  summaryMessage.value = null
  showSummaryModal.value = false
  editingRovo.value = false
  activeTab.value = 'overview'
  if (!ref) return
  loading.value = true
  try {
    const res = await api.bugs.get(ref)
    bug.value = res.data
  } finally {
    loading.value = false
  }

  timelineLoading.value = true
  try {
    const tRes = await api.bugs.timeline(ref)
    timeline.value = tRes.data
  } finally {
    timelineLoading.value = false
  }
})

async function onSummaryButtonClick() {
  if (bug.value?.ai_summary) {
    showSummaryModal.value = true
    return
  }
  await summarize()
}

async function summarize() {
  if (!jiraRef.value) return
  summarizing.value = true
  summaryMessage.value = null
  showSummaryModal.value = true
  try {
    const res = await api.bugs.summarize(jiraRef.value)
    if (res.data.message) {
      summaryMessage.value = res.data.message
    } else if (bug.value) {
      bug.value.ai_summary = res.data.summary
      bug.value.ai_summary_at = new Date().toISOString()
    }
  } catch (e: any) {
    summaryMessage.value = e?.response?.data?.detail ?? 'Failed to generate summary.'
  } finally {
    summarizing.value = false
  }
}

function close() {
  closeBug()
}

function toggleRovoEdit() {
  if (!editingRovo.value) rovoContextDraft.value = bug.value?.rovo_context ?? ''
  editingRovo.value = !editingRovo.value
}

async function saveRovoContext() {
  if (!jiraRef.value) return
  savingRovo.value = true
  try {
    const res = await api.bugs.patch(jiraRef.value, { rovo_context: rovoContextDraft.value })
    if (bug.value) {
      bug.value.rovo_context = res.data.rovo_context
      bug.value.rovo_context_at = res.data.rovo_context_at
    }
    editingRovo.value = false
  } finally {
    savingRovo.value = false
  }
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) +
    ' ' + new Date(d).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}
function tierClass(tier: string) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
</script>
