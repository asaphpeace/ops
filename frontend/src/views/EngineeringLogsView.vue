<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Logs</h2>
        <p>Real AWS log events, imported from a periodic manual export — not a live log platform. No live tail, no query language, no continuous ingest. Search covers whatever's been imported so far ({{ totalImported }} entries on file).</p>
      </div>
    </div>

    <div class="tw" style="padding:15px 17px;margin-bottom:16px">
      <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:10px">Import Export</div>
      <div style="display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap">
        <select class="sel" v-model="importType">
          <option value="application">Application / System</option>
          <option value="rds">RDS / Database</option>
          <option value="cloudtrail">CloudTrail</option>
          <option value="vpc_flow">VPC Flow Logs</option>
        </select>
        <input class="inp" style="width:220px" placeholder="Log group / trail name" v-model="sourceGroup">
        <select class="sel" v-model.number="importResourceId">
          <option :value="null">— not linked to a resource —</option>
          <option v-for="r in resources" :key="r.id" :value="r.id">{{ r.name || r.resource_id }}<template v-if="r.customer_name"> ({{ r.customer_name }})</template></option>
        </select>
        <button class="btn btn-g btn-sm" :disabled="importing" @click="runImport">{{ importing ? 'Importing…' : 'Import' }}</button>
      </div>
      <div class="el-paste-label">
        {{ importType === 'cloudtrail' ? 'aws cloudtrail lookup-events output' : 'aws logs filter-log-events output' }}
      </div>
      <textarea class="inp el-textarea" v-model="entriesText" placeholder="Paste the raw AWS CLI JSON output…"></textarea>
      <div v-if="importError" class="sub" style="color:var(--red);font-size:10.5px;margin-top:8px">{{ importError }}</div>
      <div v-if="importResult" class="sub" style="color:var(--green);font-size:10.5px;margin-top:8px">
        Imported — {{ importResult.created }} new, {{ importResult.skipped }} already on file.
      </div>
    </div>

    <div class="tw" style="padding:15px 17px">
      <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800;margin-bottom:10px">Search</div>
      <div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap">
        <input class="inp" style="flex:1;min-width:200px" placeholder="Search message text…" v-model="q" @keyup.enter="runSearch">
        <select class="sel" v-model="filterType">
          <option value="">All types</option>
          <option value="application">Application</option>
          <option value="rds">RDS</option>
          <option value="cloudtrail">CloudTrail</option>
          <option value="vpc_flow">VPC Flow</option>
        </select>
        <input class="inp" type="datetime-local" v-model="since">
        <input class="inp" type="datetime-local" v-model="until">
        <button class="btn btn-g btn-sm" :disabled="searching" @click="runSearch">{{ searching ? 'Searching…' : 'Search' }}</button>
      </div>

      <div v-if="entries.length" class="el-results">
        <div v-for="e in entries" :key="e.id" class="el-row">
          <span class="sub el-ts">{{ formatTs(e.timestamp) }}</span>
          <span v-if="e.level" :class="['el-level', e.level.toLowerCase()]">{{ e.level }}</span>
          <span class="el-type">{{ e.log_type }}</span>
          <span class="el-msg">{{ e.message }}</span>
          <span v-if="e.customer_name" class="sub el-cust" @click="goToCustomer(e.customer_id!, 'overview')">{{ e.customer_name }}</span>
        </div>
      </div>
      <div v-else class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:20px 0">
        {{ searched ? 'No log entries match.' : 'No search run yet — showing nothing until you search or import.' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, type AwsResource, type LogEntry, type LogImportResult, type LogType } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCustomer: goToCustomer } = useCustomerDrill()

const importType = ref<LogType>('application')
const sourceGroup = ref('')
const importResourceId = ref<number | null>(null)
const entriesText = ref('')
const importing = ref(false)
const importError = ref<string | null>(null)
const importResult = ref<LogImportResult | null>(null)

const resources = ref<AwsResource[]>([])

const q = ref('')
const filterType = ref('')
const since = ref('')
const until = ref('')
const entries = ref<LogEntry[]>([])
const searching = ref(false)
const searched = ref(false)
const totalImported = ref(0)

function formatTs(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

async function runImport() {
  importError.value = null
  importResult.value = null
  if (!sourceGroup.value.trim()) {
    importError.value = 'Log group / trail name is required.'
    return
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(entriesText.value)
  } catch {
    importError.value = "That isn't valid JSON — check for a stray comma or unclosed bracket."
    return
  }

  importing.value = true
  try {
    const res = await api.engineering.importLogs({
      log_type: importType.value,
      source_group: sourceGroup.value.trim(),
      aws_resource_id: importResourceId.value ?? undefined,
      entries: parsed,
    })
    importResult.value = res.data
  } catch (e: any) {
    importError.value = e?.response?.data?.detail || 'Import failed.'
  } finally {
    importing.value = false
  }
}

async function runSearch() {
  searching.value = true
  searched.value = true
  try {
    const res = await api.engineering.searchLogs({
      q: q.value.trim() || undefined,
      log_type: filterType.value || undefined,
      since: since.value ? new Date(since.value).toISOString() : undefined,
      until: until.value ? new Date(until.value).toISOString() : undefined,
    })
    entries.value = res.data.entries
    totalImported.value = res.data.total_imported
  } finally {
    searching.value = false
  }
}

onMounted(async () => {
  const res = await api.engineering.resources()
  resources.value = res.data
  await runSearch()
})
</script>

<style scoped>
.el-paste-label { font-size: 9px; color: var(--text3); margin-bottom: 4px; text-transform: uppercase; letter-spacing: .04em; }
.el-textarea { width: 100%; height: 110px; font-family: monospace; font-size: 9.5px; resize: vertical; }
.el-results { display: flex; flex-direction: column; gap: 2px; max-height: 520px; overflow-y: auto; }
.el-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px dashed var(--border2); font-size: 10.5px; flex-wrap: wrap; }
.el-row:last-child { border-bottom: none; }
.el-ts { font-family: monospace; font-size: 9.5px; white-space: nowrap; }
.el-type { font-size: 8.5px; text-transform: uppercase; color: var(--text3); background: var(--surface2); border-radius: 3px; padding: 1px 5px; }
.el-msg { flex: 1; color: var(--text); word-break: break-word; }
.el-cust { cursor: pointer; font-weight: 600; }
.el-cust:hover { text-decoration: underline; }
.el-level { font-size: 8px; font-weight: 800; padding: 1px 6px; border-radius: 3px; text-transform: uppercase; }
.el-level.error, .el-level.fatal, .el-level.critical { background: var(--red-dim); color: var(--red); }
.el-level.warn, .el-level.warning { background: var(--amber-dim); color: var(--amber); }
.el-level.info { background: var(--surface2); color: var(--text3); }
.el-level.debug { background: var(--surface2); color: var(--text3); }
</style>
