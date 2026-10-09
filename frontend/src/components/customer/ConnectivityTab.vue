<template>
  <!-- Product & connectivity profile -->
  <div class="tw cp-card">
    <div class="md-eyebrow">Product & connectivity profile</div>
    <div class="cp-chips">
      <span v-for="p in profile" :key="p.label" class="cp-chip" :class="p.tone"><span>{{ p.label }}</span><b>{{ p.value }}</b></span>
    </div>
  </div>

  <div v-if="releaseSpread" class="info-bar cp-gap">{{ releaseSpread }}</div>

  <!-- Instances -->
  <div class="cp-instances">
    <div v-for="slot in slots" :key="slot.env" class="tw cp-inst" :class="{ empty: !slot.t }">
      <div class="cp-inst-head">
        <span class="cp-env" :class="slot.env.toLowerCase()">{{ slot.env }}</span>
        <a v-if="slot.t && !editing[slot.env]" class="cp-host" :href="`https://${host(slot.t.subdomain)}`" target="_blank">{{ host(slot.t.subdomain) }} ↗</a>
        <button v-if="slot.t && !editing[slot.env]" class="cp-link cp-push" @click="startEdit(slot.env, slot.t.subdomain)">edit</button>
      </div>

      <!-- Add / change the subdomain -->
      <div v-if="!slot.t || editing[slot.env]" class="cp-sub-edit">
        <div v-if="!slot.t && !editing[slot.env]" class="cp-muted">No {{ slot.env }} environment on record.</div>
        <form v-if="editing[slot.env] || !slot.t" class="cp-inline-form" @submit.prevent="saveSubdomain(slot.env)">
          <input class="inp" v-model="subInputs[slot.env]" :placeholder="slot.env === 'PROD' ? 'e.g. sfl, gb-prod, or full URL' : `e.g. ${slot.env.toLowerCase() === 'test' ? 'gb-test' : 'gb-dev'}, or full URL`">
          <button class="btn btn-sm" :disabled="!subInputs[slot.env]?.trim() || busy === slot.env">{{ busy === slot.env ? 'Saving…' : slot.t ? 'Save & check' : `Add ${slot.env}` }}</button>
          <button v-if="editing[slot.env]" type="button" class="btn btn-g btn-sm" @click="editing[slot.env] = false">Cancel</button>
        </form>
        <div class="cp-muted cp-hint">A bare code (e.g. "sfl") becomes sfl.dataloy.com; paste the full URL for tenants on their own domain.</div>
      </div>

      <template v-if="slot.t">
        <div class="cp-inst-status">
          <span class="cp-dot" :class="state(slot.t)"></span>
          <span v-if="live[slot.env]">{{ live[slot.env]!.ok ? `Up · ${live[slot.env]!.latency_ms}ms just now` : `Not reachable · ${live[slot.env]!.error}` }}</span>
          <span v-else-if="slot.t.last_sync_error">Last check failed · {{ slot.t.last_sync_error }}</span>
          <span v-else-if="slot.t.last_synced_at">Reachable · last checked {{ fmtDateTime(slot.t.last_synced_at) }}</span>
          <span v-else class="cp-muted">Never checked</span>
        </div>

        <div v-if="slot.t.is_jvms_mode" class="cp-warnbox">
          ⚠ JVM-mode tenant — its /info isn't authoritative; the release below can be stale (one JVM tenant reported 6.38.3 while really on 8.30.1). Prefer DevOps' value.
        </div>

        <div class="cp-fact"><span>Release</span><b class="cp-mono" :class="versionTone(release(slot.t))">{{ release(slot.t) || '—' }}</b></div>
        <div v-if="wildflyGuess(release(slot.t))" class="cp-fact"><span>WildFly</span><b>{{ wildflyGuess(release(slot.t)) }}</b></div>
        <div class="cp-fact">
          <span>Reports itself as</span>
          <b :class="{ warn: mismatch(slot.t) }">{{ reported(slot.t) || '—' }}<template v-if="mismatch(slot.t)"> · expected {{ slot.env.toLowerCase() }}</template></b>
        </div>
        <div class="cp-fact">
          <span>SSL certificate</span>
          <b v-if="slot.t.cert_check_error" class="bad">{{ slot.t.cert_check_error }}</b>
          <b v-else-if="slot.t.cert_expires_at" :class="certTone(daysUntil(slot.t.cert_expires_at))">
            {{ fmtDate(slot.t.cert_expires_at) }} · {{ daysUntil(slot.t.cert_expires_at)! < 0 ? 'expired' : `${daysUntil(slot.t.cert_expires_at)}d left` }}
            <span v-if="slot.t.cert_issuer" class="cp-muted">· {{ slot.t.cert_issuer }}</span>
          </b>
          <b v-else class="cp-muted">not checked</b>
        </div>
        <div class="cp-fact"><span>aws-util</span><b>{{ awsUtil(slot.t) }}</b></div>
        <div class="cp-flags">
          <span v-for="f in flags(slot.t)" :key="f.label" class="cp-flag" :class="{ on: f.on }">{{ f.label }}</span>
        </div>
        <div class="cp-inst-actions">
          <button class="btn btn-sm" :disabled="busy === slot.env" @click="check(slot.t)">{{ busy === slot.env ? 'Checking…' : 'Check now' }}</button>
          <RouterLink v-if="runnerEnv(slot.t)" class="btn btn-g btn-sm" to="/operations?tab=runner">Upgrade…</RouterLink>
        </div>
      </template>
    </div>
    <button v-if="!slots.some(s => s.env === 'DEV')" class="cp-add-env" @click="showDev = true">+ Add DEV environment</button>
  </div>

  <div class="cp-grid cp-gap">
    <!-- Access -->
    <div class="tw cp-card">
      <div class="md-eyebrow">Login instructions</div>
      <textarea class="inp" rows="4" v-model="loginNotes" placeholder="e.g. don't use the default user — create one per support engineer"></textarea>
      <div class="cp-row-end">
        <span v-if="loginSaved" class="cp-muted">Saved</span>
        <button class="btn btn-sm" :disabled="savingLogin || loginNotes === (customer.tenant_login_notes ?? '')" @click="saveLogin">{{ savingLogin ? 'Saving…' : 'Save' }}</button>
      </div>
    </div>

    <!-- API access -->
    <div class="tw cp-card">
      <div class="md-eyebrow">VMS API access <span class="cp-muted">· machine-to-machine</span></div>
      <div class="cp-muted cp-gap-sm">
        <template v-if="!credential">Loading…</template>
        <template v-else-if="credential.has_credential">✓ Configured — {{ credential.label }} ({{ credential.client_id }})</template>
        <template v-else>No API credential for this customer yet.</template>
      </div>
      <form class="cp-inline-form" @submit.prevent="saveCredential">
        <input class="inp" v-model="clientId" placeholder="Client ID">
        <input class="inp" v-model="clientSecret" type="password" placeholder="Client secret">
        <button class="btn btn-g btn-sm" :disabled="!clientId.trim() || !clientSecret.trim() || savingCred">{{ savingCred ? 'Saving…' : credential?.has_credential ? 'Replace' : 'Save' }}</button>
      </form>

      <div class="md-eyebrow cp-gap">Live VMS data</div>
      <form class="cp-inline-form" @submit.prevent="fetchEntity">
        <input class="inp" v-model="entity" placeholder="Entity, e.g. Voyage">
        <input class="inp" v-model="entityKey" placeholder="Key">
        <label class="cp-check cp-muted"><input type="checkbox" v-model="useDemo"> demo credential</label>
        <button class="btn btn-sm" :disabled="!entity.trim() || !entityKey.trim() || fetching">{{ fetching ? 'Fetching…' : 'Fetch' }}</button>
      </form>
      <div v-if="entityResult?.message" class="cp-warnbox">{{ entityResult.message }}</div>
      <pre v-else-if="entityResult?.data" class="cp-json">{{ JSON.stringify(entityResult.data, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
// What do they run, can I reach it, and how do I get in? Everything about
// the customer's instances lives here: the old panel's "Technical" tab
// (subdomains, /info sync, flags, SSL, JVM warnings, login instructions,
// API credential + live data explorer) plus SSO/integrations/infra.
import { ref, reactive, computed, watch } from 'vue'
import {
  api, type Customer, type TenantInfo, type LiveInfo, type RunnerTargets, type VmsCredentialStatus, type VmsEntityResult,
} from '@/api/client'
import { useToast } from '@/composables/useToast'
import { fmtDate, fmtDateTime, host, versionTone, wildflyGuess, daysUntil, certTone } from './profileUtils'

const props = defineProps<{ customer: Customer }>()
const emit = defineEmits<{ 'update:customer': [Customer] }>()

const tenants = ref<TenantInfo[]>([])
const live = ref<Record<string, LiveInfo | undefined>>({})
const runnerTargets = ref<RunnerTargets | null>(null)
const busy = ref('')
const editing = reactive<Record<string, boolean>>({})
const subInputs = reactive<Record<string, string>>({ PROD: '', TEST: '', DEV: '' })
const showDev = ref(false)

// ── Profile ──
const profile = computed(() => {
  const c = props.customer
  const wf = c.wildfly8 ? '8 — active, check after migration' : wildflyGuess(c.prod_version) ?? 'Unknown'
  return [
    { label: 'Infra', value: c.infra, tone: c.infra === 'Old' ? 'warn' : '' },
    { label: 'Client', value: c.jvm_client ? 'JVM desktop' : 'Web', tone: c.jvm_client ? 'warn' : '' },
    { label: 'SSO', value: c.sso || 'None', tone: '' },
    { label: 'Integrations', value: c.integrations || 'None', tone: c.integrations && c.integrations !== 'None' ? 'warn' : '' },
    { label: 'API customer', value: c.api_customer ? 'Yes' : 'No', tone: c.api_customer ? 'ok' : '' },
    { label: 'IP whitelist / FW', value: c.ip_fw ? 'Yes' : 'No', tone: c.ip_fw ? 'warn' : '' },
    { label: 'WildFly', value: wf, tone: c.wildfly8 ? 'warn' : '' },
  ]
})

// ── Instances: PROD and TEST always have a slot; DEV when it exists or is being added ──
const slots = computed(() => {
  const by = (env: string) => tenants.value.find(t => t.environment === env) ?? null
  const out = [{ env: 'PROD', t: by('PROD') }, { env: 'TEST', t: by('TEST') }]
  if (by('DEV') || showDev.value) out.push({ env: 'DEV', t: by('DEV') })
  return out
})
function release(t: TenantInfo) { return live.value[t.environment]?.release || t.release }
function reported(t: TenantInfo) { return live.value[t.environment]?.environment || t.reported_environment }
function mismatch(t: TenantInfo) {
  const r = reported(t)?.toLowerCase()
  if (!r) return false
  const expected = { PROD: ['prod', 'production'], TEST: ['test'], DEV: ['dev', 'development'] }[t.environment] ?? []
  return !expected.includes(r)
}
function state(t: TenantInfo) {
  const l = live.value[t.environment]
  if (l) return l.ok ? 'ok' : 'bad'
  if (t.last_sync_error) return 'bad'
  return t.last_synced_at ? 'ok' : ''
}
function flags(t: TenantInfo) {
  return [
    { label: 'Auth0 / SSO', on: !!t.is_auth0_installation },
    { label: 'Azure auth', on: !!t.is_azure_installation },
    { label: 'Pure web', on: !!t.is_pure_web },
    { label: 'JVMS mode', on: !!t.is_jvms_mode },
  ]
}
const releaseSpread = computed(() => {
  const withRel = tenants.value.filter(t => t.release)
  const distinct = new Set(withRel.map(t => t.release!.split('-')[0]))
  if (distinct.size < 2) return ''
  return 'Releases differ across environments — ' + withRel.map(t => `${t.environment} ${t.release}`).join(' · ')
})
function runnerEnv(t: TenantInfo) {
  return runnerTargets.value?.customers.find(c => c.customer_id === props.customer.id)
    ?.instances.find(i => i.environment === t.environment && i.subdomain === t.subdomain)?.runner_env ?? null
}
function awsUtil(t: TenantInfo) {
  if (!runnerTargets.value) return '…'
  if (!runnerTargets.value.runner_online) return 'unknown (runner offline)'
  return runnerEnv(t) ?? 'not managed in aws-util'
}

function replaceTenant(row: TenantInfo) {
  const i = tenants.value.findIndex(t => t.environment === row.environment)
  if (i >= 0) tenants.value.splice(i, 1, row)
  else tenants.value.push(row)
  if (row.matched_incidents?.length) {
    useToast().push(`Matched ${row.matched_incidents.length} open incident(s): ${row.matched_incidents.map(m => m.incident_title).join(', ')}`, 'info', 8000)
  }
}
async function check(t: TenantInfo) {
  busy.value = t.environment
  try {
    const [synced, probe] = await Promise.all([
      api.customers.syncTenantInfo(props.customer.id, t.environment).catch(() => null),
      api.automation.live(t.subdomain).catch(() => null),
    ])
    if (synced) replaceTenant(synced.data)
    if (probe) live.value = { ...live.value, [t.environment]: probe.data }
  } finally {
    busy.value = ''
  }
}
function startEdit(env: string, current: string) {
  subInputs[env] = current
  editing[env] = true
}
async function saveSubdomain(env: string) {
  const sub = subInputs[env]?.trim()
  if (!sub) return
  busy.value = env
  try {
    await api.customers.setTenantSubdomain(props.customer.id, env, sub)
    replaceTenant((await api.customers.syncTenantInfo(props.customer.id, env)).data)
    editing[env] = false
    live.value = { ...live.value, [env]: undefined }
  } finally {
    busy.value = ''
  }
}

// ── Access ──
const loginNotes = ref('')
const savingLogin = ref(false)
const loginSaved = ref(false)
async function saveLogin() {
  savingLogin.value = true
  try {
    emit('update:customer', (await api.customers.patch(props.customer.id, { tenant_login_notes: loginNotes.value })).data)
    loginSaved.value = true
  } finally {
    savingLogin.value = false
  }
}

// ── API access ──
const credential = ref<VmsCredentialStatus | null>(null)
const clientId = ref('')
const clientSecret = ref('')
const savingCred = ref(false)
const entity = ref('')
const entityKey = ref('')
const useDemo = ref(false)
const fetching = ref(false)
const entityResult = ref<VmsEntityResult | null>(null)
async function saveCredential() {
  savingCred.value = true
  try {
    credential.value = (await api.customers.setVmsCredential(props.customer.id, { client_id: clientId.value.trim(), client_secret: clientSecret.value.trim() })).data
    clientId.value = ''
    clientSecret.value = ''
  } finally {
    savingCred.value = false
  }
}
async function fetchEntity() {
  fetching.value = true
  entityResult.value = null
  try {
    entityResult.value = (await api.customers.getVmsEntity(props.customer.id, entity.value.trim(), entityKey.value.trim(), useDemo.value)).data
  } catch (e: any) {
    entityResult.value = { data: null, message: e?.response?.data?.detail ?? 'Request failed' }
  } finally {
    fetching.value = false
  }
}

async function load() {
  const id = props.customer.id
  live.value = {}
  loginNotes.value = props.customer.tenant_login_notes ?? ''
  loginSaved.value = false
  const [t, cred] = await Promise.all([api.customers.tenantInfo(id), api.customers.getVmsCredential(id)])
  tenants.value = t.data
  credential.value = cred.data
  api.automation.targets().then(r => { runnerTargets.value = r.data }).catch(() => {})
}
watch(() => props.customer.id, load, { immediate: true })
</script>
