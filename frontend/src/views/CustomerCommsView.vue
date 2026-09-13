<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Customer Comms</h2>
        <p>Real Jira contacts + a draft you copy into your own email client · no sending happens here</p>
      </div>
      <RouterLink to="/customers" class="btn btn-g btn-sm">← Back to Customers</RouterLink>
    </div>

    <!-- CAMPAIGN HISTORY -->
    <div class="tw" style="padding:15px 17px;margin-bottom:16px">
      <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between">
        <span>Campaign History</span>
        <button class="btn btn-sm" @click="newCampaign">+ New Campaign</button>
      </div>
      <div v-if="!campaigns.length" class="sub" style="font-size:11px;color:var(--text3)">No campaigns yet.</div>
      <table v-else>
        <thead><tr><th>Name</th><th>Status</th><th>Customers</th><th>Created</th><th>Sent</th></tr></thead>
        <tbody>
          <tr v-for="c in campaigns" :key="c.id" class="cc-hist-row" :class="{ active: currentCampaign.id === c.id }" @click="openCampaign(c.id)">
            <td class="td-name">{{ c.name }}</td>
            <td><span class="flag-pill" :style="c.status === 'Sent' ? 'background:var(--green-dim);color:var(--green)' : 'background:var(--surface2);color:var(--text3)'">{{ c.status }}</span></td>
            <td>{{ c.customer_count }}</td>
            <td class="sub">{{ formatDate(c.created_at) }}</td>
            <td class="sub">{{ c.sent_at ? formatDate(c.sent_at) : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="tw" style="padding:15px 17px;margin-bottom:16px">
      <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between">
        <span>{{ currentCampaign.id ? `Editing: ${currentCampaign.name || '(untitled)'}` : 'New Campaign' }}</span>
        <span v-if="isReadOnly" class="flag-pill" style="background:var(--green-dim);color:var(--green)">Sent — read-only</span>
      </div>
      <div v-if="sourceIncidentTitle" class="sub" style="font-size:10.5px;color:var(--accent);margin-bottom:6px">📢 Notifying affected customers for incident: {{ sourceIncidentTitle }}</div>
      <input class="inp" style="width:100%;margin-bottom:4px" placeholder="Campaign name, e.g. Maintenance Window — 5 Sept 2026" v-model="currentCampaign.name" :disabled="isReadOnly">
    </div>

    <!-- STEP 1: SEGMENT -->
    <div class="tw" style="padding:15px 17px;margin-bottom:16px">
      <div class="md-eyebrow">1. Choose the segment <span class="md-period">· {{ includedCount }} of {{ customers.length }} customers included</span></div>
      <div class="ttb" style="padding:0 0 10px">
        <input class="inp" style="width:190px" placeholder="Search customers..." v-model="search">
        <select class="sel" v-model="filterTier">
          <option value="">All tiers</option>
          <option>Premier</option>
          <option>Strategic</option>
          <option>Scale</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text2);white-space:nowrap;cursor:pointer" title="Hides Email-only, CompassAir-only, and no-product-tagged customers — a Jira contact resolve is only meaningful for real VMS customers">
          <input type="checkbox" v-model="vmsOnly" :disabled="isReadOnly">
          VMS customers only
        </label>
        <button class="btn btn-g btn-sm" :disabled="isReadOnly" @click="includeAll">Include all</button>
        <button class="btn btn-g btn-sm" :disabled="isReadOnly" @click="excludeAll">Exclude all</button>
      </div>
      <div class="nc-grid">
        <label v-for="c in filtered" :key="c.id" class="nc-row" :class="{ excluded: !included[c.id] }">
          <input type="checkbox" v-model="included[c.id]" :disabled="isReadOnly">
          <span class="td-name">{{ c.name }}</span>
          <span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span>
        </label>
        <div v-if="!filtered.length" class="sub" style="color:var(--text3);padding:12px;text-align:center">No customers match filters.</div>
      </div>
    </div>

    <!-- STEP 2: RESOLVE CONTACTS -->
    <div class="tw" style="padding:15px 17px;margin-bottom:16px">
      <div class="md-eyebrow" style="display:flex;align-items:center;justify-content:space-between">
        <span>2. Resolve real contacts via Jira</span>
        <button class="btn btn-sm" :disabled="!includedCount || resolving" @click="resolveContacts">
          {{ resolving ? 'Resolving…' : `Resolve Contacts (${includedCount})` }}
        </button>
      </div>
      <div v-if="!resolutions.length" class="sub" style="font-size:11px;color:var(--text3)">Not resolved yet.</div>
      <template v-else>
        <div class="nc-actions">
          <button class="btn btn-g btn-sm" @click="copyAllEmails">
            {{ copied ? '✓ Copied' : copyFailed ? '✕ Copy failed — select manually' : `Copy main contacts (${totalEmails})` }}
          </button>
          <a class="btn btn-g btn-sm" style="text-decoration:none" :href="csvHref" download="customer-comms-contacts.csv">⭳ Export CSV</a>
          <span v-if="undesignatedCount" class="sub" style="color:var(--amber)">⚠ {{ undesignatedCount }} customer{{ undesignatedCount === 1 ? '' : 's' }} with no main contact designated — every real email included for {{ undesignatedCount === 1 ? 'them' : 'those' }} instead</span>
        </div>
        <div v-for="r in resolutions" :key="r.customer_id" class="nc-result-row">
          <button type="button" class="nc-result-head" @click="toggleExpanded(r.customer_id)">
            <span class="nc-caret">{{ expanded === r.customer_id ? '▾' : '▸' }}</span>
            <span class="td-name">{{ r.customer_name }}</span>
            <span v-if="r.email_count === 0" class="flag-pill" style="background:var(--red-dim);color:var(--red)">⚠ No emails found</span>
            <span v-else-if="r.jira_org_matched && r.email_count < r.member_count / 2" class="flag-pill" style="background:var(--amber-dim);color:var(--amber)">⚠ Thin coverage — verify manually</span>
            <span v-else-if="!r.jira_org_matched" class="flag-pill" style="background:var(--surface2);color:var(--text3)" title="No Jira Service Management org exists for this customer — these contacts came from the stored Contacts list instead">Stored contacts only</span>
            <span v-if="r.email_count > 1 && !r.primary_contact_email" class="flag-pill" style="background:var(--amber-dim);color:var(--amber)">⚠ No main contact — sending to all {{ r.email_count }}</span>
            <span class="sub" style="margin-left:auto;color:var(--text3)">{{ r.primary_contact_email ?? (r.jira_org_matched ? `${r.email_count} / ${r.member_count} contacts` : `${r.email_count} contact${r.email_count === 1 ? '' : 's'}`) }}</span>
          </button>
          <div v-if="expanded === r.customer_id" class="nc-contacts">
            <div v-for="(c, i) in r.contacts" :key="i" class="nc-contact-row">
              <span>{{ c.primary ? '⭐ ' : '' }}{{ c.name ?? 'Unknown' }}</span>
              <span :style="!c.email ? 'color:var(--text3);font-style:italic' : ''">{{ c.email ?? 'no email exposed' }}</span>
            </div>
            <div v-if="!r.contacts.length" class="sub" style="color:var(--text3)">No org members found.</div>
          </div>
        </div>
      </template>
    </div>

    <!-- STEP 3: DRAFT -->
    <div class="tw" style="padding:15px 17px;margin-bottom:16px">
      <div class="md-eyebrow">3. Draft message <span class="md-period">· copy into your own email client</span></div>
      <textarea class="inp" style="width:100%;min-height:180px;font-family:inherit;resize:vertical" v-model="currentCampaign.message" :disabled="isReadOnly"></textarea>
    </div>

    <div style="display:flex;gap:8px;align-items:center">
      <button class="btn" :disabled="isReadOnly || !currentCampaign.name.trim() || !includedCount || saving" @click="saveDraft">
        {{ saving ? 'Saving…' : 'Save Draft' }}
      </button>
      <button v-if="currentCampaign.id && !isReadOnly" class="btn btn-g" :disabled="marking" @click="markSent">
        {{ marking ? 'Marking…' : '✓ Mark as Sent' }}
      </button>
      <span v-if="saveMessage" class="sub" style="color:var(--green)">{{ saveMessage }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, type Customer, type CustomerContactResolution, type Campaign } from '@/api/client'

const route = useRoute()

const customers = ref<Customer[]>([])
const included = ref<Record<number, boolean>>({})
const search = ref('')
const filterTier = ref('')
// Default ON — a Jira contact resolve only makes sense for real VMS
// customers (Email-only/CompassAir-only/no-product-tag rows have no
// reason to be in a VMS maintenance/comms segment). Matches the same
// convention and product-tag check already used in CustomersView.vue.
const vmsOnly = ref(true)
function isVms(c: Customer) {
  return (c.product ?? '').toLowerCase().includes('vms')
}

const campaigns = ref<Campaign[]>([])
const currentCampaign = ref<{ id: number | null; name: string; message: string; status: 'Draft' | 'Sent' | null; incident_id: number | null }>({
  id: null, name: '', message: DEFAULT_DRAFT(), status: null, incident_id: null,
})
const sourceIncidentTitle = ref('')
const isReadOnly = computed(() => currentCampaign.value.status === 'Sent')
const saving = ref(false)
const marking = ref(false)
const saveMessage = ref('')

const resolving = ref(false)
const resolutions = ref<CustomerContactResolution[]>([])
const expanded = ref<number | null>(null)
const copied = ref(false)
const copyFailed = ref(false)

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return customers.value.filter(c =>
    (!q || c.name.toLowerCase().includes(q)) &&
    (!filterTier.value || c.tier === filterTier.value) &&
    (!vmsOnly.value || isVms(c))
  )
})
const includedCount = computed(() => customers.value.filter(c => included.value[c.id]).length)

