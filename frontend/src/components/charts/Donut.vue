<template>
  <svg viewBox="0 0 36 36" class="donut">
    <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--surface2)" stroke-width="3.2" />
    <circle
      v-for="(seg, i) in segments"
      :key="i"
      cx="18" cy="18" r="15.9" fill="none"
      :stroke="seg.color"
      stroke-width="3.2"
      stroke-linecap="round"
      :stroke-dasharray="`${seg.pct} ${100 - seg.pct}`"
      :stroke-dashoffset="seg.offset"
      transform="rotate(-90 18 18)"
      class="donut-seg"
      :style="{ color: seg.color }"
    >
      <title v-if="seg.label">{{ seg.label }}: {{ seg.value }}{{ seg.sharePct != null ? ` (${seg.sharePct}%)` : '' }}</title>
    </circle>
    <text x="18" y="17" text-anchor="middle" class="donut-val">{{ centerValue }}</text>
    <text x="18" y="23" text-anchor="middle" class="donut-lbl">{{ centerLabel }}</text>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  values: { value: number; color: string; label?: string }[]
  centerValue: string | number
  centerLabel: string
}>()

// A small fixed gap (in arc-percent) between segments — the "surface gap"
// spacer from the dataviz mark specs, so rounded end-caps read as distinct
// segments instead of bleeding into each other at the seams.
const GAP_PCT = 1.4

const segments = computed(() => {
  const total = props.values.reduce((s, v) => s + v.value, 0) || 1
  const visible = props.values.filter(v => v.value > 0)
  let cursor = 0
  return visible.map(v => {
    const rawPct = (v.value / total) * 100
    const pct = Math.max(0, rawPct - GAP_PCT)
    const seg = {
      pct, color: v.color, offset: -cursor, label: v.label,
      value: v.value, sharePct: Math.round(rawPct),
    }
    cursor += rawPct
    return seg
  })
})
</script>

<style scoped>
.donut { width: 88px; height: 88px; overflow: visible; }
.donut-seg { transition: stroke-dasharray .25s ease; filter: drop-shadow(0 0 1.5px currentColor); }
.donut-val { font-size: 7px; font-weight: 800; fill: var(--text); }
.donut-lbl { font-size: 2.6px; text-transform: uppercase; letter-spacing: .08em; fill: var(--text3); font-weight: 700; }
</style>
