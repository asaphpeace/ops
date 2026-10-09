<template>
  <div class="cp-head">
    <div class="cp-head-main">
      <h1 class="cp-name">{{ customer.name }}</h1>
      <div class="cp-row-wrap">
        <span class="cp-badge">{{ customer.tier }}</span>
        <span class="cp-badge">{{ planName(customer.tier) }}</span>
        <span v-if="customer.plan" class="cp-badge">{{ customer.plan }}</span>
        <span v-if="customer.product" class="cp-badge">{{ customer.product }}</span>
        <span v-if="customer.jvm_client" class="jvm-badge" style="margin-left:0" title="Still on the old Java desktop client, not the web app">JVM client</span>
        <span class="cp-muted">CSM {{ customer.csm }}</span>
      </div>
    </div>
    <div class="cp-head-actions">
      <button class="btn btn-g btn-sm" :disabled="summarizing" @click="onSummary">
        {{ summarizing ? 'Generating…' : customer.ai_summary ? '✦ Case summary' : '✦ Summarize cases' }}
      </button>
      <button class="btn btn-g btn-sm" @click="toggleEdit">{{ editing ? '✕ Close' : '✎ Edit status' }}</button>
    </div>
  </div>

  <!-- Status: is this customer OK right now? -->
  <div class="cp-status">
    <span class="cp-stat" :class="healthTone">
      <span class="cp-stat-lbl">Health</span> {{ customer.health_score }}/100
    </span>
    <span class="cp-stat" :class="sentimentTone">
      <span class="cp-stat-lbl">Sentiment</span> {{ customer.sentiment }}
    </span>
    <span class="cp-stat" :class="churnTone">
      <span class="cp-stat-lbl">Churn risk</span> {{ customer.churn_risk }}
    </span>
    <span v-if="customer.hypercare_until" class="cp-stat" :class="hypercareOverdue ? 'warn' : 'info'" :title="customer.hypercare_reason || ''">
      <span class="cp-stat-lbl">🔥 Hypercare</span>
      {{ hypercareOverdue ? `est. ended ${fmtDate(customer.hypercare_until)}` : `until ${fmtDate(customer.hypercare_until)}` }}
      <span v-if="customer.hypercare_reason" class="cp-muted">· {{ customer.hypercare_reason }}</span>
    </span>
    <span class="cp-stat" :class="engagement ? 'warn' : ''">
      <span class="cp-stat-lbl">Last case</span>
      {{ customer.last_case_activity_at ? fmtDate(customer.last_case_activity_at) : 'none on record' }}
      <template v-if="engagement"> · {{ engagement === 'dormant' ? 'Dormant' : 'Quiet' }}</template>
    </span>
  </div>

  <div v-if="editing" class="tw cp-card cp-edit">
    <label>Health score (0–100)<input class="inp" type="number" min="0" max="100" v-model.number="form.score"></label>
    <label>Sentiment
      <select class="sel" v-model="form.sentiment"><option>Happy</option><option>Neutral</option><option>Frustrated</option><option>Escalating</option></select>
    </label>
    <label>Churn risk
      <select class="sel" v-model="form.churnRisk"><option>Low</option><option>Medium</option><option>High</option><option>Critical</option></select>
    </label>
    <label>Hypercare until<input class="inp" type="date" v-model="form.hypercareUntil"></label>
    <label class="cp-edit-wide">Hypercare reason<input class="inp" v-model="form.hypercareReason" placeholder="e.g. post-migration stabilisation"></label>
    <label>After-hours<span class="cp-check"><input type="checkbox" v-model="form.afterHoursEligible"> eligible</span></label>
    <label v-if="form.afterHoursEligible">After-hours limit / yr<input class="inp" type="number" min="0" v-model.number="form.afterHoursLimit"></label>
    <div class="cp-edit-actions">
      <button class="btn btn-sm" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
      <button v-if="customer.hypercare_until" class="btn btn-g btn-sm" :disabled="saving" @click="clearHypercare">Clear hypercare</button>
    </div>
  </div>

  <div v-for="n in stickyNotes" :key="n.id" class="sticky-note-banner cp-sticky">
    <span>📌</span>
    <span class="cp-sticky-text">{{ n.text }}</span>
    <span class="cp-muted">{{ n.author }} · {{ fmtDate(n.created_at) }}</span>
    <button class="btn btn-g btn-sm" :disabled="unpinning === n.id" @click="unpin(n)">Unpin</button>
  </div>

  <AiSummaryModal
    :open="showSummary" :title="customer.name" :summary="customer.ai_summary ?? null"
    :generated-at="customer.ai_summary_at ?? null" :loading="summarizing" :error="summaryError"
    @close="showSummary = false" @regenerate="summarize"
  />
