<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Version intelligence</h2>
        <p>Pick a release to see exactly which estate it owns — and who is exposed if it turns out to be the problem.</p>
      </div>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>

    <div v-else class="ev-body">
      <div class="tw" style="padding:0;overflow:hidden;align-self:start">
        <div
          v-for="v in versions" :key="v.version"
          class="ev-row" :class="{ active: selected === v.version }"
          @click="selected = v.version"
        >
          <div style="display:flex;align-items:baseline;gap:8px">
            <span style="font-weight:700;font-size:14px;font-variant-numeric:tabular-nums">{{ v.version }}</span>
            <span style="font-size:10.5px" :style="{ color: statusColor(v.status) }">{{ v.status }}</span>
            <span class="sub" style="margin-left:auto;font-size:11px">{{ v.envs }} env</span>
          </div>
          <div style="display:flex;gap:10px;font-size:10.5px;color:var(--text3);margin-top:3px">
            <span>{{ v.released_at }}</span><span>{{ v.known_defect_count }} known defect(s)</span>
          </div>
          <div class="ev-share-track"><div class="ev-share-fill" :style="{ width: v.share, background: statusColor(v.status) }"></div></div>
        </div>
      </div>

      <div v-if="detail" style="display:flex;flex-direction:column;gap:14px">
        <div class="tw" style="padding:16px">
          <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap">
            <span style="font-weight:700;font-size:24px;font-variant-numeric:tabular-nums">{{ detail.version }}</span>
            <span class="tag-outline">{{ detail.status }}</span>
            <span class="sub" style="font-size:11.5px">
              released {{ detail.released_at }} · {{ detail.age_days }}d ago
              <template v-if="detail.previous_version"> · previous {{ detail.previous_version }}</template>
              <template v-if="detail.next_version"> · next {{ detail.next_version }}</template>
            </span>
          </div>
          <div class="ev-stats">
            <div v-for="s in statTiles" :key="s.label" class="ev-stat-tile">
              <div class="sub" style="font-size:9.5px;text-transform:uppercase;letter-spacing:.08em">{{ s.label }}</div>
              <div style="font-weight:700;font-size:20px;margin-top:3px" :style="{ color: s.color }">{{ s.value }}</div>
              <div class="sub" style="font-size:10.5px">{{ s.sub }}</div>
            </div>
          </div>
        </div>

        <div class="tw" style="padding:16px">
          <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);font-weight:800;margin-bottom:10px">If this release is the problem</div>
          <div style="font-size:14px;line-height:1.5">{{ detail.exposure_sentence }}</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:12px">
            <button v-for="c in detail.affected_customers" :key="c.id" class="btn btn-g btn-sm" @click="goToCustomer(c.id, 'overview')">{{ c.name }}</button>
          </div>
        </div>

        <div class="tw" style="padding:16px">
          <div class="lbl" style="font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);font-weight:800;margin-bottom:8px">Known defects in this release</div>
          <div v-for="d in detail.known_defects" :key="d.vms_ref" class="ev-defect-row" @click="openBug(d.vms_ref)">
            <span class="ev-mono">{{ d.vms_ref }}</span>
            <span style="flex:1;font-size:12.5px">reported by {{ d.reported_count }} customer(s)</span>
            <span style="font-size:10.5px" :style="{ color: d.critical ? 'var(--red)' : 'var(--text3)' }">{{ d.critical ? 'Critical' : 'Known' }}</span>
            <span class="sub" style="font-size:10.5px">fix {{ d.fix_version }}</span>
          </div>
          <div v-if="!detail.known_defects.length" class="sub" style="font-size:11px">No known defects unresolved for this exact version.</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api, type VersionListItem, type VersionDetail } from '@/api/client'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'

const { openEngineeringCustomer: goToCustomer, openEngineeringDefect: openBug } = useEngineeringDrill()

const loading = ref(true)
const versions = ref<VersionListItem[]>([])
const selected = ref<string | null>(null)
const detail = ref<VersionDetail | null>(null)

function statusColor(status: string | null): string {
  if (status === 'Current') return 'var(--green)'
  if (status === 'Supported') return 'var(--accent)'
  if (status === 'Ageing') return 'var(--amber)'
  if (status === 'Legacy' || status === 'End of life') return 'var(--red)'
  return 'var(--text3)'
}

const statTiles = computed(() => {
  if (!detail.value) return []
  const s = detail.value.stats
  return [
    { label: 'Environments', value: s.environments, sub: 'on this exact version', color: 'var(--text)' },
    { label: 'Customers', value: s.customers, sub: 'distinct real customers', color: 'var(--text)' },
    { label: 'Estate Share', value: s.estate_share, sub: 'of all tracked environments', color: 'var(--text)' },
    { label: 'Known Defects', value: s.known_defects, sub: 'still unresolved', color: s.known_defects ? 'var(--amber)' : 'var(--text)' },
    { label: 'Critical', value: s.critical, sub: 'multi-customer-reported', color: s.critical ? 'var(--red)' : 'var(--text)' },
    { label: 'Live Incidents', value: s.live_incidents, sub: 'open, affecting this version', color: s.live_incidents ? 'var(--red)' : 'var(--text)' },
  ]
})

async function loadDetail(version: string) {
  const res = await api.engineering.versionDetail(version)
  detail.value = res.data
}

watch(selected, (v) => { if (v) loadDetail(v) })

onMounted(async () => {
  try {
    const res = await api.engineering.versions()
    versions.value = res.data
    if (versions.value.length) selected.value = versions.value[0].version
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.ev-body { display: grid; grid-template-columns: minmax(0, 320px) minmax(0, 1fr); gap: 20px; align-items: start; }
.ev-row { padding: 12px 14px; cursor: pointer; box-shadow: inset 0 -1px 0 var(--border2); }
.ev-row:hover { background: var(--surface2); }
.ev-row.active { background: var(--accent-dim); }
.ev-share-track { height: 3px; border-radius: 2px; margin-top: 8px; background: var(--border2); }
.ev-share-fill { height: 3px; border-radius: 2px; }
.tag-outline { font-size: 10.5px; border: 1px solid var(--border); border-radius: 5px; padding: 2px 8px; color: var(--text2); }
.ev-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 11px; margin-top: 16px; }
.ev-stat-tile { padding: 11px; background: var(--surface2); border-radius: 8px; }
.ev-defect-row { display: flex; align-items: center; gap: 11px; padding: 8px 0; cursor: pointer; box-shadow: inset 0 -1px 0 var(--border2); }
.ev-defect-row:last-child { box-shadow: none; }
.ev-defect-row:hover { opacity: .8; }
.ev-mono { font-family: ui-monospace, monospace; font-size: 12px; color: var(--accent); min-width: 76px; }
</style>
