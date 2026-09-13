<template>
  <div>
    <div v-for="b in buckets" :key="b.label" class="ab-row">
      <div class="ab-label">{{ b.label }}</div>
      <div class="ab-track">
        <div class="ab-fill" :class="colorClass(b.label)" :style="{ width: b.share_pct + '%' }"></div>
      </div>
      <div class="ab-count">{{ b.count }} · {{ b.share_pct }}%</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AgingBucket } from '@/api/client'

defineProps<{ buckets: AgingBucket[] }>()

function colorClass(label: string) {
  if (label.startsWith('0-7') || label.startsWith('8-30')) return 'ab-ok'
  if (label.startsWith('31-90')) return 'ab-warn'
  return 'ab-bad'
}
</script>

<style scoped>
.ab-row { display: flex; align-items: center; gap: 9px; margin-bottom: 8px; }
.ab-label { font-size: 10px; color: var(--text2); width: 90px; flex-shrink: 0; }
.ab-track { flex: 1; height: 14px; background: var(--surface2); border-radius: 3px; overflow: hidden; }
.ab-fill { height: 100%; border-radius: 3px; transition: width .2s; }
.ab-ok { background: var(--green); }
.ab-warn { background: var(--amber); }
.ab-bad { background: var(--red); }
.ab-count { font-size: 10px; color: var(--text3); width: 70px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }
</style>
