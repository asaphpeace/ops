<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Jira Mapping</h2>
        <p>Jira issues seen during polling with no matching local customer · assign or dismiss each one</p>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-g btn-sm" @click="triggerPoll" :disabled="polling">
          {{ polling ? 'Polling…' : '↻ Poll Jira now' }}
        </button>
      </div>
    </div>

    <div v-if="pollResult" :class="['info-bar', pollResult.errors ? 'bar-warn' : '']" style="margin-bottom:12px">
      Poll complete — {{ pollResult.updated }} updated · {{ pollResult.skipped }} unmatched · {{ pollResult.errors }} errors
    </div>

    <div v-if="error" class="info-bar" style="border-color:var(--red);color:var(--red);background:rgba(232,68,90,.06)">
      ⚠ {{ error }}
    </div>
    <div v-if="loading" class="info-bar">Loading unmatched refs…</div>

    <div v-if="!loading && !rows.length" style="color:var(--text3);font-size:11px;padding:32px 0;text-align:center">
      No unmatched Jira refs. Everything from the last poll has been assigned or dismissed.
    </div>

    <template v-if="!loading && rows.length">
      <div class="info-bar" style="margin-bottom:12px">
        {{ rows.length }} unmatched ref{{ rows.length !== 1 ? 's' : '' }} — these Jira issues exist in your project but have no local customer. Assign each one to create a case, or dismiss to ignore it.
      </div>

      <div class="jm-list">
        <div v-for="row in rows" :key="row.jira_ref" class="jm-card">
          <!-- Header row -->
          <div class="jm-head">
            <a class="jref" :href="jiraUrl(row.jira_ref)" target="_blank" rel="noopener" title="Open in Jira">↗ {{ row.jira_ref }}</a>
            <span :class="['priority-pill', priClass(row.priority)]">{{ row.priority }}</span>
            <span class="type-pill">{{ row.case_type }}</span>
            <span v-if="row.request_type" class="label-chip">{{ row.request_type }}</span>
            <span v-for="lbl in row.labels.slice(0, 3)" :key="lbl" class="label-chip">{{ lbl }}</span>
            <span style="margin-left:auto;font-size:9px;color:var(--text3)">
              {{ row.jira_customer_name ?? 'no customer set' }} · first seen {{ row.first_seen_at }} · last seen {{ row.last_seen_at }} · {{ row.days_open }}d open
            </span>
          </div>

          <!-- Editable title -->
          <div v-if="editing[row.jira_ref]" style="margin:6px 0">
            <input
              v-model="editing[row.jira_ref].title"
              class="fi"
              style="width:100%;font-size:12px"
              placeholder="Case title"
            />
          </div>
          <div v-else class="jm-title">{{ row.title || '(no title)' }}</div>

          <!-- Assignment form (shown when assigning) -->
          <div v-if="editing[row.jira_ref]" class="jm-form">
            <select v-model="editing[row.jira_ref].customer_id" class="fi">
              <option value="" disabled>Select customer…</option>
              <option v-for="c in customers" :key="c.id" :value="c.id">
                {{ c.name }} ({{ c.tier }})
              </option>
            </select>
            <select v-model="editing[row.jira_ref].case_type" class="fi">
              <option>Defect</option>
              <option>Support</option>
              <option>Upgrade</option>
              <option>Training Gap</option>
            </select>
            <select v-model="editing[row.jira_ref].environment" class="fi">
              <option>PROD</option>
              <option>TEST</option>
              <option>DEV</option>
            </select>
            <button
              class="btn btn-sm"
              :disabled="!editing[row.jira_ref].customer_id || saving[row.jira_ref]"
              @click="assign(row.jira_ref)"
            >
              {{ saving[row.jira_ref] ? 'Saving…' : 'Assign' }}
            </button>
            <button class="btn btn-g btn-sm" @click="cancelEdit(row.jira_ref)">Cancel</button>
          </div>

          <!-- Action buttons (default state) -->
          <div v-else class="jm-actions">
            <button class="btn btn-sm" @click="startEdit(row)">Assign to customer →</button>
            <template v-if="confirmingDismiss === row.jira_ref">
              <button class="btn btn-sm" style="background:var(--red);color:#fff;border-color:var(--red)" @click="confirmDismiss(row.jira_ref)" :disabled="saving[row.jira_ref]">
                {{ saving[row.jira_ref] ? '…' : 'Confirm dismiss' }}
              </button>
              <button class="btn btn-g btn-sm" @click="cancelDismiss">Cancel</button>
            </template>
            <button v-else class="btn btn-g btn-sm" @click="startDismiss(row.jira_ref)">Dismiss</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { api, jiraUrl, type JiraUnmatched, type Customer } from '@/api/client'