function includeAll() {
  for (const c of filtered.value) included.value[c.id] = true
}
function excludeAll() {
  for (const c of filtered.value) included.value[c.id] = false
}

function newCampaign() {
  currentCampaign.value = { id: null, name: '', message: DEFAULT_DRAFT(), status: null, incident_id: null }
  sourceIncidentTitle.value = ''
  for (const c of customers.value) included.value[c.id] = isVms(c)
  resolutions.value = []
  saveMessage.value = ''
}

async function openCampaign(id: number) {
  const res = await api.campaigns.get(id)
  const d = res.data
  currentCampaign.value = { id: d.id, name: d.name, message: d.message, status: d.status, incident_id: d.incident_id }
  sourceIncidentTitle.value = ''
  const includedIds = new Set(d.customers.map(c => c.id))
  for (const c of customers.value) included.value[c.id] = includedIds.has(c.id)
  resolutions.value = []
  saveMessage.value = ''
}

// Arrived via an incident's "Notify affected customers" link — pre-fill
// the segment to exactly that incident's remediation-tracked customers
// (not the default VMS-only set) and a draft mentioning the incident.
async function startFromIncident(incidentId: number) {
  const res = await api.incidents.get(incidentId)
  const inc = res.data
  sourceIncidentTitle.value = inc.title
  const affectedIds = new Set(inc.remediations.map(r => r.customer_id))
  for (const c of customers.value) included.value[c.id] = affectedIds.has(c.id)
  currentCampaign.value = {
    id: null, status: null, incident_id: incidentId,
    name: `${inc.title} — affected customer notice`,
    message: `Subject: ${inc.title}\n\nDear customer,\n\n${inc.impact || inc.detail}\n\n${inc.affected_below_version ? `This affects installations below version ${inc.affected_below_version}.` : ''}\n\nThank you for your patience.\n`,
  }
  resolutions.value = []
  saveMessage.value = ''
}