</template>

<script setup lang="ts">
// Identity + "is this customer OK right now?" — always visible above the
// tabs. Status editing (health/sentiment/churn/hypercare/after-hours) and
// the AI case summary moved here from the retired slide-over's header.
import { ref, reactive, computed } from 'vue'
import { api, planName, engagementTier, type Customer, type CustomerNoteEntry } from '@/api/client'
import AiSummaryModal from '@/components/AiSummaryModal.vue'
import { fmtDate } from './profileUtils'

const props = defineProps<{ customer: Customer; notes: CustomerNoteEntry[] }>()
const emit = defineEmits<{ 'update:customer': [Customer]; 'notes-changed': [] }>()

const stickyNotes = computed(() => props.notes.filter(n => n.is_sticky))
const engagement = computed(() => engagementTier(props.customer.last_case_activity_at))
const hypercareOverdue = computed(() =>
  !!props.customer.hypercare_until && new Date(props.customer.hypercare_until) < new Date(new Date().toDateString())
)
const healthTone = computed(() => (props.customer.health_score > 70 ? 'ok' : props.customer.health_score > 45 ? 'warn' : 'bad'))
const sentimentTone = computed(() => {
  const s = props.customer.sentiment
  return s === 'Frustrated' || s === 'Escalating' ? 'bad' : s === 'Happy' ? 'ok' : ''
})
const churnTone = computed(() => (['High', 'Critical'].includes(props.customer.churn_risk) ? 'bad' : ''))

// ── Status edit ──
const editing = ref(false)
const saving = ref(false)
const form = reactive({ score: 50, sentiment: 'Neutral', churnRisk: 'Medium', hypercareUntil: '', hypercareReason: '', afterHoursEligible: false, afterHoursLimit: 0 })
function toggleEdit() {
  editing.value = !editing.value
  if (!editing.value) return
  const c = props.customer
  Object.assign(form, {
    score: c.health_score, sentiment: c.sentiment, churnRisk: c.churn_risk,
    hypercareUntil: c.hypercare_until ?? '', hypercareReason: c.hypercare_reason ?? '',
    afterHoursEligible: c.after_hours_eligible, afterHoursLimit: c.after_hours_limit,
  })
}
async function save() {
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      health_score: form.score, sentiment: form.sentiment, churn_risk: form.churnRisk,
      after_hours_eligible: form.afterHoursEligible, after_hours_limit: form.afterHoursLimit,
    }
    // A PATCH can't null a field, so hypercare is only sent when set;
    // clearing goes through the dedicated action.
    if (form.hypercareUntil) {
      payload.hypercare_until = form.hypercareUntil
      payload.hypercare_reason = form.hypercareReason || null
    }
    emit('update:customer', (await api.customers.patch(props.customer.id, payload)).data)
    editing.value = false
  } finally {
    saving.value = false
  }
}
async function clearHypercare() {
  saving.value = true
  try {
    emit('update:customer', (await api.customers.clearHypercare(props.customer.id)).data)
    form.hypercareUntil = ''
    form.hypercareReason = ''
  } finally {
    saving.value = false
  }
}

// ── Pinned notes ──
const unpinning = ref<number | null>(null)
async function unpin(n: CustomerNoteEntry) {
  unpinning.value = n.id
  try {
    await api.customers.setNoteSticky(props.customer.id, n.id, false)
    emit('notes-changed')
  } finally {
    unpinning.value = null
  }
}

// ── AI case summary: view the cached one instantly, generate otherwise ──
const showSummary = ref(false)
const summarizing = ref(false)
const summaryError = ref<string | null>(null)
async function onSummary() {
  if (props.customer.ai_summary) { showSummary.value = true; return }
  await summarize()
}
async function summarize() {
  summarizing.value = true
  summaryError.value = null
  showSummary.value = true
  try {
    const res = await api.customers.summarize(props.customer.id)
    if (res.data.summary) {
      emit('update:customer', { ...props.customer, ai_summary: res.data.summary, ai_summary_at: new Date().toISOString() })
    } else if (res.data.message) {
      summaryError.value = res.data.message
    }
  } catch (e: any) {
    summaryError.value = e?.response?.data?.detail ?? 'Failed to generate summary.'
  } finally {
    summarizing.value = false
  }
}
</script>
