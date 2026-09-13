<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Defect intelligence</h2>
        <p>Not a Jira mirror. Each defect carries the chain Jira will not draw: release → environments → customers → cases → incidents.</p>
      </div>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>

    <div v-else class="tw" style="padding:0;overflow:hidden">
      <div class="ed-grid ed-head">
        <div>Ref</div><div>Title</div><div>Sev</div><div>Status</div><div style="text-align:center">Affects</div><div>Fix</div><div style="text-align:right">Age</div><div style="text-align:right">Impact</div>
      </div>
      <template v-for="d in defects" :key="d.vms_ref">
        <div class="ed-grid ed-row" @click="openBug(d.vms_ref)">
          <div class="ed-mono">{{ d.vms_ref }}</div>
          <div class="ed-title">{{ d.title }}</div>
          <div style="font-size:10.5px" :style="{ color: d.critical ? 'var(--red)' : 'var(--text3)' }">{{ d.critical ? 'Critical' : 'Known' }}</div>
          <div class="sub" style="font-size:11px">{{ d.status }}</div>
          <div style="text-align:center;font-variant-numeric:tabular-nums">{{ d.affects_count }}</div>
          <div style="font-size:11px" :class="d.fix_released ? '' : 'ed-unreleased'">
            {{ d.fix_version || '—' }}<span v-if="d.fix_version && !d.fix_released" class="sub" style="font-size:9.5px"> (not released)</span>
          </div>
          <div class="sub" style="text-align:right;font-size:11px">{{ d.age_days != null ? `${d.age_days}d` : '—' }}</div>
          <div style="text-align:right;font-size:11px" :style="{ color: d.critical ? 'var(--red)' : 'var(--text3)' }">{{ d.incident_count ? `${d.incident_count} incident(s)` : `${d.case_count} case(s)` }}</div>
        </div>
      </template>
      <div v-if="!defects.length" class="sub" style="text-align:center;padding:20px;font-size:11px">No real customer-linked defects on file.</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api, type DefectRow } from '@/api/client'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'

const { openEngineeringDefect: openBug } = useEngineeringDrill()

const loading = ref(true)
const defects = ref<DefectRow[]>([])

onMounted(async () => {
  try {
    const res = await api.engineering.defects()
    defects.value = res.data
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.ed-grid { display: grid; grid-template-columns: 90px 2.4fr 0.7fr 0.9fr 0.8fr 1.2fr 0.6fr 1.3fr; gap: 10px; align-items: center; padding: 10px 14px; font-size: 12.5px; }
.ed-head { font-size: 9px; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); box-shadow: inset 0 -1px 0 var(--border); font-weight: 700; }
.ed-row { cursor: pointer; box-shadow: inset 0 -1px 0 var(--border2); }
.ed-row:hover { background: var(--surface2); }
.ed-mono { font-family: ui-monospace, monospace; font-size: 12px; color: var(--accent); }
.ed-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ed-unreleased { color: var(--amber); }
</style>
