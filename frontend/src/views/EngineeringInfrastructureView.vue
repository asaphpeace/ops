<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Infrastructure</h2>
        <p>Compute and database inventory from the latest AWS export, mapped to the customers that sit on it — where is what, by account, region and tenant.</p>
      </div>
    </div>

    <div class="ei-accounts">
      <div v-for="a in accounts" :key="a.name" class="tw ei-account-card">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-weight:700;font-size:14px">{{ a.name }}</span>
          <span v-if="a.region" class="sub" style="font-size:10.5px;margin-left:auto">{{ a.region }}</span>
        </div>
        <div class="sub" style="font-size:11.5px;margin-top:5px">{{ a.summary }}</div>
        <div style="font-size:10.5px;margin-top:7px" :style="{ color: a.state_color }">{{ a.state }}</div>
        <div v-if="a.needs_import" class="ei-import-cta">
          <div class="sub" style="font-size:11px">{{ a.import_copy }}</div>
          <div class="ei-cmd">{{ a.import_cmd }}</div>
          <div style="display:flex;gap:6px;margin-top:7px">
            <button class="btn btn-g btn-sm" @click="jumpToImport(a.name.startsWith('Old') ? 'Old' : 'New')">Paste export</button>
            <button class="btn btn-g btn-sm" @click="copyCmd(a.import_cmd)">{{ copiedCmd === a.import_cmd ? 'Copied ✓' : 'Copy command' }}</button>
          </div>
        </div>
      </div>
    </div>

    <div ref="importSectionRef" class="tw" style="padding:15px 17px;margin-bottom:16px">
      <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:10px">Import Export</div>
      <div style="display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap">
        <select class="sel" v-model="importEnv">
          <option value="Old">Old AWS</option>
          <option value="New">New AWS</option>
        </select>
        <input class="inp" style="width:160px" placeholder="Region, e.g. eu-west-1" v-model="importRegion">
        <button class="btn btn-g btn-sm" :disabled="importing" @click="runImport">{{ importing ? 'Importing…' : 'Import' }}</button>
      </div>
      <div class="ei-paste-grid">
        <div>
          <div class="ei-paste-label">ec2.json</div>
          <textarea class="inp ei-textarea" v-model="ec2Text" placeholder="Paste aws ec2 describe-instances output…"></textarea>
        </div>
        <div>
          <div class="ei-paste-label">rds.json</div>
          <textarea class="inp ei-textarea" v-model="rdsText" placeholder="Paste aws rds describe-db-instances output…"></textarea>
        </div>
        <div>
          <div class="ei-paste-label">cloudwatch.json</div>
          <textarea class="inp ei-textarea" v-model="cloudwatchText" placeholder="Paste the CPU snapshot array…"></textarea>
        </div>
      </div>
      <div v-if="importError" class="sub" style="color:var(--red);font-size:10.5px;margin-top:8px">{{ importError }}</div>
      <div v-if="importResult" class="sub" style="color:var(--green);font-size:10.5px;margin-top:8px">
        Imported — {{ importResult.created }} created, {{ importResult.updated }} updated, {{ importResult.suggested }} auto-suggested a customer match.
      </div>
    </div>

    <div class="tw" style="padding:15px 17px;margin-bottom:16px" v-if="unmatched.length">
      <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:10px">
        Unmatched Resources <span style="text-transform:none;font-weight:600;color:var(--text2)">· {{ unmatched.length }} need a real customer confirmed</span>
      </div>
      <div v-for="r in unmatched" :key="r.id" class="ei-row">
        <span class="ei-res">{{ r.resource_type }} · {{ r.name || r.resource_id }}</span>
        <span :class="['env-badge', r.aws_environment === 'Old' ? 'et' : 'ep']">{{ r.aws_environment }} AWS</span>
        <span v-if="r.suggested_customer_id" class="sub" style="font-size:10px">suggested: {{ customerName(r.suggested_customer_id) }}</span>
        <select class="sel ei-sel" v-model.number="pendingCustomer[r.id]">
          <option :value="null">— pick customer —</option>
          <option v-for="c in customers" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <select class="sel ei-sel-sm" v-model="pendingEnv[r.id]">
          <option value="PROD">PROD</option>
          <option value="TEST">TEST</option>
          <option value="DEV">DEV</option>
        </select>
        <button
          v-if="r.suggested_customer_id"
          class="btn btn-g btn-sm"
          @click="confirm(r, r.suggested_customer_id!)"
        >✓ Confirm suggestion</button>
        <button class="btn btn-g btn-sm" :disabled="!pendingCustomer[r.id]" @click="confirm(r, pendingCustomer[r.id]!)">Confirm</button>
        <button class="btn btn-g btn-sm" @click="markInternal(r)">Mark internal</button>
      </div>
    </div>

    <div class="ei-body">
      <div class="tw" style="padding:0;overflow:hidden">
        <div style="display:flex;align-items:baseline;gap:10px;padding:12px 14px 8px">
          <span class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800">Inventory</span>
          <span class="sub" style="font-size:11px">{{ filteredResources.length }}</span>
          <input class="inp" v-model="invQuery" placeholder="instance id, customer, subdomain…" style="margin-left:auto;width:220px;font-size:11.5px">
        </div>
        <div class="ei-inv-head">
          <div>Instance</div><div>Customer</div><div>Type</div><div>Class</div><div>Stack</div><div style="text-align:right">CPU</div>
        </div>
        <div v-for="r in filteredResources" :key="r.id" class="ei-inv-row" @click="r.customer_id && goToCustomer(r.customer_id, r.customer_environment ?? undefined)">
          <div class="ei-mono">{{ r.resource_id }}</div>
          <div class="ei-ellipsis">{{ r.customer_name || '—' }}</div>
          <div class="sub" style="font-size:10.5px">{{ r.resource_type }}</div>
          <div class="sub" style="font-size:10.5px">{{ r.instance_type || '—' }}</div>
          <div class="sub" style="font-size:10.5px">{{ r.engine ? `${r.engine} ${r.engine_version || ''}` : '—' }}</div>
          <div style="text-align:right" class="sub">—</div>
        </div>
        <div v-if="!filteredResources.length" class="sub" style="text-align:center;padding:20px;font-size:11px">
          {{ resources.length ? 'No matches.' : 'No AWS resources imported yet.' }}
        </div>
      </div>

      <div style="display:flex;flex-direction:column;gap:12px">
        <div class="tw" style="padding:14px">
          <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);font-weight:800;margin-bottom:10px">Hosting Model</div>
          <div v-for="h in hosting" :key="h.label" style="margin-bottom:10px">
            <div style="display:flex;justify-content:space-between;font-size:11.5px">
              <span>{{ h.label }}</span><span class="sub">{{ h.count }}</span>
            </div>
            <div class="ei-bar-track"><div class="ei-bar-fill" :style="{ width: h.share, background: h.color }"></div></div>
            <div class="sub" style="font-size:10px;margin-top:3px">{{ h.note }}</div>
          </div>
          <div v-if="!hosting.length" class="sub" style="font-size:10.5px">No confirmed AWS resources yet.</div>
        </div>
        <div class="tw" style="padding:14px">
          <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);font-weight:800;margin-bottom:8px">Dependency Lifecycle</div>
          <div v-for="d in dependencyLifecycle" :key="d.name" class="ei-dep-row">
            <span style="font-size:11.5px;flex:1">{{ d.name }}</span>
            <span class="sub" style="font-size:10.5px">{{ d.envs }}</span>
            <span style="font-size:10.5px" :style="{ color: d.color }">{{ d.state }}</span>
          </div>
          <div v-if="!dependencyLifecycle.length" class="sub" style="font-size:10.5px">No confirmed RDS resources yet.</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type AwsResource, type Customer, type InfraAccountCard, type HostingModelRow, type DependencyLifecycleRow } from '@/api/client'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'

