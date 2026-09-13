<template>
  <div class="tw md-card" v-if="lanes">
    <div class="md-eyebrow">Where Your Load Sits <span class="md-period">· who's holding the ball right now</span></div>
    <div class="ld-grid">
      <Donut :values="donutValues" :center-value="lanes.total_open + ''" center-label="Open" />
      <div class="md-legend">
        <div v-for="l in lanes.lanes" :key="l.lane" class="md-legend-row">
          <span class="md-legend-dot" :style="{ background: laneColor(l.lane) }"></span>
          <span class="md-legend-name">{{ l.label }}</span>
          <span class="md-legend-val">{{ l.count }} · {{ l.share_pct }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DeskLanes, Lane } from '@/api/client'
import Donut from '@/components/charts/Donut.vue'

const props = defineProps<{ lanes: DeskLanes | null }>()

// Validated categorical series (see main.css) — deliberately NOT reusing
// --green/--amber/--red (those are reserved status colors elsewhere on
// this page, e.g. SLA breach) so a lane's identity never impersonates a
// status indicator. Fixed order, tied to LANE_ORDER's own real sequence.
const LANE_COLORS: Record<Lane, string> = {
  me: 'var(--series-1)',
  defect: 'var(--series-8)',
  devops: 'var(--series-2)',
  dev: 'var(--series-3)',
  customer: 'var(--series-4)',
  csm: 'var(--series-5)',
  escalated: 'var(--series-6)',
  unassigned: 'var(--series-7)',
}
function laneColor(lane: Lane) {
  return LANE_COLORS[lane]
}

const donutValues = computed(() => {
  if (!props.lanes) return []
  return props.lanes.lanes.filter(l => l.count > 0).map(l => ({ value: l.count, color: laneColor(l.lane), label: l.label }))
})
</script>

<style scoped>
.ld-grid { display: grid; grid-template-columns: 88px 1fr; gap: 18px; align-items: center; }
.md-legend { display: flex; flex-direction: column; gap: 5px; width: 100%; }
.md-legend-row { display: flex; align-items: center; gap: 6px; font-size: 10.5px; }
.md-legend-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.md-legend-name { flex: 1; color: var(--text2); }
.md-legend-val { font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
</style>
