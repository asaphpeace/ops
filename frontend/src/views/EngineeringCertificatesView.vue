<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>SSL Certificates</h2>
        <p>Certificate expiry for every real tenant host on file, read by a daily TLS handshake against each subdomain — no manual renewal tracking.</p>
      </div>
    </div>

    <div class="tw" style="padding:12px 15px;margin-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
      <span class="sub" style="font-size:10.5px;color:var(--text3)">
        {{ summary?.last_scan_at ? `Last scanned ${formatDateTime(summary.last_scan_at)}` : 'Never scanned' }}
      </span>
      <button class="btn btn-g btn-sm" style="margin-left:auto" :disabled="scanning || summary?.scan_running" @click="runScan">
        {{ scanning || summary?.scan_running ? 'Scanning…' : '🔍 Scan Now' }}
      </button>
    </div>
    <div v-if="scanning || summary?.scan_running" class="sub" style="font-size:10.5px;color:var(--text3);margin:-8px 0 14px">
      A full scan of ~{{ summary?.total ?? '120' }} hosts takes a minute or two and runs server-side — this page can be left and checked again later.
    </div>

    <div class="stats-row sr-6" style="margin-bottom:14px">
      <div class="sc">
        <div class="lbl">Total Hosts</div>
        <div class="val">{{ summary?.total ?? '—' }}</div>
      </div>
      <div class="sc" :class="summary?.expiring ? 'warn' : ''">
        <div class="lbl">Expiring ≤{{ summary?.warn_days ?? 30 }}d</div>
        <div class="val">{{ summary?.expiring ?? '—' }}</div>
      </div>
      <div class="sc" :class="summary?.critical ? 'alert' : ''">
        <div class="lbl">Critical ≤{{ summary?.critical_days ?? 7 }}d</div>
        <div class="val">{{ summary?.critical ?? '—' }}</div>
      </div>
      <div class="sc" :class="summary?.expired ? 'alert' : ''">
        <div class="lbl">Expired</div>
        <div class="val">{{ summary?.expired ?? '—' }}</div>
      </div>
      <div class="sc" :class="summary?.error ? 'warn' : ''">
        <div class="lbl">Unreachable</div>
        <div class="val">{{ summary?.error ?? '—' }}</div>
      </div>
      <div class="sc">
        <div class="lbl">Never Checked</div>
        <div class="val">{{ summary?.never_checked ?? '—' }}</div>
      </div>
    </div>

    <div class="tw" style="padding:0;overflow:hidden">
      <div style="display:flex;align-items:center;gap:10px;padding:12px 14px 8px;flex-wrap:wrap">
        <span class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);font-weight:800">Hosts</span>
        <span class="sub" style="font-size:11px">{{ filteredRows.length }}</span>
        <FilterPills :options="statusOptions" all-label="All statuses" v-model="statusFilter" />
        <FilterPills :options="tierOptions" all-label="All tiers" v-model="tierFilter" />
        <input class="inp" v-model="query" placeholder="customer, subdomain, issuer…" style="margin-left:auto;width:220px;font-size:11.5px">
      </div>
      <div class="cert-inv-head">
        <div>Host</div><div>Customer</div><div>Env</div><div>Expires</div><div style="text-align:right">Days</div><div>Issuer</div><div style="text-align:right">Status</div>
      </div>
      <div v-for="r in filteredRows" :key="r.id" class="cert-inv-row" @click="goToCustomer(r.customer_id, r.environment)">
        <div class="cert-mono">{{ r.hostname }}</div>
        <div class="cert-ellipsis">{{ r.customer_name || '—' }}</div>
        <div><span :class="['env-badge', envClass(r.environment)]" style="font-size:9px">{{ r.environment }}</span></div>
        <div class="sub" style="font-size:11px">{{ r.cert_expires_at ? formatDate(r.cert_expires_at) : '—' }}</div>
        <div style="text-align:right;font-variant-numeric:tabular-nums" :class="daysClass(r)">{{ r.days_until_expiry ?? '—' }}</div>
        <div class="sub cert-ellipsis" style="font-size:10.5px">{{ r.cert_issuer || '—' }}</div>
        <div style="text-align:right">
          <span class="cert-status" :class="r.status">{{ statusLabel(r.status) }}</span>
          <div v-if="r.cert_check_error" class="sub" style="font-size:9px;color:var(--red);margin-top:2px">{{ r.cert_check_error }}</div>
        </div>
      </div>
      <div v-if="!filteredRows.length" class="sub" style="text-align:center;padding:20px;font-size:11px">
        {{ rows.length ? 'No matches.' : 'No scan has run yet — the daily sweep runs at 03:00 UTC, or scan now.' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type CertRow, type CertSummary, type CertStatus } from '@/api/client'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'
import FilterPills from '@/components/FilterPills.vue'

const { openEngineeringCustomer: goToCustomer } = useEngineeringDrill()

const summary = ref<CertSummary | null>(null)
const rows = ref<CertRow[]>([])
const scanning = ref(false)
const query = ref('')
const statusFilter = ref('')
const tierFilter = ref('')

const statusOptions = [
  { value: 'expired', label: 'Expired' },
  { value: 'critical', label: 'Critical' },
  { value: 'expiring', label: 'Expiring' },
  { value: 'error', label: 'Unreachable' },
  { value: 'valid', label: 'Valid' },
]
const tierOptions = [
  { value: 'Premier', label: 'Premier' },
  { value: 'Strategic', label: 'Strategic' },
  { value: 'Scale', label: 'Scale' },
]

const filteredRows = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter(r => {
    if (statusFilter.value && r.status !== statusFilter.value) return false
    if (tierFilter.value && r.tier !== tierFilter.value) return false
    if (q) {
      const hay = `${r.customer_name ?? ''} ${r.subdomain} ${r.hostname} ${r.cert_issuer ?? ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

function envClass(env: string) {
  return env === 'PROD' ? 'ep' : env === 'TEST' ? 'et' : 'ed'
}
function statusLabel(s: CertStatus): string {
  return { valid: 'Valid', expiring: 'Expiring', critical: 'Critical', expired: 'Expired', error: 'Unreachable', never_checked: 'Never checked' }[s]
}
function daysClass(r: CertRow): string {
  if (r.days_until_expiry == null) return ''
  if (r.days_until_expiry < 0) return 'em-alert'
  if (r.days_until_expiry <= (summary.value?.critical_days ?? 7)) return 'em-alert'
  if (r.days_until_expiry <= (summary.value?.warn_days ?? 30)) return 'em-warn-text'
  return ''
}
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}
function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

async function loadCertificates() {
  const res = await api.engineering.certificates()
  summary.value = res.data.summary
  rows.value = res.data.rows
}

async function runScan() {
  scanning.value = true
  try {
    await api.engineering.scanCertificates()
    // Poll every 5s until the background scan flips scan_running back off,
    // then do one final refresh — same pattern as Ollama's content-index
    // refresh button.
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 5000))
      await loadCertificates()
      if (!summary.value?.scan_running) break
    }
  } finally {
    scanning.value = false
  }
}

onMounted(loadCertificates)
</script>

<style scoped>
.cert-inv-head { display: grid; grid-template-columns: 1.6fr 1.6fr 0.6fr 1fr 0.6fr 1.2fr 0.9fr; font-size: 9px; letter-spacing: .06em; text-transform: uppercase; color: var(--text3); padding: 8px 14px; box-shadow: inset 0 -1px 0 var(--border); }
.cert-inv-row { display: grid; grid-template-columns: 1.6fr 1.6fr 0.6fr 1fr 0.6fr 1.2fr 0.9fr; align-items: center; padding: 8px 14px; font-size: 11.5px; cursor: pointer; box-shadow: inset 0 -1px 0 var(--border2); }
.cert-inv-row:hover { background: var(--surface2); }
.cert-mono { font-family: ui-monospace, monospace; color: var(--text2); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cert-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.cert-status { font-size: 8px; font-weight: 800; text-transform: uppercase; padding: 2px 6px; border-radius: 3px; white-space: nowrap; }
.cert-status.valid { background: var(--green-dim); color: var(--green); }
.cert-status.expiring { background: var(--amber-dim); color: var(--amber); }
.cert-status.critical, .cert-status.expired { background: var(--red-dim); color: var(--red); }
.cert-status.error, .cert-status.never_checked { background: var(--surface2); color: var(--text3); }
</style>
