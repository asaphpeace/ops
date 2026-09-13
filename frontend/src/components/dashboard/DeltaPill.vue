<template>
  <span class="delta-pill" :class="isGood ? 'delta-good' : 'delta-bad'">
    <span class="delta-arrow">{{ value > 0 ? '↑' : value < 0 ? '↓' : '→' }}</span>{{ Math.abs(value) }}{{ suffix }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  value: number
  suffix?: string
  // Most deltas here are "more is good" (resolved count, ARR); a few are
  // "less is good" (SLA breaches, open-load growth) — pass 'down' for those
  // so a rising number renders as bad (red), not accidentally green.
  goodDirection?: 'up' | 'down'
}>(), {
  suffix: '%',
  goodDirection: 'up',
})

const isGood = computed(() => {
  if (props.value === 0) return true
  const rising = props.value > 0
  return props.goodDirection === 'up' ? rising : !rising
})
</script>

<style scoped>
.delta-pill {
  display: inline-flex; align-items: center; gap: 2px;
  font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 10px;
  font-variant-numeric: tabular-nums;
}
.delta-arrow { font-size: 9px; line-height: 1; }
.delta-good { background: var(--green-dim); color: var(--green); }
.delta-bad { background: var(--red-dim); color: var(--red); }
</style>
