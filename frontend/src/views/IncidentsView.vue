<template>
  <div class="view">
    <div class="sh">
      <div><h2>Platform Incidents</h2><p>Real incidents affecting the Sedna Ops app itself — not customer support cases</p></div>
    </div>

    <div class="tw" style="padding:15px 17px;margin-bottom:14px">
      <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0">
        <span>Log a new incident</span>
        <button class="btn btn-g btn-sm" @click="showForm = !showForm">{{ showForm ? 'Cancel' : '+ Log Incident' }}</button>
      </div>
      <div v-if="showForm" style="margin-top:12px;display:flex;flex-direction:column;gap:8px">
        <input class="inp" placeholder="Title — short, one-line summary" v-model="newIncident.title">
        <div style="display:flex;gap:8px">
          <select class="sel" v-model="newIncident.source" style="width:160px">
            <option value="code">code</option>
            <option value="infra">infra</option>
            <option value="ai-tooling">ai-tooling</option>
            <option value="product">product</option>
          </select>
          <select class="sel" v-model="newIncident.severity" style="width:120px">
            <option value="Critical">Critical</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </div>
        <input v-if="newIncident.source === 'product'" class="inp" placeholder="Linked VMS bug ref (optional) — e.g. VMS-12345" v-model="newIncident.linked_vms_ref">
        <input v-if="newIncident.source === 'product'" class="inp" placeholder="Fix threshold (optional) — e.g. 8.24.5. Any customer below this is affected." v-model="newIncident.affected_below_version">
        <textarea class="inp" placeholder="What happened" v-model="newIncident.detail" rows="3"></textarea>
        <textarea class="inp" placeholder="Impact (optional) — real user/data impact, if known" v-model="newIncident.impact" rows="2"></textarea>
        <button class="btn btn-sm" style="align-self:flex-start" :disabled="!newIncident.title.trim() || !newIncident.detail.trim() || saving" @click="submitIncident">
          {{ saving ? 'Saving…' : 'Log Incident' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>
    <div v-else-if="!sortedIncidents.length" class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:32px 0">No incidents logged yet.</div>

    <div v-else class="inc-list">
      <div v-for="inc in sortedIncidents" :key="inc.id" class="tw inc-card">
        <div class="inc-head">
          <span class="flag-pill" :style="inc.status === 'Open' ? 'background:var(--red-dim);color:var(--red)' : 'background:var(--green-dim);color:var(--green)'">{{ inc.status }}</span>
          <span class="flag-pill" :style="severityStyle(inc.severity)">{{ inc.severity }}</span>
          <span class="flag-pill" :style="sourceStyle(inc.source)">{{ inc.source }}</span>
          <select v-if="inc.status === 'Open'" class="sel" style="font-size:9px;padding:2px 4px" :value="inc.phase" @change="onPhaseChange(inc.id, $event)">
            <option v-for="p in PHASES" :key="p" :value="p">{{ p }}</option>
          </select>
          <span v-else class="flag-pill" style="background:var(--surface2);color:var(--text3)">{{ inc.phase }}</span>
          <span style="font-size:12px;font-weight:700;color:var(--text)">{{ inc.title }}</span>
          <span class="sub" style="margin-left:auto;font-size:9px;color:var(--text3)">detected {{ formatDate(inc.detected_at) }}</span>
        </div>
        <div class="sub" style="font-size:11px;color:var(--text2);margin-top:6px">{{ inc.detail }}</div>
        <div v-if="inc.impact" class="sub" style="font-size:10.5px;color:var(--text3);margin-top:4px">Impact: {{ inc.impact }}</div>
        <div v-if="inc.linked_vms_ref" class="sub" style="font-size:10.5px;color:var(--text3);margin-top:2px">Linked bug: {{ inc.linked_vms_ref }}</div>

        <div v-if="inc.source === 'product'" style="display:flex;align-items:center;gap:6px;margin-top:4px">
          <span v-if="editingThreshold !== inc.id" class="sub" style="font-size:10.5px;color:var(--text3)">
            Fix threshold: {{ inc.affected_below_version ? `below ${inc.affected_below_version}` : 'not set — auto-match on sync is off for this incident' }}
          </span>
          <template v-if="editingThreshold === inc.id">
            <input class="inp" style="width:110px;font-size:10px" placeholder="e.g. 8.24.5" v-model="thresholdDraft">
            <button class="btn btn-sm" style="font-size:9px;padding:2px 6px" @click="saveThreshold(inc.id)">Save</button>
            <button class="btn btn-g btn-sm" style="font-size:9px;padding:2px 6px" @click="editingThreshold = null">Cancel</button>
          </template>
          <button v-else class="btn btn-g btn-sm" style="font-size:9px;padding:2px 6px" @click="startEditThreshold(inc)">{{ inc.affected_below_version ? 'Edit' : '+ Set threshold' }}</button>
        </div>

        <div v-if="inc.source === 'product'" class="inc-remediation">
          <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;flex-wrap:wrap;gap:6px">
            <span>Affected Customers</span>
            <div style="display:flex;gap:6px">
              <button v-if="remediationsByIncident[inc.id]?.length" class="btn btn-g btn-sm" @click="notifyAffectedCustomers(inc.id)">📢 Notify affected customers</button>
              <button class="btn btn-g btn-sm" @click="addingCustomerFor = addingCustomerFor === inc.id ? null : inc.id">
                {{ addingCustomerFor === inc.id ? 'Cancel' : '+ Add affected customer' }}
              </button>
            </div>
          </div>

          <div v-if="!remediationsByIncident[inc.id]" class="sub" style="font-size:10.5px;color:var(--text3)">Loading…</div>
          <div v-else-if="!remediationsByIncident[inc.id].length" class="sub" style="font-size:10.5px;color:var(--text3)">No affected customers listed yet.</div>
          <div v-else class="inc-rem-list">
            <div v-for="r in sortedRemediations(inc.id)" :key="r.id">
              <div class="inc-rem-row">
                <span class="flag-pill" :style="remediationStyle(r.derived_status)">{{ r.derived_status }}</span>
                <span style="font-size:11px;color:var(--text)">{{ r.customer_name }}</span>
                <span :class="['tier-badge', tierClass(r.customer_tier)]">{{ r.customer_tier }}</span>
                <span v-if="r.notified" class="flag-pill" style="background:var(--green-dim);color:var(--green)" title="Notified via a Sent campaign or manual toggle">✓ notified</span>
                <button v-else class="btn btn-g btn-sm" style="padding:2px 6px;font-size:9px" @click="markNotified(inc.id, r)">Mark notified</button>
                <template v-if="r.derived_status === 'In progress'">
                  <span v-if="r.upgrade_id" class="sub" style="font-size:9px;color:var(--text3);margin-left:auto">→ {{ r.upgrade_to_version }} ({{ r.upgrade_stage }})</span>
                  <button v-else class="btn btn-g btn-sm" :style="`margin-left:${r.upgrade_id ? '0' : 'auto'};padding:2px 6px;font-size:9px`" @click="linkingUpgradeFor = linkingUpgradeFor === r.id ? null : r.id">Link upgrade</button>
                  <button class="btn btn-g btn-sm" style="padding:2px 6px;font-size:9px" @click="manualResolveFor = manualResolveFor === r.id ? null : r.id">Resolve manually</button>
                  <button class="btn btn-g btn-sm" style="padding:2px 6px;font-size:9px" @click="mitigationFor = mitigationFor === r.id ? null : r.id">Accept risk / workaround</button>
                </template>
                <span v-else-if="r.mitigation_type" class="sub" style="font-size:9px;color:var(--text3);margin-left:auto">{{ r.mitigation_owner }} · {{ r.mitigation_note }}</span>
              </div>
              <div v-if="linkingUpgradeFor === r.id" style="margin:4px 0 4px 0">
                <select class="sel" style="font-size:10px" @change="onLinkUpgrade(inc.id, r, $event)">
                  <option value="">Select an existing Upgrade…</option>
                  <option v-for="u in upgradeOptionsFor(r.customer_id)" :key="u.id" :value="u.id">{{ u.to_version }} — {{ u.stage }}</option>
                </select>
              </div>
              <div v-if="manualResolveFor === r.id" style="margin:4px 0;display:flex;gap:6px;align-items:center">
                <input class="inp" style="font-size:10px" placeholder="Notes — why this needed no upgrade" v-model="manualResolveNotes">
                <button class="btn btn-sm" style="font-size:9px" :disabled="!manualResolveNotes.trim()" @click="confirmManualResolve(inc.id, r)">Confirm</button>
              </div>
              <div v-if="mitigationFor === r.id" style="margin:4px 0;display:flex;flex-direction:column;gap:6px;padding:6px;background:var(--surface2);border-radius:6px">
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                  <select class="sel" style="font-size:10px" v-model="mitigationDraft.mitigation_type">
                    <option value="accepted_risk">Accepted risk</option>
                    <option value="workaround_applied">Workaround applied</option>
                  </select>
                  <input class="inp" style="font-size:10px;width:130px" placeholder="Owner" v-model="mitigationDraft.mitigation_owner">
                  <input class="inp" style="font-size:10px;width:120px" type="date" v-model="mitigationDraft.review_by_date">
                </div>
                <input class="inp" style="font-size:10px" placeholder="Note — why accepted, or what the workaround is" v-model="mitigationDraft.mitigation_note">
                <button class="btn btn-sm" style="font-size:9px;align-self:flex-start" :disabled="!mitigationDraft.mitigation_owner.trim() || !mitigationDraft.mitigation_note.trim() || !mitigationDraft.review_by_date" @click="confirmMitigation(inc.id, r)">Confirm</button>
              </div>
            </div>
          </div>

          <div v-if="addingCustomerFor === inc.id" class="inc-add-form">
            <input class="inp" placeholder="Search customers…" v-model="customerSearch" style="margin-top:8px">
            <div style="display:flex;gap:6px;align-items:center;margin-top:6px;flex-wrap:wrap">
              <button v-if="inc.linked_vms_ref" class="btn btn-g btn-sm" @click="loadSuggestions(inc.id)">Suggest from linked bug's fix version</button>
              <span class="sub" style="font-size:9px;color:var(--text3)">or</span>
              <input class="inp" style="width:110px;font-size:10px" placeholder="e.g. 8.24.5" v-model="minVersionInput">
              <button class="btn btn-g btn-sm" :disabled="!minVersionInput.trim()" @click="loadSuggestions(inc.id, minVersionInput.trim())">Suggest customers below this version</button>
            </div>
            <div v-if="suggestions.length" class="sub" style="font-size:10px;color:var(--text3);margin-top:4px">
              <div style="margin-bottom:4px">
                Suggested ({{ suggestions.length }} — real PROD version on file, below the threshold):
                <button class="btn btn-sm" style="font-size:9px;padding:2px 6px;margin-left:6px" :disabled="addingAllSuggested" @click="addAllSuggested(inc.id)">{{ addingAllSuggested ? 'Adding…' : `+ Add all ${suggestions.length}` }}</button>
              </div>
              <span v-for="s in suggestions" :key="s.id" class="inc-suggest-chip" @click="addRemediation(inc.id, s.id)">{{ s.name }} ({{ s.prod_version }})</span>
            </div>
            <div class="inc-cust-list">
              <div v-for="c in filteredCustomers" :key="c.id" class="inc-cust-row" @click="addRemediation(inc.id, c.id)">
                {{ c.name }} <span class="sub">{{ c.tier }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="inc.status === 'Open' && inc.source === 'product' && outstandingNames(inc.id).length" class="sub" style="font-size:10px;color:var(--red);margin-top:6px">
          ⚠ {{ outstandingNames(inc.id).length }} affected customer(s) haven't completed their upgrade yet: {{ outstandingNames(inc.id).join(', ') }}
        </div>

        <!-- STAKEHOLDER DECISIONS / TIMELINE -->
        <div style="margin-top:8px">
          <button class="btn btn-g btn-sm" @click="toggleTimeline(inc.id)">{{ expandedTimeline === inc.id ? 'Hide' : 'Show' }} decisions & timeline</button>
          <div v-if="expandedTimeline === inc.id" style="margin-top:6px;padding:8px;background:var(--surface2);border-radius:6px">
            <div style="display:flex;gap:6px;margin-bottom:8px">
              <input class="inp" style="font-size:10px" placeholder="Log a decision — e.g. Engineering: no backport planned" v-model="decisionDraft">
              <button class="btn btn-sm" style="font-size:9px" :disabled="!decisionDraft.trim() || loggingDecision" @click="submitDecision(inc.id)">{{ loggingDecision ? 'Logging…' : 'Log' }}</button>
            </div>
            <div v-if="!timelineByIncident[inc.id]" class="sub" style="font-size:10px;color:var(--text3)">Loading…</div>
            <div v-else-if="!timelineByIncident[inc.id].length" class="sub" style="font-size:10px;color:var(--text3)">No recorded events for this incident yet.</div>
            <div v-else style="display:flex;flex-direction:column;gap:4px">
              <div v-for="(t, i) in timelineByIncident[inc.id]" :key="i" class="sub" style="font-size:10px;color:var(--text2)">
                <span style="color:var(--text3)">{{ formatDate(t.created_at) }}</span> — {{ t.detail || t.action }}
              </div>
            </div>
          </div>
        </div>

        <template v-if="inc.status === 'Resolved'">
          <div class="sub" style="font-size:10.5px;color:var(--text3);margin-top:6px">
            Resolved {{ formatDate(inc.resolved_at) }}
          </div>
          <div class="sub" style="font-size:10.5px;color:var(--text2);margin-top:4px"><strong>Root cause:</strong> {{ inc.root_cause }}</div>
          <div class="sub" style="font-size:10.5px;color:var(--text2);margin-top:2px"><strong>Resolution:</strong> {{ inc.resolution }}</div>
          <div v-if="inc.lessons_learned" class="sub" style="font-size:10.5px;color:var(--text2);margin-top:2px"><strong>Lessons learned:</strong> {{ inc.lessons_learned }}</div>
          <div v-if="inc.detection_gap" class="sub" style="font-size:10.5px;color:var(--text2);margin-top:2px"><strong>Detection gap:</strong> {{ inc.detection_gap }}</div>
        </template>

        <template v-else>
          <button
            v-if="expandedResolve !== inc.id"
            class="btn btn-g btn-sm"
            style="margin-top:8px"
            :disabled="!canResolve(inc)"
            :title="!canResolve(inc) ? 'Resolve all affected customers\' remediations first' : ''"
            @click="startResolve(inc.id)"
          >Mark Resolved</button>
          <div v-else style="margin-top:8px;display:flex;flex-direction:column;gap:6px">
            <textarea class="inp" placeholder="Root cause" v-model="resolveDraft[inc.id].root_cause" rows="2"></textarea>
            <textarea class="inp" placeholder="Resolution — e.g. fixed in commit X, rolled back migration Y" v-model="resolveDraft[inc.id].resolution" rows="2"></textarea>
            <textarea class="inp" placeholder="Lessons learned (optional)" v-model="resolveDraft[inc.id].lessons_learned" rows="2"></textarea>
            <textarea class="inp" placeholder="Detection gap (optional) — how was this caught, could it have been sooner" v-model="resolveDraft[inc.id].detection_gap" rows="2"></textarea>
            <div style="display:flex;gap:8px">
              <button
                class="btn btn-sm"
                :disabled="!resolveDraft[inc.id].root_cause.trim() || !resolveDraft[inc.id].resolution.trim() || resolving === inc.id"
                @click="confirmResolve(inc.id)"
              >{{ resolving === inc.id ? 'Saving…' : 'Confirm Resolved' }}</button>
              <button class="btn btn-g btn-sm" @click="expandedResolve = null">Cancel</button>
            </div>
            <div v-if="resolveError" class="sub" style="font-size:10.5px;color:var(--red)">⚠ {{ resolveError }}</div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, type Incident, type IncidentRemediation, type IncidentCustomerCandidate, type IncidentTimelineEntry, type Customer, type Upgrade } from '@/api/client'

const router = useRouter()

const PHASES = ['Detected', 'Fix Identified', 'Fix Released', 'Remediating Customers', 'Closed'] as const

const incidents = ref<Incident[]>([])
const loading = ref(true)
const showForm = ref(false)
const saving = ref(false)
const expandedResolve = ref<number | null>(null)
const resolving = ref<number | null>(null)

const newIncident = reactive({ title: '', source: 'code', severity: 'Medium', detail: '', impact: '', linked_vms_ref: '', affected_below_version: '' })
const editingThreshold = ref<number | null>(null)
const thresholdDraft = ref('')
const resolveDraft = reactive<Record<number, { root_cause: string; resolution: string; lessons_learned: string; detection_gap: string }>>({})

// Decisions / timeline
const expandedTimeline = ref<number | null>(null)
const timelineByIncident = reactive<Record<number, IncidentTimelineEntry[]>>({})
const decisionDraft = ref('')
const loggingDecision = ref(false)

// Mitigation (accepted risk / workaround) path
const mitigationFor = ref<number | null>(null)
const mitigationDraft = reactive({ mitigation_type: 'accepted_risk', mitigation_owner: '', mitigation_note: '', review_by_date: '' })

// Affected-customer remediation state
const remediationsByIncident = reactive<Record<number, IncidentRemediation[]>>({})
const allCustomers = ref<Customer[]>([])
const customerSearch = ref('')
// Lets a human suggest customers by a known fix version directly, without
// needing a correctly-linked VmsBug first — confirmed live this was the
// real blocker (a placeholder linked_vms_ref with no matching VmsBug row
// silently produced zero suggestions).
const minVersionInput = ref('')
const addingCustomerFor = ref<number | null>(null)
const linkingUpgradeFor = ref<number | null>(null)
const manualResolveFor = ref<number | null>(null)
const manualResolveNotes = ref('')
const suggestions = ref<IncidentCustomerCandidate[]>([])
const upgradesByCustomer = reactive<Record<number, Upgrade[]>>({})

const filteredCustomers = computed(() => {
  const q = customerSearch.value.trim().toLowerCase()
  if (!q) return []
  return allCustomers.value.filter(c => c.name.toLowerCase().includes(q)).slice(0, 15)
})

function outstandingNames(incidentId: number): string[] {
  const rows = remediationsByIncident[incidentId]
  if (!rows) return []
  return rows.filter(r => r.derived_status === 'In progress').map(r => r.customer_name || `customer ${r.customer_id}`)
}

function canResolve(inc: Incident): boolean {
  if (inc.source !== 'product') return true
  const rows = remediationsByIncident[inc.id]
  if (!rows) return false // still loading — don't allow resolving until we know
  return rows.every(r => r.derived_status !== 'In progress')
}

function remediationStyle(status: string) {
  if (status === 'Done') return 'background:var(--green-dim);color:var(--green)'
  if (status === 'Resolved (manual)') return 'background:var(--surface3);color:var(--text3)'
  if (status.startsWith('Accepted risk') || status === 'Workaround applied') return 'background:var(--surface3);color:var(--text2)'
  return 'background:var(--amber-dim);color:var(--amber)'
}

function severityStyle(severity: string) {
  if (severity === 'Critical') return 'background:var(--red-dim);color:var(--red)'
  if (severity === 'High') return 'background:var(--amber-dim);color:var(--amber)'
  if (severity === 'Medium') return 'background:var(--accent-dim);color:var(--accent)'
  return 'background:var(--surface2);color:var(--text3)'
}

function tierClass(tier?: string | null) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}

// Tier-weighted, not schema — Premier before Strategic before Scale, since
// a Premier customer stuck below the fix threshold is a bigger business
// risk than a Scale one at the same technical severity.
const TIER_RANK: Record<string, number> = { Premier: 0, Strategic: 1, Scale: 2 }
function sortedRemediations(incidentId: number): IncidentRemediation[] {
  const rows = remediationsByIncident[incidentId]
  if (!rows) return []
  return [...rows].sort((a, b) => (TIER_RANK[a.customer_tier ?? ''] ?? 3) - (TIER_RANK[b.customer_tier ?? ''] ?? 3))
}

async function onPhaseChange(incidentId: number, event: Event) {
  const phase = (event.target as HTMLSelectElement).value
  const res = await api.incidents.patch(incidentId, { phase })
  const idx = incidents.value.findIndex(i => i.id === incidentId)
  if (idx >= 0) incidents.value.splice(idx, 1, res.data)
}

async function markNotified(incidentId: number, r: IncidentRemediation) {
  await api.incidents.notifyRemediation(incidentId, r.id)
  await loadRemediations(incidentId)
}

function notifyAffectedCustomers(incidentId: number) {
  router.push(`/customers/comms?incident=${incidentId}`)
}

async function toggleTimeline(incidentId: number) {
  if (expandedTimeline.value === incidentId) {
    expandedTimeline.value = null
    return
  }
  expandedTimeline.value = incidentId
  if (!timelineByIncident[incidentId]) {
    const res = await api.incidents.timeline(incidentId)
    timelineByIncident[incidentId] = res.data
  }
}

async function submitDecision(incidentId: number) {
  loggingDecision.value = true
  try {
    await api.incidents.logDecision(incidentId, decisionDraft.value.trim())
    decisionDraft.value = ''
    const res = await api.incidents.timeline(incidentId)
    timelineByIncident[incidentId] = res.data
  } finally {
    loggingDecision.value = false
  }
}

async function confirmMitigation(incidentId: number, r: IncidentRemediation) {
  await api.incidents.patchRemediation(incidentId, r.id, {
    mitigation_type: mitigationDraft.mitigation_type,
    mitigation_owner: mitigationDraft.mitigation_owner.trim(),
    mitigation_note: mitigationDraft.mitigation_note.trim(),
    review_by_date: mitigationDraft.review_by_date,
  })
  mitigationFor.value = null
  mitigationDraft.mitigation_owner = ''
  mitigationDraft.mitigation_note = ''
  mitigationDraft.review_by_date = ''
  await loadRemediations(incidentId)
}

function startEditThreshold(inc: Incident) {
  thresholdDraft.value = inc.affected_below_version ?? ''
  editingThreshold.value = inc.id
}

async function saveThreshold(incidentId: number) {
  const res = await api.incidents.patch(incidentId, { affected_below_version: thresholdDraft.value.trim() || null })
  const idx = incidents.value.findIndex(i => i.id === incidentId)
  if (idx >= 0) incidents.value.splice(idx, 1, res.data)
  editingThreshold.value = null
}

async function loadRemediations(incidentId: number) {
  const res = await api.incidents.get(incidentId)
  remediationsByIncident[incidentId] = res.data.remediations
}

async function addRemediation(incidentId: number, customerId: number) {
  await api.incidents.addRemediation(incidentId, { customer_id: customerId })
  customerSearch.value = ''
  suggestions.value = []
  addingCustomerFor.value = null
  await loadRemediations(incidentId)
}

async function loadSuggestions(incidentId: number, minVersion?: string) {
  const res = await api.incidents.suggestCustomers(incidentId, minVersion)
  suggestions.value = res.data
}

const addingAllSuggested = ref(false)
async function addAllSuggested(incidentId: number) {
  addingAllSuggested.value = true
  try {
    // Sequential, not Promise.all — add_remediation() 400s on a duplicate
    // customer, and a partial batch (some added, one skipped) shouldn't
    // abort the rest.
    for (const s of suggestions.value) {
      try {
        await api.incidents.addRemediation(incidentId, { customer_id: s.id })
      } catch { /* already listed, or a real error — either way, keep going */ }
    }
    suggestions.value = []
    await loadRemediations(incidentId)
  } finally {
    addingAllSuggested.value = false
  }
}

async function upgradeOptionsForAsync(customerId: number) {
  if (!upgradesByCustomer[customerId]) {
    const res = await api.upgrades.list({ customer_id: String(customerId) })
    upgradesByCustomer[customerId] = res.data
  }
}
function upgradeOptionsFor(customerId: number): Upgrade[] {
  if (!upgradesByCustomer[customerId]) {
    upgradeOptionsForAsync(customerId)
    return []
  }
  return upgradesByCustomer[customerId]
}

async function onLinkUpgrade(incidentId: number, remediation: IncidentRemediation, event: Event) {
  const upgradeId = Number((event.target as HTMLSelectElement).value)
  if (!upgradeId) return
  await api.incidents.patchRemediation(incidentId, remediation.id, { upgrade_id: upgradeId })
  linkingUpgradeFor.value = null
  await loadRemediations(incidentId)
}

async function confirmManualResolve(incidentId: number, remediation: IncidentRemediation) {
  await api.incidents.patchRemediation(incidentId, remediation.id, {
    manually_resolved: true, notes: manualResolveNotes.value.trim(),
  })
  manualResolveFor.value = null
  manualResolveNotes.value = ''
  await loadRemediations(incidentId)
}

const sortedIncidents = computed(() => {
  return [...incidents.value].sort((a, b) => {
    const rank = (s: string) => (s === 'Open' ? 0 : 1)
    if (rank(a.status) !== rank(b.status)) return rank(a.status) - rank(b.status)
    return new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime()
  })
})

function sourceStyle(source: string) {
  if (source === 'code') return 'background:var(--accent-dim);color:var(--accent)'
  if (source === 'infra') return 'background:var(--amber-dim);color:var(--amber)'
  return 'background:var(--purple-dim);color:var(--purple)'
}

function formatDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

async function loadIncidents() {
  loading.value = true
  try {
    const res = await api.incidents.list()
    incidents.value = res.data
    await Promise.all(
      incidents.value.filter(i => i.source === 'product').map(i => loadRemediations(i.id))
    )
  } finally {
    loading.value = false
  }
}

async function submitIncident() {
  saving.value = true
  try {
    await api.incidents.create({
      title: newIncident.title.trim(),
      source: newIncident.source,
      severity: newIncident.severity,
      detail: newIncident.detail.trim(),
      impact: newIncident.impact.trim() || undefined,
      linked_vms_ref: newIncident.linked_vms_ref.trim() || undefined,
      affected_below_version: newIncident.affected_below_version.trim() || undefined,
    })
    newIncident.title = ''
    newIncident.detail = ''
    newIncident.impact = ''
    newIncident.linked_vms_ref = ''
    newIncident.affected_below_version = ''
    newIncident.source = 'code'
    newIncident.severity = 'Medium'
    showForm.value = false
    await loadIncidents()
  } finally {
    saving.value = false
  }
}

function startResolve(id: number) {
  resolveDraft[id] = { root_cause: '', resolution: '', lessons_learned: '', detection_gap: '' }
  resolveError.value = null
  expandedResolve.value = id
}

const resolveError = ref<string | null>(null)

async function confirmResolve(id: number) {
  const draft = resolveDraft[id]
  resolving.value = id
  resolveError.value = null
  try {
    await api.incidents.patch(id, {
      status: 'Resolved',
      root_cause: draft.root_cause.trim(),
      resolution: draft.resolution.trim(),
      lessons_learned: draft.lessons_learned.trim() || undefined,
      detection_gap: draft.detection_gap.trim() || undefined,
    })
    expandedResolve.value = null
    await loadIncidents()
  } catch (e: any) {
    resolveError.value = e?.response?.data?.detail ?? 'Could not resolve this incident.'
  } finally {
    resolving.value = null
  }
}

onMounted(async () => {
  await loadIncidents()
  const res = await api.customers.list()
  allCustomers.value = res.data
})
</script>

<style scoped>
.inc-list { display: flex; flex-direction: column; gap: 10px; }
.inc-card { padding: 12px 14px; }
.inc-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.inc-remediation { margin-top: 10px; padding: 10px; background: var(--surface2); border-radius: 7px; }
.inc-rem-list { display: flex; flex-direction: column; gap: 4px; }
.inc-rem-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; flex-wrap: wrap; }
.inc-cust-list { max-height: 160px; overflow-y: auto; margin-top: 6px; }
.inc-cust-row { font-size: 11px; padding: 5px 6px; border-radius: 5px; cursor: pointer; }
.inc-cust-row:hover { background: var(--surface3); }
.inc-suggest-chip { display: inline-block; font-size: 10px; color: var(--accent); background: var(--accent-dim); border-radius: 4px; padding: 2px 6px; margin: 2px 4px 2px 0; cursor: pointer; }
</style>