const { openEngineeringCustomer: goToCustomer } = useEngineeringDrill()

const importEnv = ref<'Old' | 'New'>('New')
const importRegion = ref('')
const ec2Text = ref('')
const rdsText = ref('')
const cloudwatchText = ref('')
const importing = ref(false)
const importError = ref<string | null>(null)
const importResult = ref<{ created: number; updated: number; suggested: number } | null>(null)
const importSectionRef = ref<HTMLElement | null>(null)
const copiedCmd = ref<string | null>(null)

const resources = ref<AwsResource[]>([])
const customers = ref<Customer[]>([])
const pendingCustomer = ref<Record<number, number | null>>({})
const pendingEnv = ref<Record<number, string>>({})
const invQuery = ref('')

const accounts = ref<InfraAccountCard[]>([])
const hosting = ref<HostingModelRow[]>([])
const dependencyLifecycle = ref<DependencyLifecycleRow[]>([])

const unmatched = computed(() => resources.value.filter(r => r.match_status === 'unmatched'))

const filteredResources = computed(() => {
  const q = invQuery.value.trim().toLowerCase()
  if (!q) return resources.value
  return resources.value.filter(r =>
    r.resource_id.toLowerCase().includes(q) ||
    (r.name || '').toLowerCase().includes(q) ||
    (r.customer_name || '').toLowerCase().includes(q)
  )
})

function customerName(id: number): string {
  return customers.value.find(c => c.id === id)?.name || `#${id}`
}

