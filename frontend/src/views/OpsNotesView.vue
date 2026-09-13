<template>
  <div class="view">
    <div class="sh">
      <div><h2>Ops Notes</h2><p>Real operational context from outside this app — Slack discussion, hallway conversations — pasted in by hand and folded into AI summaries and the Ollama supervisor</p></div>
    </div>

    <div class="tw" style="padding:15px 17px;margin-bottom:14px">
      <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0">
        <span>+ Add a note</span>
        <button class="btn btn-g btn-sm" @click="showForm = !showForm">{{ showForm ? 'Cancel' : '+ Add Note' }}</button>
      </div>
      <div v-if="showForm" style="margin-top:12px;display:flex;flex-direction:column;gap:8px">
        <textarea class="inp" placeholder="Paste the whole thread — every message in it, not just one — plus anything else worth knowing…" v-model="draft.text" rows="8"></textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <input class="inp" style="width:220px" placeholder="Channel (optional)" v-model="draft.source_label" list="ops-note-channels">
          <datalist id="ops-note-channels">
            <option v-for="ch in SLACK_CHANNELS" :key="ch" :value="ch" />
          </datalist>
          <input class="inp" style="width:160px" placeholder="Jira ref (optional) — e.g. DSD-1234" v-model="draft.jira_ref">
          <input class="inp" style="width:220px" placeholder="Search customer (optional)…" v-model="customerSearch" @focus="showCustomerList = true">
        </div>
        <div v-if="showCustomerList && filteredCustomers.length" class="on-cust-list">
          <div v-for="c in filteredCustomers" :key="c.id" class="on-cust-row" @click="pickCustomer(c)">
            {{ c.name }} <span class="sub">{{ c.tier }}</span>
          </div>
        </div>
        <div v-if="draft.customer_id" style="font-size:10.5px;color:var(--text3)">
          Tagged to: {{ draft.customer_name }}
          <span class="jref" style="margin-left:6px" @click="draft.customer_id = null; draft.customer_name = ''">✕ clear</span>
        </div>
        <button class="btn btn-sm" style="align-self:flex-start" :disabled="!draft.text.trim() || saving" @click="submitNote">
          {{ saving ? 'Saving…' : 'Save Note' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>
    <div v-else-if="!notes.length" class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:32px 0">No ops notes yet.</div>

    <div v-else class="on-list">
      <div v-for="n in notes" :key="n.id" class="tw on-card">
        <div class="on-head">
          <span v-if="n.source_label" class="flag-pill" style="background:var(--surface3);color:var(--text3)">{{ n.source_label }}</span>
          <span v-if="n.customer_name" class="td-name" style="cursor:pointer" @click="goToCustomer(n.customer_id!, 'overview')">{{ n.customer_name }}</span>
          <span v-if="n.jira_ref" class="jref" @click="openCase(n.jira_ref!)">{{ n.jira_ref }}</span>
          <span class="sub" style="margin-left:auto;font-size:9px;color:var(--text3)">{{ formatDate(n.created_at) }}</span>
          <span class="jref" style="font-size:9px" @click="deleteNote(n.id)">✕</span>
        </div>
        <div class="sub" style="font-size:11px;color:var(--text2);margin-top:6px;white-space:pre-wrap">{{ n.text }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { api, type OpsNote, type Customer } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { useCaseDrill } from '@/composables/useCaseDrill'

const { openCustomer: goToCustomer } = useCustomerDrill()
const { openCase } = useCaseDrill()

const notes = ref<OpsNote[]>([])
const loading = ref(true)
const showForm = ref(false)
const saving = ref(false)

// The real channels this app's Slack workspace context comes from — no
// Slack API access exists to look these up live (see OpsNote's own
// docstring), so this is just a quick-pick list for the free-text
// source_label field, not a structured/validated set.
const SLACK_CHANNELS = [
  '#cs-saga-welco-stabilisation-project', '#cs-support-vms', '#customer-success',
  '#data-squad', '#oce-bergen', '#oce-south-africa', '#sedna-team-hq', '#shout-outs',
  '#vms-cs-team', '#vms-devops-stakeholders', '#vms-engineering',
  '#vms-jira-support-feed', '#vms-jira-support-p1', '#vms-release', '#vms-support-discussion',
]

const draft = reactive({ text: '', source_label: '', jira_ref: '', customer_id: null as number | null, customer_name: '' })
const allCustomers = ref<Customer[]>([])
const customerSearch = ref('')
const showCustomerList = ref(false)

const filteredCustomers = computed(() => {
  const q = customerSearch.value.trim().toLowerCase()
  if (!q) return []
  return allCustomers.value.filter(c => c.name.toLowerCase().includes(q)).slice(0, 10)
})

function pickCustomer(c: Customer) {
  draft.customer_id = c.id
  draft.customer_name = c.name
  customerSearch.value = ''
  showCustomerList.value = false
}

function formatDate(d: string) {
  return new Date(d).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadNotes() {
  loading.value = true
  try {
    const res = await api.opsNotes.list()
    notes.value = res.data
  } finally {
    loading.value = false
  }
}

async function submitNote() {
  saving.value = true
  try {
    await api.opsNotes.create({
      text: draft.text.trim(),
      source_label: draft.source_label.trim() || undefined,
      jira_ref: draft.jira_ref.trim() || undefined,
      customer_id: draft.customer_id ?? undefined,
    })
    draft.text = ''
    draft.source_label = ''
    draft.jira_ref = ''
    draft.customer_id = null
    draft.customer_name = ''
    showForm.value = false
    await loadNotes()
  } finally {
    saving.value = false
  }
}

async function deleteNote(id: number) {
  await api.opsNotes.delete(id)
  await loadNotes()
}

onMounted(async () => {
  await loadNotes()
  const res = await api.customers.list()
  allCustomers.value = res.data
})
</script>

<style scoped>
.on-list { display: flex; flex-direction: column; gap: 10px; }
.on-card { padding: 12px 14px; }
.on-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.on-cust-list { max-height: 140px; overflow-y: auto; background: var(--surface2); border-radius: 6px; padding: 4px; }
.on-cust-row { font-size: 11px; padding: 5px 6px; border-radius: 5px; cursor: pointer; }
.on-cust-row:hover { background: var(--surface3); }
</style>