// Arrived via Troubleshoot's "Notify affected tenants" link — pre-fill the
// segment to that bug's real exposed customers (reported + silently
// exposed) and a draft mentioning the real bug/fix version. No
// incident_id-style back-reference exists for this path (no
// Campaign.vms_ref column) — only worth adding later if a "comms sent for
// this bug" lookup ever turns out to matter, per the plan's own scoping.
async function startFromBugExposure(vmsRef: string) {
  const res = await api.troubleshoot.investigate(vmsRef)
  const bug = res.data.bug
  if (!bug) return
  const affectedIds = new Set([
    ...bug.reported_customers.map(c => c.id),
    ...bug.silently_exposed_customers.map(c => c.id),
  ])
  for (const c of customers.value) included.value[c.id] = affectedIds.has(c.id)
  currentCampaign.value = {
    id: null, status: null, incident_id: null,
    name: `${bug.vms_ref} — affected customer notice`,
    message: `Subject: ${bug.vms_ref} fix${bug.fix_version ? ' (' + bug.fix_version + ')' : ''}\n\nDear customer,\n\nWe wanted to let you know about a fix for an issue affecting your Dataloy VMS installation${bug.matched_release ? ` — released in ${bug.matched_release}` : ' — the fix has shipped and will be included in an upcoming formal release'}.\n\nPlease reach out if you'd like help scheduling the upgrade.\n\nThank you.\n`,
  }
  resolutions.value = []
  saveMessage.value = ''
}

async function loadCampaignHistory() {
  const res = await api.campaigns.list()
  campaigns.value = res.data
}

async function saveDraft() {
  const ids = customers.value.filter(c => included.value[c.id]).map(c => c.id)
  saving.value = true
  saveMessage.value = ''
  try {
    if (currentCampaign.value.id) {
      await api.campaigns.patch(currentCampaign.value.id, {
        name: currentCampaign.value.name, message: currentCampaign.value.message, customer_ids: ids,
      })
    } else {
      const res = await api.campaigns.create({
        name: currentCampaign.value.name, message: currentCampaign.value.message, customer_ids: ids,
        incident_id: currentCampaign.value.incident_id ?? undefined,
      })
      currentCampaign.value.id = res.data.id
      currentCampaign.value.status = res.data.status
    }
    await loadCampaignHistory()
    saveMessage.value = '✓ Saved'
    setTimeout(() => { saveMessage.value = '' }, 2500)
  } finally {
    saving.value = false
  }
}