const rows = ref<JiraUnmatched[]>([])
const customers = ref<Customer[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const polling = ref(false)
const pollResult = ref<{ updated: number; skipped: number; errors: number } | null>(null)

interface EditState {
  title: string
  customer_id: number | ''
  case_type: string
  environment: string
}
const editing = reactive<Record<string, EditState>>({})
const saving = reactive<Record<string, boolean>>({})
const confirmingDismiss = ref<string | null>(null)

onMounted(async () => {
  try {
    const unmatchedRes = await api.jira.unmatched()
    rows.value = unmatchedRes.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Failed to load Jira mapping data'
  } finally {
    loading.value = false
  }

  // Load customers independently — a slow/large response shouldn't block the refs list
  try {
    const custRes = await api.customers.list({ product: 'VMS' })
    customers.value = custRes.data.filter(c => c.product?.toLowerCase().includes('vms'))
  } catch {
    // non-fatal: assign form will just have an empty customer dropdown
  }
})

function startEdit(row: JiraUnmatched) {
  editing[row.jira_ref] = {
    title: row.title,
    customer_id: '',
    case_type: row.case_type,
    environment: 'PROD',
  }
}

function cancelEdit(ref: string) {
  delete editing[ref]
}

async function assign(jira_ref: string) {
  const state = editing[jira_ref]
  if (!state?.customer_id) return
  saving[jira_ref] = true
  try {
    await api.jira.assign(jira_ref, {
      customer_id: state.customer_id as number,
      title: state.title,
      case_type: state.case_type,
      environment: state.environment,
    })
    rows.value = rows.value.filter(r => r.jira_ref !== jira_ref)
    delete editing[jira_ref]
  } catch {
    // keep card open so user can retry
  } finally {
    saving[jira_ref] = false
  }
}

function startDismiss(jira_ref: string) {
  confirmingDismiss.value = jira_ref
}

function cancelDismiss() {
  confirmingDismiss.value = null
}

async function confirmDismiss(jira_ref: string) {
  saving[jira_ref] = true
  confirmingDismiss.value = null
  try {
    await api.jira.dismiss(jira_ref)
    rows.value = rows.value.filter(r => r.jira_ref !== jira_ref)
  } finally {
    saving[jira_ref] = false
  }
}

async function triggerPoll() {
  polling.value = true
  pollResult.value = null
  try {
    const res = await api.jira.poll()
    pollResult.value = res.data
    const updated = await api.jira.unmatched()
    rows.value = updated.data
  } finally {
    polling.value = false
  }
}

function priClass(p: string) {
  return p === 'High' ? 'pri-high' : p === 'Low' ? 'pri-low' : 'pri-med'
}
</script>

<style scoped>
.jm-list { display: flex; flex-direction: column; gap: 10px; }

.jm-card {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.jm-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.jm-title {
  font-size: 12px;
  color: var(--text);
  font-weight: 500;
  line-height: 1.4;
}

.jm-form {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.jm-actions {
  display: flex;
  gap: 6px;
}

.priority-pill {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: .06em;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}
.pri-high { background: rgba(255,80,80,.15); color: var(--red); }
.pri-med  { background: rgba(255,180,40,.12); color: var(--amber); }
.pri-low  { background: var(--border); color: var(--text3); }

.type-pill {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(100,150,255,.12);
  color: var(--accent);
  border: 1px solid rgba(100,150,255,.2);
}

.label-chip {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--border);
  color: var(--text3);
}

.bar-warn { border-color: rgba(255,180,40,.4); color: var(--amber); background: rgba(255,180,40,.08); }
</style>
