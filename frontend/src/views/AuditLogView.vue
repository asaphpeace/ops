<template>
  <div class="view">
    <div class="sh">
      <div><h2>Audit Log</h2><p>Every real system/user action logged across the app — cases, upgrades, bugs, incidents, customers. Read-only.</p></div>
    </div>

    <div class="tw" style="padding:12px 15px;margin-bottom:14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <input class="inp" style="width:260px" placeholder="Search ref or detail — e.g. DSD-31489, Peak People…" v-model="q" @keyup.enter="reload">
      <select class="sel" v-model="actionFilter" @change="reload">
        <option value="">All actions</option>
        <option v-for="a in actions" :key="a" :value="a">{{ a }}</option>
      </select>
      <select class="sel" v-model="targetTypeFilter" @change="reload">
        <option value="">All target types</option>
        <option v-for="t in targetTypes" :key="t" :value="t">{{ t }}</option>
      </select>
      <button class="btn btn-sm" @click="reload">Search</button>
      <span v-if="!loading" class="sub" style="font-size:10px;color:var(--text3);margin-left:auto">{{ rows.length }} shown</span>
    </div>

    <div v-if="loading && !rows.length" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>
    <div v-else-if="!rows.length" class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:32px 0">No matching audit entries.</div>

    <div v-else class="tw" style="padding:0;overflow:hidden">
      <table class="al-table">
        <thead>
          <tr>
            <th style="width:140px">When</th>
            <th style="width:100px">Actor</th>
            <th style="width:220px">Action</th>
            <th style="width:160px">Target</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td class="al-time">{{ formatWhen(r.created_at) }}</td>
            <td>{{ r.actor }}</td>
            <td><code class="al-action">{{ r.action }}</code></td>
            <td>
              <span v-if="isJiraRef(r.target_id) && r.target_id!.startsWith('DSD-')" class="jref" @click="openCase(r.target_id!)">{{ r.target_id }}</span>
              <span v-else-if="isJiraRef(r.target_id) && r.target_id!.startsWith('VMS-')" class="jref" @click="openBug(r.target_id!)">{{ r.target_id }}</span>
              <span v-else-if="r.target_type === 'customer' && r.target_id" class="jref" @click="goToCustomer(Number(r.target_id), 'overview')">customer #{{ r.target_id }}</span>
              <span v-else-if="r.target_id">{{ r.target_type ? `${r.target_type} ` : '' }}{{ r.target_id }}</span>
              <span v-else class="sub" style="color:var(--text3)">—</span>
            </td>
            <td class="al-detail">{{ r.detail || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="rows.length && !loading" style="text-align:center;margin-top:12px">
      <button class="btn btn-g btn-sm" :disabled="loadingMore" @click="loadMore">{{ loadingMore ? 'Loading…' : 'Load older →' }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type AuditLogEntry } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useBugDrill } from '@/composables/useBugDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCase } = useCaseDrill()
const { openBug } = useBugDrill()
const { openCustomer: goToCustomer } = useCustomerDrill()

const rows = ref<AuditLogEntry[]>([])
const actions = ref<string[]>([])
const q = ref('')
const actionFilter = ref('')
const targetTypeFilter = ref('')
const loading = ref(true)
const loadingMore = ref(false)

// Known target types this app actually writes — kept as a small static
// list rather than a second endpoint, since AuditLog.target_type is a far
// smaller, more stable vocabulary than `action` (which grows constantly).
const targetTypes = ['case', 'upgrade', 'customer', 'bug', 'incident', 'migration', 'cancellation', 'campaign', 'release']

const JIRA_REF_RE = /^(DSD|VMS)-\d+$/
function isJiraRef(id: string | null): boolean {
  return !!id && JIRA_REF_RE.test(id)
}

function formatWhen(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

async function reload() {
  loading.value = true
  try {
    const res = await api.auditLog.list({
      q: q.value.trim() || undefined,
      action: actionFilter.value || undefined,
      target_type: targetTypeFilter.value || undefined,
      limit: 100,
    })
    rows.value = res.data.rows
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!rows.value.length) return
  loadingMore.value = true
  try {
    const oldest = rows.value[rows.value.length - 1].created_at
    const res = await api.auditLog.list({
      q: q.value.trim() || undefined,
      action: actionFilter.value || undefined,
      target_type: targetTypeFilter.value || undefined,
      before: oldest,
      limit: 100,
    })
    rows.value.push(...res.data.rows)
  } finally {
    loadingMore.value = false
  }
}

onMounted(async () => {
  const [logRes, actionsRes] = await Promise.all([
    api.auditLog.list({ limit: 100 }),
    api.auditLog.actions(),
  ])
  rows.value = logRes.data.rows
  actions.value = actionsRes.data.actions
  loading.value = false
})
</script>

<style scoped>
.al-table { width: 100%; border-collapse: collapse; font-size: 10.5px; }
.al-table thead th {
  text-align: left; padding: 8px 10px; font-size: 9px; font-weight: 800; text-transform: uppercase;
  letter-spacing: .06em; color: var(--text3); border-bottom: 1px solid var(--border); background: var(--surface2);
}
.al-table tbody tr { border-bottom: 1px solid var(--border2); }
.al-table tbody tr:hover { background: var(--surface2); }
.al-table td { padding: 6px 10px; vertical-align: top; }
.al-time { color: var(--text3); white-space: nowrap; font-variant-numeric: tabular-nums; }
.al-action { font-size: 9.5px; color: var(--accent); background: var(--accent-dim); padding: 2px 6px; border-radius: 4px; white-space: nowrap; }
.al-detail { color: var(--text2); }
</style>