async function markSent() {
  if (!currentCampaign.value.id) return
  if (!confirm('Mark this campaign as Sent? The name, segment, and message become read-only afterward.')) return
  marking.value = true
  try {
    const res = await api.campaigns.patch(currentCampaign.value.id, { status: 'Sent' })
    currentCampaign.value.status = res.data.status
    await loadCampaignHistory()
  } finally {
    marking.value = false
  }
}

async function resolveContacts() {
  const ids = customers.value.filter(c => included.value[c.id]).map(c => c.id)
  if (!ids.length) return
  resolving.value = true
  copied.value = false
  try {
    const res = await api.customers.resolveContacts(ids)
    resolutions.value = res.data
  } finally {
    resolving.value = false
  }
}

function toggleExpanded(id: number) {
  expanded.value = expanded.value === id ? null : id
}

// The actual outbound list — one designated main contact per customer when
// one exists, falling back to every real email only for the (hopefully
// rare, flagged separately below) customers with 2+ contacts and no
// designation yet. This is what fixed the original complaint: a customer
// with 48 stored contacts sends to exactly 1 email once designated, not 48.
function outboundEmails(r: CustomerContactResolution): string[] {
  if (r.primary_contact_email) return [r.primary_contact_email]
  return r.contacts.map(c => c.email).filter((e): e is string => !!e)
}
const totalEmails = computed(() =>
  resolutions.value.reduce((sum, r) => sum + outboundEmails(r).length, 0)
)
const undesignatedCount = computed(() =>
  resolutions.value.filter(r => r.email_count > 1 && !r.primary_contact_email).length
)

async function copyAllEmails() {
  const emails = resolutions.value.flatMap(outboundEmails)
  copyFailed.value = false
  try {
    await navigator.clipboard.writeText(emails.join(', '))
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // Clipboard access can be denied by the browser (permissions, focus,
    // insecure context) — fail visibly rather than silently doing nothing.
    copyFailed.value = true
    setTimeout(() => { copyFailed.value = false }, 3000)
  }
}

const csvHref = computed(() => {
  const rows = [['customer', 'contact_name', 'email', 'designated_main_contact']]
  for (const r of resolutions.value) {
    for (const email of outboundEmails(r)) {
      const contact = r.contacts.find(c => c.email === email)
      rows.push([r.customer_name, contact?.name ?? '', email, r.primary_contact_email ? 'yes' : 'no — sent to all'])
    }
  }
  const csv = rows.map(row => row.map(v => `"${v.replace(/"/g, '""')}"`).join(',')).join('\r\n')
  return 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv)
})

function DEFAULT_DRAFT() {
  return `Subject: Scheduled Maintenance Window — [DATE]

Dear customer,

We're writing to let you know about a scheduled maintenance window on [DATE/TIME], during which [SYSTEM/SERVICE] may be temporarily unavailable.

What to expect:
- [details]

We don't expect this to affect [X], and we'll confirm once the window is complete.

Thank you for your patience.
`
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
function tierClass(tier?: string | null) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}

onMounted(async () => {
  const res = await api.customers.list()
  customers.value = res.data.filter(c => c.status !== 'Cancelled')
  for (const c of customers.value) included.value[c.id] = isVms(c)
  await loadCampaignHistory()

  const campaignParam = route.query.campaign
  if (campaignParam) {
    const id = Number(campaignParam)
    if (!Number.isNaN(id)) await openCampaign(id)
    return
  }
  const incidentParam = route.query.incident
  if (incidentParam) {
    const id = Number(incidentParam)
    if (!Number.isNaN(id)) await startFromIncident(id)
    return
  }
  const vmsRefParam = route.query.vms_ref
  if (vmsRefParam && typeof vmsRefParam === 'string') {
    await startFromBugExposure(vmsRefParam)
  }
})
</script>

<style scoped>
.nc-grid { max-height: 360px; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.nc-row { display: flex; align-items: center; gap: 9px; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 11px; }
.nc-row:hover { background: var(--surface2); }
.nc-row.excluded { opacity: .4; }
.nc-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.nc-result-row { border-top: 1px dashed var(--border2); }
.nc-result-row:first-of-type { border-top: none; }
.nc-result-head {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px 2px;
  background: none; border: none; cursor: pointer; font: inherit; text-align: left;
}
.nc-caret { font-size: 9px; color: var(--text3); width: 10px; flex-shrink: 0; }
.nc-contacts { margin: 0 0 8px 19px; padding: 6px 9px; background: var(--surface2); border-radius: 6px; display: flex; flex-direction: column; gap: 4px; }
.nc-contact-row { display: flex; gap: 12px; font-size: 10.5px; color: var(--text2); }
.cc-hist-row { cursor: pointer; transition: background .15s; }
.cc-hist-row:hover { background: var(--surface2); }
.cc-hist-row.active { background: var(--surface2); box-shadow: inset 2px 0 0 var(--accent); }
</style>