function jumpToImport(env: 'Old' | 'New') {
  importEnv.value = env
  importSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function copyCmd(cmd: string | null) {
  if (!cmd) return
  try {
    await navigator.clipboard.writeText(cmd)
    copiedCmd.value = cmd
    setTimeout(() => { if (copiedCmd.value === cmd) copiedCmd.value = null }, 2000)
  } catch { /* clipboard unavailable — silently ignore */ }
}

function parseOrNull(text: string, label: string): unknown | null {
  if (!text.trim()) return null
  try {
    return JSON.parse(text)
  } catch {
    importError.value = `${label} isn't valid JSON — check for a stray comma or unclosed bracket.`
    return undefined
  }
}

async function runImport() {
  importError.value = null
  importResult.value = null
  const ec2 = parseOrNull(ec2Text.value, 'ec2.json')
  if (ec2 === undefined) return
  const rds = parseOrNull(rdsText.value, 'rds.json')
  if (rds === undefined) return
  const cloudwatch = parseOrNull(cloudwatchText.value, 'cloudwatch.json')
  if (cloudwatch === undefined) return

  importing.value = true
  try {
    const res = await api.engineering.importAws({
      aws_environment: importEnv.value,
      region: importRegion.value || undefined,
      ec2: ec2 ?? undefined,
      rds: rds ?? undefined,
      cloudwatch: (cloudwatch as unknown[]) ?? undefined,
    })
    importResult.value = res.data
    await loadAll()
  } catch (e: any) {
    importError.value = e?.response?.data?.detail || 'Import failed.'
  } finally {
    importing.value = false
  }
}

async function loadResources() {
  const res = await api.engineering.resources()
  resources.value = res.data
  for (const r of res.data) {
    if (!(r.id in pendingEnv.value)) pendingEnv.value[r.id] = 'PROD'
    if (!(r.id in pendingCustomer.value)) pendingCustomer.value[r.id] = null
  }
}

async function loadInfraSummary() {
  const res = await api.engineering.infrastructure()
  accounts.value = res.data.accounts
  hosting.value = res.data.hosting
  dependencyLifecycle.value = res.data.dependency_lifecycle
}

async function loadAll() {
  await Promise.all([loadResources(), loadInfraSummary()])
}

async function confirm(r: AwsResource, customerId: number) {
  await api.engineering.confirmMatch(r.id, { customer_id: customerId, environment: pendingEnv.value[r.id] || 'PROD' })
  await loadAll()
}

async function markInternal(r: AwsResource) {
  await api.engineering.markInternal(r.id)
  await loadAll()
}

onMounted(async () => {
  const [, custRes] = await Promise.all([loadAll(), api.customers.list()])
  customers.value = custRes.data
})
</script>

<style scoped>
.ei-accounts { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 11px; margin-bottom: 16px; }
.ei-account-card { padding: 14px; }
.ei-import-cta { margin-top: 11px; padding-top: 11px; box-shadow: inset 0 1px 0 var(--border2); }
.ei-cmd { font-family: ui-monospace, monospace; font-size: 10.5px; color: var(--accent); background: var(--surface2); padding: 8px; border-radius: 4px; margin-top: 8px; overflow-x: auto; white-space: pre; }
.ei-code { background: var(--surface2); border-radius: 3px; padding: 1px 5px; font-size: 10px; }
.ei-paste-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.ei-paste-label { font-size: 9px; color: var(--text3); margin-bottom: 4px; text-transform: uppercase; letter-spacing: .04em; }
.ei-textarea { width: 100%; height: 90px; font-family: monospace; font-size: 9.5px; resize: vertical; }
.ei-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px dashed var(--border2); flex-wrap: wrap; font-size: 10.5px; }
.ei-row:last-child { border-bottom: none; }
.ei-res { font-weight: 600; color: var(--text); }
.ei-sel { min-width: 150px; }
.ei-sel-sm { width: 70px; }
.ei-status { font-size: 8px; font-weight: 800; text-transform: uppercase; padding: 2px 6px; border-radius: 3px; }
.ei-status.unmatched { background: var(--amber-dim); color: var(--amber); }
.ei-status.confirmed { background: var(--green-dim); color: var(--green); }
.ei-status.internal { background: var(--surface2); color: var(--text3); }

.ei-body { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 320px); gap: 16px; align-items: start; }
.ei-inv-head { display: grid; grid-template-columns: 1.3fr 1.5fr 1fr 1fr 1.6fr 0.8fr; font-size: 9px; letter-spacing: .06em; text-transform: uppercase; color: var(--text3); padding: 8px 14px; box-shadow: inset 0 -1px 0 var(--border); }
.ei-inv-row { display: grid; grid-template-columns: 1.3fr 1.5fr 1fr 1fr 1.6fr 0.8fr; align-items: center; padding: 8px 14px; font-size: 11.5px; cursor: pointer; box-shadow: inset 0 -1px 0 var(--border2); }
.ei-inv-row:hover { background: var(--surface2); }
.ei-mono { font-family: ui-monospace, monospace; color: var(--text2); font-size: 11px; }
.ei-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ei-bar-track { height: 4px; border-radius: 2px; background: var(--border2); margin-top: 5px; }
.ei-bar-fill { height: 4px; border-radius: 2px; }
.ei-dep-row { display: flex; align-items: baseline; gap: 8px; padding: 5px 0; box-shadow: inset 0 -1px 0 var(--border2); }
</style>
