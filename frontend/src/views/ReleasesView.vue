<template>
  <div class="view">
    <div class="sh">
      <div><h2>Release Intelligence</h2><p>Track releases · see who needs upgrading · generate proactive contact lists</p></div>
      <button class="btn">+ Add Release</button>
    </div>
    <div class="info-bar">ℹ When a release is added and defects are tagged, Sedna Ops automatically identifies which customers have those defects open and are below the fix version — generating your proactive upgrade contact list.</div>

    <div style="display:grid;grid-template-columns:320px 1fr;gap:16px">
      <div>
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">Recent Releases</div>
        <div v-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-for="r in releases" :key="r.id" class="ric">
          <div class="ri-ver">{{ r.version }}</div>
          <div class="ri-meta">
            Released {{ formatDate(r.released_at) }}
            · {{ r.defects_fixed }} defect{{ r.defects_fixed !== 1 ? 's' : '' }} fixed
            <span v-if="r.improvements"> · {{ r.improvements }} improvement{{ r.improvements !== 1 ? 's' : '' }}</span>
          </div>
          <div v-if="r.is_latest" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
            <span class="type-badge type-s">Current latest</span>
          </div>
          <div v-if="r.notes" class="ri-impact">{{ r.notes }}</div>
        </div>
      </div>
      <div>
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">
          {{ latest?.version }} — Customers Below This Version
        </div>
        <div class="info-bar" style="margin-bottom:12px">Phase 2 will cross-reference open defects with customer versions to generate proactive upgrade contact lists.</div>
        <div class="tw">
          <table>
            <thead>
              <tr><th>Customer</th><th>Tier</th><th>Current Version</th><th>Gap</th><th>Renewal</th><th>Action</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in belowLatest" :key="c.id">
                <td class="td-name">{{ c.name }}</td>
                <td><span :class="['tier-badge', tierClass(c.tier)]">{{ c.tier }}</span></td>
                <td class="vm" :style="versionColor(c.prod_version)">{{ c.prod_version }}</td>
                <td class="vm" style="color:var(--text3)">→ {{ latest?.version }}</td>
                <td>{{ formatRenewal(c.renewal_date) }}</td>
                <td><button class="btn btn-sm">Recommend Upgrade</button></td>
              </tr>
              <tr v-if="!belowLatest.length && !loading">
                <td colspan="6" style="text-align:center;color:var(--text3);padding:16px">All customers on latest version.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type Release, type Customer } from '@/api/client'

const releases = ref<Release[]>([])
const customers = ref<Customer[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [relRes, custRes] = await Promise.all([api.releases.list(), api.customers.list()])
    releases.value = relRes.data
    customers.value = custRes.data
  } finally {
    loading.value = false
  }
})

const latest = computed(() => releases.value.find(r => r.is_latest) ?? releases.value[0])

const belowLatest = computed(() => {
  if (!latest.value) return []
  const latestNum = parseFloat(latest.value.version.replace('-R', ''))
  return customers.value.filter(c => {
    if (!c.prod_version) return false
    return parseFloat(c.prod_version.replace('-R', '')) < latestNum
  })
})

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
function formatRenewal(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}
function tierClass(tier: string) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
function versionColor(v?: string | null) {
  if (!v) return ''
  const num = parseFloat(v.replace('-R', ''))
  if (num < 8.23) return 'color:var(--red)'
  if (num < 8.27) return 'color:var(--amber)'
  return ''
}
</script>
